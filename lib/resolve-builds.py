"""Validate upstream targets and choose the packages that need building."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import sys


@dataclass
class PackageFile:
    path: Path
    name: str
    version: str
    architecture: str
    stream: str
    checksum: str


def read_package(path):
    """Read the small control archive; leave the package payload compressed."""
    result = subprocess.run(
        ["dpkg-deb", "--field", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )

    fields = {}
    for line in result.stdout.splitlines():
        if not line or line[0].isspace() or ":" not in line:
            continue
        name, value = line.split(":", 1)
        fields[name.lower()] = value.strip()

    return PackageFile(
        path=path,
        name=fields.get("package", ""),
        version=fields.get("version", ""),
        architecture=fields.get("architecture", ""),
        stream=fields.get("x-publisher-stream", ""),
        checksum=fields.get("x-build-inputs-sha256", ""),
    )


def check_filename(package):
    name, version, architecture = package.path.stem.split("_")
    if name != package.name or architecture != package.architecture:
        raise ValueError(f"Filename does not match package metadata: {package.path}")

    # Older repository managers may leave the epoch out of filenames.
    version_without_epoch = package.version.split(":", 1)[-1]
    if version != package.version and version != version_without_epoch:
        raise ValueError(f"Filename does not match package version: {package.path}")


def list_packages(package_name):
    pool = Path(os.environ["REPO_DIR"]) / "pool"
    packages = []

    for path in sorted(pool.rglob(f"{package_name}_*.deb")):
        package = read_package(path)
        check_filename(package)
        packages.append(package)

    return packages


def choose_version(packages, upstream_version, stream, checksum):
    highest_revision = 0
    latest_stream_package = None
    latest_stream_revision = 0

    for package in packages:
        upstream, _, revision_text = package.version.rpartition("-")
        if upstream != upstream_version:
            continue

        if not revision_text.isascii() or not revision_text.isdigit():
            raise ValueError(f"Cannot increment Debian revision: {package.version}")
        revision = int(revision_text)
        if revision < 1:
            raise ValueError(f"Debian revision must be positive: {package.version}")

        highest_revision = max(highest_revision, revision)
        if package.stream != stream:
            continue

        if revision == latest_stream_revision:
            if package.checksum != latest_stream_package.checksum:
                raise ValueError(f"Conflicting checksums for {stream} {package.version}")

        if revision > latest_stream_revision:
            latest_stream_revision = revision
            latest_stream_package = package

    if latest_stream_package is not None:
        if latest_stream_package.checksum == checksum:
            return latest_stream_package.version

    return f"{upstream_version}-{highest_revision + 1}"


def find_package(packages, name, version, architecture):
    for package in packages:
        if (
            package.name == name
            and package.version == version
            and package.architecture in (architecture, "all")
        ):
            return package
    return None


def read_targets(path, architectures):
    seen = set()
    targets = []
    content = path.read_bytes().decode("utf-8")
    if content and not content.endswith("\n"):
        raise SystemExit("targets.tsv must end with a newline")

    for number, line in enumerate(content.splitlines(keepends=True), 1):
        line = line.removesuffix("\n")
        fields = line.split("\t")
        if len(fields) != 2:
            raise SystemExit(f"Invalid target row {number}: expected VERSION<TAB>ARCH")

        version, architecture = fields
        if not re.fullmatch(r"[0-9][A-Za-z0-9.+:~\-]*", version):
            raise SystemExit(f"Invalid Debian version in row {number}: {version}")
        subprocess.run(["dpkg", "--validate-version", version], check=True)

        if architecture not in architectures:
            raise SystemExit(f"Unrequested architecture in row {number}: {architecture}")
        if architecture in seen:
            raise SystemExit(f"Multiple current releases for architecture: {architecture}")

        seen.add(architecture)
        targets.append((version, architecture))
    # An empty file is valid: the adapter has no eligible releases.

    return targets


def prepare_builds():
    stream = os.environ["PUBLISHER_STREAM"]
    names = os.environ["BINARY_PACKAGES"].split()
    checksum = os.environ["BUILD_INPUTS_SHA256"]
    workspace = Path(os.environ["WORKSPACE"])
    architectures = set(os.environ["ARCHES"].split())
    targets = read_targets(workspace / "targets.tsv", architectures)

    packages = []
    for name in names:
        packages.extend(list_packages(name))

    selected_versions = {}
    output_path = workspace / "builds.tsv"

    with output_path.open("w") as output:
        for upstream_version, architecture in targets:
            if upstream_version not in selected_versions:
                version = choose_version(
                    packages, upstream_version, stream, checksum
                )
                selected_versions[upstream_version] = version

            version = selected_versions[upstream_version]
            complete = True
            for name in names:
                existing = find_package(packages, name, version, architecture)
                if existing is None:
                    complete = False
                elif existing.checksum != checksum or existing.stream != stream:
                    raise ValueError(f"Package belongs to another build: {existing.path}")

            output.write(f"{version}\t{architecture}\t{'complete' if complete else ''}\n")


if __name__ == "__main__":
    try:
        prepare_builds()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
