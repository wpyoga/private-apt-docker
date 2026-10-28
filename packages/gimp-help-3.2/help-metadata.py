"""Read pinned Debian manuals and validate their repackaged metadata."""

import json
import lzma
import os
from pathlib import Path
import re
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


def package_records(path):
    # Keep only one stanza in memory: the full sid index exceeds our memory limit.
    with lzma.open(path, "rt") as stream:
        record = []
        for line in stream:
            if line.strip():
                record.append(line)
            elif record:
                yield fields("".join(record))
                record = []
        if record:
            yield fields("".join(record))


def query():
    selected = {}
    names = {name for name in os.environ["BINARY_PACKAGES"].split() if name.startswith("gimp-help-")}
    for row in package_records(workspace / "Packages.xz"):
        name = row.get("Package")
        version = row.get("Version", "")
        if name not in names or not re.fullmatch(r"3\.2\.\d+-[0-9]+", version):
            continue
        if row.get("Architecture") != "all":
            raise SystemExit(f"Unexpected help architecture: {name}")
        if not re.fullmatch(r"[0-9a-f]{64}", row.get("SHA256", "")):
            raise SystemExit(f"Invalid help checksum: {name}")
        if row.get("Filename") != f"pool/main/g/gimp-help/{name}_{version}_all.deb":
            raise SystemExit(f"Unexpected help filename: {name}")
        previous = selected.get(name)
        if previous and previous != row:
            raise SystemExit(f"Ambiguous help release: {name}")
        selected[name] = row

    if set(selected) != names:
        raise SystemExit(f"Missing GIMP 3.2 help packages: {sorted(names - set(selected))}")
    versions = {row["Version"] for row in selected.values()}
    if len(versions) != 1:
        raise SystemExit(f"Inconsistent help versions: {sorted(versions)}")
    upstream_version = versions.pop()
    # The epoch upgrades manuals previously numbered after the application.
    version = "1:" + upstream_version.replace("-", "+deb")
    (workspace / "help-assets.json").write_text(json.dumps(selected) + "\n")
    manifest = "".join(
        f"{name}|{row['Version']}|{row['SHA256']}|{row['Filename']}\n"
        for name, row in sorted(selected.items())
    )
    (workspace / "help-assets").write_text(manifest)
    (workspace / "targets.tsv").write_text("".join(
        f"{version}\t{architecture}\n"
        for architecture in os.environ["ARCHES"].split()
    ))


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



if sys.argv[1] == "query":
    query()
elif sys.argv[1] == "rewrite":
    rewrite()
else:
    raise SystemExit(f"Unknown help metadata operation: {sys.argv[1]}")
