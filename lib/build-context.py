"""Copy only build inputs into a Docker dependency-installation context."""

import hashlib
import gzip
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def prepare(context, architecture):
    root = Path(os.environ["FRAMEWORK_DIR"])
    workspace = Path(os.environ["WORKSPACE"])
    selection = json.loads((workspace / "build-dependencies.json").read_text())[architecture]
    if "unavailable" in selection:
        raise ValueError(f"No private build dependencies for {architecture}")
    framework = context / "framework"
    framework.mkdir()
    shutil.copytree(root / "lib", framework / "lib", ignore=shutil.ignore_patterns("__pycache__"))
    def ignore_generated(directory, names):
        return [name for name in names if name == "__pycache__"
                or (name == "build" and (Path(directory) / name).is_dir())]

    shutil.copytree(os.environ["ADAPTER_DIR"], framework / "adapter", ignore=ignore_generated)
    shutil.copyfile(root / "Dockerfile", framework / "Dockerfile")
    shutil.copyfile(root / "lib/build-worker.Dockerfile", context / "Dockerfile")
    repository = context / "repository"
    pool = repository / "pool"
    pool.mkdir(parents=True)
    for number, package in enumerate(selection["packages"]):
        source = Path(package["path"])
        if hashlib.sha256(source.read_bytes()).hexdigest() != package["sha256"]:
            raise ValueError(f"Private build dependency changed: {source}")
        shutil.copyfile(source, pool / f"{number}.deb")
    with (repository / "Packages").open("w") as output:
        subprocess.run(["dpkg-scanpackages", "--multiversion", "pool"],
                       cwd=repository, stdout=output, check=True)
    (repository / "Packages.gz").write_bytes(gzip.compress(
        (repository / "Packages").read_bytes(), mtime=0))
    with (repository / "Release").open("w") as output:
        subprocess.run(["apt-ftparchive", "release", "."], cwd=repository,
                       stdout=output, check=True)
    (context / "install").write_text("\n".join(selection["install"]) + "\n")
    # Deliberately exclude signing identities, operator secrets, and arbitrary
    # coordinator environment variables from workers.
    names = ("MAINTAINER", "PUBLISHER_STREAM", "BUILD_INPUTS_SHA256", "BINARY_PACKAGES",
             "BINARY_PACKAGES_AMD64", "BINARY_PACKAGES_ARM64", "ARCHES")
    environment = {name: os.environ[name] for name in names if name in os.environ}
    environment.update(FRAMEWORK_DIR="/framework", ADAPTER_DIR="/framework/adapter",
                       WORKSPACE=str(workspace), HOME="/tmp")
    for name, value in environment.items():
        if "\n" in value or "\r" in value:
            raise ValueError(f"Worker environment {name} must be single-line")
    (context / "environment").write_text("".join(
        f"{name}={value}\n" for name, value in environment.items()))
    (context / "architecture").write_text(architecture + "\n")
    (context / "workspace").write_text(str(workspace) + "\n")


def record_dependencies(context, architecture, output):
    workspace = Path(os.environ["WORKSPACE"])
    selection = json.loads((workspace / "build-dependencies.json").read_text())[architecture]
    installed_bytes = (context / "installed-packages").read_bytes()
    installed = {}
    for line in installed_bytes.decode().splitlines():
        name, version, package_architecture = line.split("\t")
        installed[(name, package_architecture)] = version
    for requirement in selection["install"]:
        name_architecture, version = requirement.split("=", 1)
        name, target = name_architecture.split(":", 1)
        if (installed.get((name, target)) != version
                and installed.get((name, "all")) != version):
            raise ValueError(f"Worker did not install required private package {requirement}")
    records = []
    for package in selection["packages"]:
        key = (package["package"], package["architecture"])
        if key in installed:
            if installed[key] != package["version"]:
                raise ValueError(f"Worker installed unexpected {key}: {installed[key]}")
            records.append(f"{key[0]}:{key[1]} (= {installed[key]})")
    if not records:
        raise ValueError("Worker installed none of the selected private dependencies")
    helper_path = Path(os.environ["FRAMEWORK_DIR"]) / "lib/adapter/rewrite-control.py"
    specification = importlib.util.spec_from_file_location("dependency_control", helper_path)
    helper = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(helper)
    replacements = {
        "X-Private-Build-Dependencies": ", ".join(sorted(records)),
        "X-Build-Environment-SHA256": hashlib.sha256(installed_bytes).hexdigest(),
    }
    for path in sorted(output.glob("*.deb")):
        with tempfile.TemporaryDirectory(prefix="dependency-control-", dir=workspace) as directory:
            tree = Path(directory) / "package"
            subprocess.run(["dpkg-deb", "--raw-extract", str(path), str(tree)], check=True)
            control = tree / "DEBIAN/control"
            control.write_text(helper.rewrite_fields(control.read_text(), replacements))
            result = Path(directory) / "annotated.deb"
            subprocess.run(["dpkg-deb", "--build", "--root-owner-group", "-Zgzip",
                            str(tree), str(result)], check=True)
            result.replace(path)


if __name__ == "__main__":
    try:
        if sys.argv[1] == "record":
            record_dependencies(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))
        else:
            prepare(Path(sys.argv[1]), sys.argv[2])
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
