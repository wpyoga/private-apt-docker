"""Choose revisions and store packages using their filenames and control metadata."""

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


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


def find_package(packages, version, architecture):
    for package in packages:
        if package.version == version and package.architecture == architecture:
            return package
    return None


def read_config(adapter):
    values = subprocess.check_output(
        ["bash", str(Path(__file__).with_name("config.sh")), str(adapter)], text=True
    ).splitlines()
    return values[0], values[1].split()


def prepare_builds(adapter, targets, checksum):
    stream, names = read_config(adapter)
    packages = [package for name in names for package in list_packages(name)]
    selected_versions = {}
    output_path = targets.parent / "builds.tsv"

    with output_path.open("w") as output:
        for line in targets.read_text().splitlines():
            upstream_version, architecture = line.split("\t")

            if upstream_version not in selected_versions:
                version = choose_version(
                    packages, upstream_version, stream, checksum
                )
                selected_versions[upstream_version] = version

            version = selected_versions[upstream_version]
            complete = True
            for name in names:
                existing = find_package(
                    [package for package in packages if package.name == name],
                    version, architecture,
                )
                if existing is None:
                    complete = False
                elif existing.checksum != checksum or existing.stream != stream:
                    raise ValueError(f"Package belongs to another build: {existing.path}")
            output.write(f"{version}\t{architecture}\t{'complete' if complete else ''}\n")


def validate_build(package, name, version, architecture, stream, checksum):
    if package.name != name:
        raise ValueError(f"Built package name must be {name}")
    if package.version != version:
        raise ValueError(f"Built package version must be {version}")
    if package.architecture != architecture:
        raise ValueError(f"Built package architecture must be {architecture}")
    if package.stream != stream:
        raise ValueError(f"Built package stream must be {stream}")
    if package.checksum != checksum:
        raise ValueError("Built package has an incorrect input checksum")


def copy_package(source, destination):
    """Make a complete file visible at once, without replacing an existing file."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".package-", dir=destination.parent)

    try:
        with os.fdopen(descriptor, "wb") as output:
            with source.open("rb") as incoming:
                shutil.copyfileobj(incoming, output)
            output.flush()
            os.fsync(output.fileno())
            os.fchmod(output.fileno(), 0o644)

        # A hard link refuses to overwrite an existing destination.
        os.link(temporary, destination)
    finally:
        os.unlink(temporary)


def store_packages(adapter, version, architecture, checksum, source):
    stream, names = read_config(adapter)
    paths = sorted(source.iterdir())
    expected = {f"{name}_{version}_{architecture}.deb" for name in names}
    if {path.name for path in paths} != expected or any(not path.is_file() for path in paths):
        raise ValueError("Build output must contain exactly the declared binary packages")

    # Validate the entire output set before storing any of it.
    pending = []
    for path in paths:
        package = read_package(path)
        check_filename(package)
        validate_build(package, path.name.split("_")[0], version, architecture, stream, checksum)
        existing = find_package(list_packages(package.name), version, architecture)
        if existing is not None:
            validate_build(existing, package.name, version, architecture, stream, checksum)
            # A resumed build may regenerate existing outputs. Preserve their bytes.
            continue
        pending.append(path)
    for path in pending:
        destination = Path(os.environ["REPO_DIR"]) / "pool/main" / stream / path.name
        copy_package(path, destination)


def main():
    command = sys.argv[1]
    adapter = Path(sys.argv[2])

    if command == "resolve":
        targets = Path(sys.argv[3])
        checksum = sys.argv[4]
        prepare_builds(adapter, targets, checksum)
    elif command == "store":
        version = sys.argv[3]
        architecture = sys.argv[4]
        checksum = sys.argv[5]
        source = Path(sys.argv[6])
        store_packages(adapter, version, architecture, checksum, source)
    else:
        raise ValueError(f"Unknown package-file operation: {command}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
