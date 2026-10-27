"""Validate Laya's fixed wheel layouts and stage files without importing them."""

import base64
import configparser
import csv
from email.parser import Parser
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import zipfile


LAYA_REQUIREMENTS = {
    "torch>=2.0.0",
    "transformers>=4.48.0",
    "safetensors>=0.4.0",
    "huggingface-hub>=0.20.0",
    "numpy>=1.20.0",
}
SERVE_REQUIREMENTS = {
    "fastapi>=0.110.0", "uvicorn>=0.27.0", "python-multipart>=0.0.9",
}


def check_requirements(metadata, project):
    core = set()
    serve = set()
    structured = set()
    for requirement in metadata.get_all("Requires-Dist", []):
        dependency, separator, marker = requirement.partition(";")
        dependency = dependency.strip().replace("_", "-").lower()
        if not separator:
            core.add(dependency)
        elif marker.strip() == 'extra == "serve"':
            serve.add(dependency)
        elif marker.strip() == 'extra == "structured"':
            structured.add(dependency)
        elif project == "click" and requirement != "colorama; platform_system == 'Windows'":
            raise ValueError(f"Unexpected Click dependency: {requirement}")
        elif project == "laya" and "extra ==" not in marker:
            raise ValueError(f"Unexpected Laya conditional dependency: {requirement}")

    if project == "laya":
        if core != LAYA_REQUIREMENTS:
            raise ValueError(f"Laya core dependencies changed: {sorted(core)}")
        if serve != SERVE_REQUIREMENTS:
            raise ValueError(f"Laya HTTP dependencies changed: {sorted(serve)}")
        if structured != {"pydantic>=2.0.0"}:
            raise ValueError(f"Laya structured dependencies changed: {sorted(structured)}")
    elif core:
        raise ValueError(f"Unexpected Click Linux dependencies: {sorted(core)}")


def check_record(archive, files, dist_info):
    record_name = f"{dist_info}/RECORD"
    rows = csv.reader(io.StringIO(archive.read(record_name).decode()))
    recorded = set()
    for row in rows:
        if len(row) != 3:
            raise ValueError(f"Invalid wheel RECORD row in {record_name}: {row}")
        name, digest, size = row
        if name in recorded or name not in files:
            raise ValueError(f"Unexpected or duplicate wheel RECORD path: {name}")
        recorded.add(name)
        if name == record_name:
            if digest or size:
                raise ValueError(f"Wheel RECORD must not hash itself: {record_name}")
            continue
        data = archive.read(name)
        expected = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        if digest != f"sha256={expected}" or size != str(len(data)):
            raise ValueError(f"Wheel RECORD hash or size mismatch: {name}")
    if recorded != files:
        raise ValueError(f"Wheel RECORD omits files: {sorted(files - recorded)}")


def install_wheel(asset, downloads, destination, project):
    version = asset["version"]
    name = f"{project}-{version}-py3-none-any.whl"
    if asset["name"] != name or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"Unexpected {project} wheel name/version: {asset['name']}")
    wheel_path = downloads / name
    if hashlib.sha256(wheel_path.read_bytes()).hexdigest() != asset["sha256"]:
        raise ValueError(f"SHA256 mismatch for {wheel_path}")

    dist_info = f"{project}-{version}.dist-info"
    license_name = "LICENSE" if project == "laya" else "LICENSE.txt"
    required = {
        f"{project}/__init__.py", f"{dist_info}/METADATA", f"{dist_info}/WHEEL",
        f"{dist_info}/RECORD", f"{dist_info}/licenses/{license_name}",
    }
    if project == "laya":
        required.update({"laya/cli.py", "laya/serve.py", "laya/router.py",
                         f"{dist_info}/entry_points.txt"})

    with zipfile.ZipFile(wheel_path) as archive:
        files = set()
        members = set()
        for entry in archive.infolist():
            path = PurePosixPath(entry.filename)
            mode = entry.external_attr >> 16
            if (path.is_absolute() or ".." in path.parts or "\\" in entry.filename
                    or str(path) != entry.filename.rstrip("/")
                    or not path.parts or path.parts[0] not in (project, dist_info)
                    or entry.filename in members):
                raise ValueError(f"Unexpected {project} wheel path: {entry.filename}")
            members.add(entry.filename)
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError(f"Unsupported wheel file type: {entry.filename}")
            if not entry.is_dir():
                if path.suffix in (".so", ".pth", ".pyc"):
                    raise ValueError(f"Unexpected executable/native wheel payload: {entry.filename}")
                files.add(entry.filename)

        if not required.issubset(files):
            raise ValueError(f"Missing {project} wheel files: {sorted(required - files)}")
        metadata = Parser().parsestr(archive.read(f"{dist_info}/METADATA").decode())
        for field, expected in (("Name", project), ("Version", version), ("Requires-Python", ">=3.10")):
            if metadata.get_all(field) != [expected]:
                raise ValueError(f"Unexpected {project} {field}: {metadata.get_all(field)}; expected {expected}")
        wheel = Parser().parsestr(archive.read(f"{dist_info}/WHEEL").decode())
        if (wheel.get_all("Wheel-Version") != ["1.0"]
                or wheel.get_all("Root-Is-Purelib") != ["true"]
                or wheel.get_all("Tag") != ["py3-none-any"]):
            raise ValueError(f"Expected a pure Python universal wheel: {wheel_path}")
        check_requirements(metadata, project)
        check_record(archive, files, dist_info)

        if project == "laya":
            entry_points = configparser.ConfigParser(interpolation=None)
            entry_points.read_string(archive.read(f"{dist_info}/entry_points.txt").decode())
            for command, target in (("laya", "laya.cli:main"), ("laya-serve", "laya.serve:main")):
                if entry_points.get("console_scripts", command, fallback=None) != target:
                    raise ValueError(f"Unexpected Laya entry point: {command}")
            source = archive.read("laya/__init__.py").decode()
            versions = re.findall(r'^__version__\s*=\s*[\'"]([^\'"]+)[\'"]', source, re.MULTILINE)
            if versions != [version]:
                raise ValueError(f"Laya module version {versions} does not match {version}")

        for name in sorted(files):
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(name))
            path.chmod(0o644)
        return archive.read(f"{dist_info}/licenses/{license_name}")


def main():
    laya_metadata, click_metadata, downloads, staging = map(Path, sys.argv[1:])
    laya = json.loads(laya_metadata.read_text())
    click = json.loads(click_metadata.read_text())
    library = staging / "python3-laya"
    license_text = install_wheel(laya, downloads, library / "usr/lib/python3/dist-packages", "laya")
    click_license = install_wheel(click, downloads, library / "usr/lib/laya/vendor", "click")

    documentation = library / "usr/share/doc/python3-laya"
    documentation.mkdir(parents=True)
    (documentation / "laya-LICENSE").write_bytes(license_text)
    (documentation / "click-LICENSE").write_bytes(click_license)
    adapter = Path(os.environ["ADAPTER_DIR"])
    shutil.copyfile(adapter / "copyright.in", documentation / "copyright")
    for package in ("laya-cli", "laya-http"):
        root = staging / package
        (root / "usr/bin").mkdir(parents=True)
        (root / "usr/share/doc").mkdir(parents=True)
        (root / f"usr/share/doc/{package}").symlink_to("python3-laya")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, zipfile.BadZipFile, configparser.Error) as error:
        sys.exit(f"Laya wheel staging failed: {error}")
