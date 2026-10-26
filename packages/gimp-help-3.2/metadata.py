"""Select and validate Debian's architecture-independent GIMP 3.2 manuals."""

import json
import lzma
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
    names = set(os.environ["BINARY_PACKAGES"].split())
    selected = {}
    with lzma.open(workspace / "Packages.xz", "rt") as stream:
        # Debian's index is large; retain only one paragraph at a time.
        paragraph = []
        for line in stream:
            if line.strip():
                paragraph.append(line)
                continue
            row = fields("".join(paragraph))
            paragraph = []
            name = row.get("Package")
            if name not in names or not re.fullmatch(r"3\.2\.\d+-[0-9]+", row.get("Version", "")):
                continue
            if name in selected:
                raise SystemExit(f"Duplicate Debian help package: {name}")
            filename = row.get("Filename", "")
            if (row.get("Architecture") != "all"
                    or not re.fullmatch(r"[0-9a-f]{64}", row.get("SHA256", ""))
                    or filename != f"pool/main/g/gimp-help/{name}_{row['Version']}_all.deb"):
                raise SystemExit(f"Unexpected Debian help metadata for {name}")
            selected[name] = row
    if set(selected) != names:
        raise SystemExit(f"Missing GIMP 3.2 help packages in sid: {sorted(names - set(selected))}")
    versions = {row["Version"] for row in selected.values()}
    if len(versions) != 1:
        raise SystemExit(f"Debian help packages have inconsistent versions: {sorted(versions)}")
    version = versions.pop()
    for name, row in selected.items():
        expected = "" if name == "gimp-help-common" else f"gimp-help-common (= {version})"
        if row.get("Depends", "") != expected:
            raise SystemExit(f"Changed help dependencies for {name}: {row.get('Depends')}")
    (workspace / "help-assets.json").write_text(json.dumps(selected) + "\n")
    (workspace / "targets.tsv").write_text("".join(
        f"{version}\t{arch}\n" for arch in os.environ["ARCHES"].split()))
    # The Debian build timestamp is checked again after downloading the package.
    # Do not invent a release date from today's metadata-query time.


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
    if not (root / "usr/share/gimp/3.0/help").is_dir():
        raise SystemExit(f"Missing GIMP help directory: {package}")
    row["Version"] = version
    row["Maintainer"] = os.environ["MAINTAINER"]
    row["X-Publisher-Stream"] = os.environ["PUBLISHER_STREAM"]
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
