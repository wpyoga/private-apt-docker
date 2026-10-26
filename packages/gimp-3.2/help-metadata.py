"""Read pinned Debian manuals and validate their repackaged metadata."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys


workspace = Path(os.environ["WORKSPACE"])


def fields(text):
    result = {}
    previous = None
    for line in text.splitlines():
        if line.startswith((" ", "\t")) and previous:
            result[previous] += "\n" + line
        elif ": " in line:
            previous, value = line.split(": ", 1)
            result[previous] = value
    return result


def query():
    selected = {}
    names = {name for name in os.environ["BINARY_PACKAGES"].split() if name.startswith("gimp-help-")}
    manifest = Path(os.environ["ADAPTER_DIR"]) / "help-assets"
    for line in manifest.read_text().splitlines():
        name, version, digest, filename = line.split("|")
        if (name in selected or name not in names
                or not re.fullmatch(r"3\.2\.\d+-[0-9]+", version)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or filename != f"pool/main/g/gimp-help/{name}_{version}_all.deb"):
            raise SystemExit(f"Unexpected pinned help asset: {line}")
        selected[name] = {"Version": version, "Filename": filename, "SHA256": digest}
    if set(selected) != names:
        raise SystemExit(f"Missing pinned GIMP help packages: {sorted(names - set(selected))}")
    versions = {row["Version"] for row in selected.values()}
    if len(versions) != 1:
        raise SystemExit(f"Debian help packages have inconsistent versions: {sorted(versions)}")
    (workspace / "help-assets.json").write_text(json.dumps(selected) + "\n")


def rewrite():
    package, upstream_version, version, directory = sys.argv[2:]
    root = Path(directory)
    control = root / "DEBIAN/control"
    row = fields(control.read_text())
    if (row.get("Package"), row.get("Version"), row.get("Architecture")) != (
            package, upstream_version, "all"):
        raise SystemExit(f"Incorrect downloaded help package metadata: {package}")
    expected = "" if package == "gimp-help-common" else f"gimp-help-common (= {upstream_version})"
    if row.get("Depends", "") != expected:
        raise SystemExit(f"Unexpected downloaded help dependencies: {package}")
    # These four packages already ship the documentation symlinks themselves.
    # Their legacy postinst migration scripts are unnecessary for this repack.
    postinst = root / "DEBIAN/postinst"
    if postinst.exists() and package in {"gimp-help-de", "gimp-help-en", "gimp-help-fr", "gimp-help-sv"}:
        postinst.unlink()
    allowed_control = {"control", "md5sums"}
    if any(path.name not in allowed_control for path in (root / "DEBIAN").iterdir()):
        raise SystemExit(f"Unexpected maintainer files in help package: {package}")
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if relative.parts[0] == "DEBIAN":
            continue
        if path.is_symlink():
            # Upstream manuals may share assets through relative links.
            target = os.readlink(path)
            resolved = Path(os.path.normpath(path.parent / target))
            if target.startswith("/") or not resolved.is_relative_to(root):
                raise SystemExit(f"Unsafe help link: {relative}")
        elif path.is_file():
            if not str(relative).startswith(("usr/share/gimp/3.0/help/", "usr/share/doc/",
                                             "usr/share/doc-base/", "usr/share/lintian/")):
                raise SystemExit(f"Unexpected help payload path: {relative}")
            with path.open("rb") as stream:
                if stream.read(4) == b"\x7fELF":
                    raise SystemExit(f"Unexpected executable in help package: {relative}")
        elif not path.is_dir():
            raise SystemExit(f"Unexpected help file type: {relative}")
    if package == "gimp-help-common":
        if not (root / "usr/share/doc/gimp-help-common/copyright").is_file():
            raise SystemExit("Missing Debian common-help copyright notice")
    elif not (root / "usr/share/gimp/3.0/help").is_dir():
        raise SystemExit(f"Missing GIMP help directory: {package}")
    row["Version"] = version
    row["Maintainer"] = os.environ["MAINTAINER"]
    row["X-Publisher-Stream"] = os.environ["PUBLISHER_STREAM"]
    row["X-Upstream-Version"] = upstream_version
    row["X-Build-Inputs-SHA256"] = os.environ["BUILD_INPUTS_SHA256"]
    if expected:
        row["Depends"] = f"gimp-help-common (= {version})"
    size = subprocess.check_output(
        ["du", "--summarize", "--block-size=1024", "--exclude=DEBIAN", root], text=True)
    row["Installed-Size"] = size.split()[0]
    control.write_text("".join(f"{key}: {value}\n" for key, value in row.items()))


if sys.argv[1] == "query":
    query()
elif sys.argv[1] == "rewrite":
    rewrite()
else:
    raise SystemExit(f"Unknown help metadata operation: {sys.argv[1]}")
