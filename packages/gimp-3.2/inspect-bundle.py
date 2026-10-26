"""Inspect AppImage data and native payloads without executing target code."""

import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys


architecture = os.environ["ARCHITECTURE"]
machine = {"amd64": 62, "arm64": 183}[architecture]


def fail(message):
    raise SystemExit(f"[gimp-3.2] {architecture}: {message}")


def elf_header(path):
    with path.open("rb") as stream:
        data = stream.read(64)
    if len(data) != 64 or data[:6] != b"\x7fELF\x02\x01":
        fail(f"Expected little-endian ELF64: {path}")
    if struct.unpack_from("<H", data, 18)[0] != machine:
        fail(f"Unexpected ELF architecture in {path}")
    return data


def appimage_offset(path):
    header = elf_header(path)
    if header[8:11] != b"AI\x02":
        fail(f"Expected a type-2 AppImage: {path}")
    start = struct.unpack_from("<Q", header, 40)[0]
    size, count = struct.unpack_from("<HH", header, 58)
    end = start + size * count
    if size != 64 or count == 0 or end > path.stat().st_size:
        fail(f"Unexpected AppImage ELF section table: {path}")
    # SquashFS follows the runtime ELF, not an arbitrary embedded 'hsqs' string.
    with path.open("rb") as stream:
        stream.seek(start)
        for _ in range(count):
            section = stream.read(size)
            kind = struct.unpack_from("<I", section, 4)[0]
            offset, length = struct.unpack_from("<QQ", section, 24)
            if kind != 8:  # SHT_NOBITS has no file-backed data.
                end = max(end, offset + length)
        stream.seek(end)
        if stream.read(4) != b"hsqs":
            fail(f"Missing SquashFS at runtime boundary {end}: {path}")
    print(end)


def check_tree(path, boundary):
    entries = [path]
    if path.is_dir() and not path.is_symlink():
        entries.extend(path.rglob("*"))
    for entry in entries:
        mode = entry.lstat().st_mode
        if stat.S_ISLNK(mode):
            target = os.readlink(entry)
            if target.startswith("/"):
                fail(f"Absolute payload link: {entry} -> {target}")
            try:
                resolved = entry.resolve(strict=True)
            except (OSError, RuntimeError) as error:
                fail(f"Broken payload link: {entry}: {error}")
            if not resolved.is_relative_to(boundary.resolve()):
                fail(f"Payload link escapes its directory: {entry} -> {target}")
        elif not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            fail(f"Unsupported payload file type: {entry}")
        if mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
            fail(f"Unexpected special permission bits: {entry}")


def required(root, relative, directory=False):
    path = root / relative
    if (not path.exists() or path.is_symlink()
            or (directory and not path.is_dir())
            or (not directory and not path.is_file())):
        fail(f"Missing or unexpected required path: {relative}")
    if not path.resolve().is_relative_to(root.resolve()):
        fail(f"Required path escapes source: {relative}")
    check_tree(path, root)
    return path


def metadata_version(root, relative):
    path = required(root, relative)
    match = re.search(r"^Version:\s*(\d+\.\d+\.\d+)\s*$", path.read_text(), re.M)
    if not match:
        fail(f"Missing release version in {relative}")
    return match[1]


def check_source():
    root = Path(os.environ["SOURCE_USR"])
    if root.is_symlink() or not root.is_dir():
        fail(f"Missing real usr directory: {root}")
    library = "lib/" + os.environ["MULTIARCH"]
    files = [
        "bin/gimp-3.2", "bin/gimp-console-3.2", "bin/gimp-script-fu-interpreter-3.0",
        "libexec/gimp-debug-tool-3.2", "etc/gimp/3.0/gimprc",
        "share/applications/org.gimp.GIMP.Stable.desktop",
        "share/metainfo/org.gimp.GIMP.Stable.appdata.xml",
    ]
    files += [f"{library}/girepository-1.0/{name}.typelib"
              for name in ("Gimp-3.0", "GimpUi-3.0", "Babl-0.1", "Gegl-0.4")]
    for relative in files:
        required(root, relative)
    for relative in (
        f"{library}/gimp/3.0", f"{library}/babl-0.1", f"{library}/gegl-0.4",
        "etc/gimp", "share/gimp/3.0", "share/icons", "share/locale",
    ):
        required(root, relative, directory=True)
    versions = {}
    for name, filename in (("gimp", "gimp-3.0.pc"), ("babl", "babl-0.1.pc"),
                           ("gegl", "gegl-0.4.pc")):
        versions[name] = metadata_version(root, f"{library}/pkgconfig/{filename}")
    if versions["gimp"] != os.environ["UPSTREAM_VERSION"]:
        fail(f"GIMP metadata version {versions['gimp']} does not match selected version")
    for name, minimum in (("babl", "0.1.116"), ("gegl", "0.4.66")):
        if subprocess.run(["dpkg", "--compare-versions", versions[name], "lt", minimum]).returncode == 0:
            fail(f"Bundled {name} {versions[name]} is below required {minimum}")
    for pattern in ("libgimp*.so*", "libbabl*.so*", "libgegl*.so*"):
        matches = list((root / library).glob(pattern))
        if not matches:
            fail(f"Missing required library family: {library}/{pattern}")
        for path in matches:
            check_tree(path, root)
    for name in ("libgimp-3.0.so.0", "libbabl-0.1.so.0", "libgegl-0.4.so.0"):
        if not (root / library / name).is_file():
            fail(f"Missing required library: {library}/{name}")
    report = Path(os.environ["WORKSPACE"]) / f"bundle-versions-{architecture}.json"
    report.write_text(json.dumps(versions) + "\n")


def check_staged():
    root = Path(os.environ["STAGING_DIR"])
    adapter = Path(os.environ["ADAPTER_DIR"])
    providers = {line.split("\t")[0] for line in
                 (adapter / "runtime-libraries.tsv").read_text().splitlines()}
    own = set()
    dependencies = []
    elf_paths = []
    count = 0
    for package in root.iterdir():
        check_tree(package, package)
        for path in package.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            with path.open("rb") as stream:
                if stream.read(4) != b"\x7fELF":
                    continue
            elf_header(path)
            elf_paths.append(path)
            dynamic = subprocess.check_output(["readelf", "--dynamic", "--wide", path], text=True)
            own.update(re.findall(r"\(SONAME\).*\[([^]]+)\]", dynamic))
            dependencies.extend((path, name) for name in
                                re.findall(r"\(NEEDED\).*\[([^]]+)\]", dynamic))
            count += 1
    loader = {"amd64": "ld-linux-x86-64.so.2", "arm64": "ld-linux-aarch64.so.1"}[architecture]
    for path, name in dependencies:
        if name not in own and name not in providers and name != loader:
            fail(f"Unknown external dependency {name} in {path}; update the adapter deliberately")
    manifest = Path(os.environ["WORKSPACE"]) / f"elf-{architecture}.paths0"
    manifest.write_bytes(b"".join(os.fsencode(path) + b"\0" for path in elf_paths))
    print(f"Validated {count} {architecture} ELF objects and declared dependencies")


if sys.argv[1] == "offset":
    appimage_offset(Path(sys.argv[2]))
elif sys.argv[1] == "source":
    check_source()
elif sys.argv[1] == "staged":
    check_staged()
else:
    fail(f"Unknown inspection operation: {sys.argv[1]}")
