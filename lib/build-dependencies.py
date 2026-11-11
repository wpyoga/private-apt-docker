"""Order streams and select complete, stored private build dependencies."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def read_configuration(directory):
    result = subprocess.run(
        ["bash", str(Path(os.environ["FRAMEWORK_DIR"]) / "lib/config.sh")],
        env={**os.environ, "ADAPTER_DIR": str(directory)},
        capture_output=True, text=True,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip())
    stream, names, amd64, arm64 = result.stdout.splitlines()
    return {"directory": str(directory), "stream": stream,
            "packages": {"amd64": (amd64 or names).split(),
                         "arm64": (arm64 or names).split()}}


def read_dependencies(directory):
    path = directory / "build-dependencies"
    if not path.exists():
        return []
    dependencies = []
    seen = set()
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if (len(fields) not in (2, 4)
                or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", fields[0])
                or not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", fields[1])):
            raise ValueError(f"{path}:{number}: expected STREAM PACKAGE [OP VERSION]")
        stream, package = fields[:2]
        if (stream, package) in seen:
            raise ValueError(f"{path}:{number}: duplicate dependency {stream} {package}")
        seen.add((stream, package))
        relation, version = fields[2:] if len(fields) == 4 else (None, None)
        if relation is not None and relation not in ("<<", "<=", "=", ">=", ">>"):
            raise ValueError(f"{path}:{number}: invalid version relation {relation}")
        if version is not None and (not re.fullmatch(r"[0-9][A-Za-z0-9.+:~\-]*", version)
                or subprocess.run(["dpkg", "--validate-version", version],
                                  capture_output=True).returncode):
            raise ValueError(f"{path}:{number}: invalid Debian version {version}")
        dependencies.append({"stream": stream, "package": package,
                             "relation": relation, "version": version})
    return dependencies


def discover():
    streams = {}
    failed = False
    for directory in sorted(Path(os.environ["PACKAGES_DIR"]).iterdir()):
        if not directory.is_dir() or directory.name.startswith("."):
            continue
        try:
            config = read_configuration(directory)
            stream = config["stream"]
            if stream in streams:
                raise ValueError(f"Duplicate RELEASE_STREAM: {stream}")
            config["dependencies"] = read_dependencies(directory)
            streams[stream] = config
        except (ValueError, OSError) as error:
            print(error, file=sys.stderr)
            failed = True
    return streams, failed


def order_streams():
    streams, failed = discover()
    ordered = []
    visited = set()
    blocked = set()

    def visit(stream, chain):
        if stream in visited:
            return stream not in blocked
        if stream in chain:
            raise ValueError("Build dependency cycle: " + " -> ".join([*chain, stream]))
        config = streams[stream]
        valid = True
        for dependency in config["dependencies"]:
            provider = dependency["stream"]
            if provider not in streams:
                raise ValueError(f"{stream}: unknown build dependency stream {provider}")
            names = set()
            for architecture_names in streams[provider]["packages"].values():
                names.update(architecture_names)
            if dependency["package"] not in names:
                raise ValueError(f"{stream}: {provider} does not declare {dependency['package']}")
            if not visit(provider, [*chain, stream]):
                valid = False
        visited.add(stream)
        if valid:
            ordered.append(config["directory"])
        else:
            blocked.add(stream)
        return valid

    for stream in streams:
        try:
            if not visit(stream, []):
                failed = True
        except ValueError as error:
            print(error, file=sys.stderr)
            blocked.add(stream)
            visited.add(stream)
            failed = True
    for directory in ordered:
        sys.stdout.buffer.write(os.fsencode(directory) + b"\0")
    return int(failed)


def package_tools():
    path = Path(os.environ["FRAMEWORK_DIR"]) / "lib/resolve-builds.py"
    spec = importlib.util.spec_from_file_location("stored_packages", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def version_matches(version, dependency):
    if dependency["relation"] is None:
        return True
    return subprocess.run(["dpkg", "--compare-versions", version,
                           dependency["relation"], dependency["version"]]).returncode == 0


def select_packages(streams, consumer, architecture, tools):
    requirements = {}

    def collect(stream, chain):
        if stream in chain:
            raise ValueError("Build dependency cycle: " + " -> ".join([*chain, stream]))
        for dependency in streams[stream]["dependencies"]:
            provider = dependency["stream"]
            if provider not in streams:
                raise ValueError(f"{stream}: unknown build dependency stream {provider}")
            if provider in [*chain, stream]:
                raise ValueError("Build dependency cycle: " + " -> ".join([*chain, stream, provider]))
            first = provider not in requirements
            requirements.setdefault(provider, []).append(dependency)
            if first:
                collect(provider, [*chain, stream])

    collect(consumer, [])
    selected = []
    direct = []
    for stream, dependencies in sorted(requirements.items()):
        names = streams[stream]["packages"][architecture]
        packages = [package for name in names for package in tools.list_packages(name)
                    if package.stream == stream and package.architecture in (architecture, "all")]
        best = None
        chosen = None
        for version in sorted({package.version for package in packages}):
            if not all(version_matches(version, dependency) for dependency in dependencies):
                continue
            outputs = [tools.find_package(packages, name, version, architecture) for name in names]
            if any(package is None for package in outputs):
                continue
            if best is None or subprocess.run(
                    ["dpkg", "--compare-versions", version, "gt", best]).returncode == 0:
                best, chosen = version, outputs
        if chosen is None:
            raise ValueError(f"{consumer}: no complete {architecture} build of {stream} "
                             f"satisfies {dependencies}")
        for dependency in dependencies:
            if dependency["package"] not in names:
                raise ValueError(f"{stream}: {dependency['package']} is unavailable for {architecture}")
            direct.append(f"{dependency['package']}:{architecture}={best}")
        for package in chosen:
            selected.append({"stream": stream, "package": package.name,
                             "version": package.version, "architecture": package.architecture,
                             "path": str(package.path),
                             "sha256": hashlib.sha256(package.path.read_bytes()).hexdigest()})
    names = [package["package"] for package in selected]
    if len(names) != len(set(names)):
        raise ValueError(f"{consumer}: dependency streams provide overlapping binary packages")
    return {"packages": selected, "install": sorted(set(direct))}


def prepare_dependencies():
    workspace = Path(os.environ["WORKSPACE"])
    consumer = os.environ["PUBLISHER_STREAM"]
    directory = Path(os.environ["ADAPTER_DIR"])
    if not read_dependencies(directory):
        return 0
    streams, _ = discover()
    failed = False
    if consumer not in streams:
        raise ValueError(f"Unknown consumer stream: {consumer}")
    tools = package_tools()
    targets = tools.read_targets(workspace / "targets.tsv", set(os.environ["ARCHES"].split()))
    manifest = {}
    errors = {}
    # Always fingerprint both architectures, including unavailable ones. Separate
    # architecture coordinators must calculate the same recipe checksum.
    for architecture in ("amd64", "arm64"):
        try:
            manifest[architecture] = select_packages(streams, consumer, architecture, tools)
        except ValueError as error:
            manifest[architecture] = {"unavailable": True}
            errors[architecture] = str(error)
    (workspace / "build-dependencies.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with (workspace / "targets.tsv").open("w") as output:
        for version, architecture in targets:
            if architecture in errors:
                print(errors[architecture], file=sys.stderr)
                failed = True
            else:
                output.write(f"{version}\t{architecture}\n")
    return int(failed)


if __name__ == "__main__":
    try:
        action = sys.argv[1]
        if action == "order":
            sys.exit(order_streams())
        elif action == "prepare":
            sys.exit(prepare_dependencies())
        else:
            raise ValueError(f"Unknown dependency action: {action}")
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
