"""Validate Zed's fixed bundle and report dependencies without running its code."""

import argparse
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import tarfile


BUNDLED_LIBRARIES = {
    "libXdmcp.so.6", "libXau.so.6", "libxcb.so.1", "libxcb-xkb.so.1",
    "libxkbcommon-x11.so.0", "libstdc++.so.6", "libbsd.so.0",
    "libX11-xcb.so.1", "libxkbcommon.so.0",
}
REQUIRED_FILES = {
    "bin/zed", "libexec/zed-editor", "licenses.md",
    "share/applications/dev.zed.Zed.desktop",
    "share/icons/hicolor/512x512/apps/zed.png",
    "share/icons/hicolor/1024x1024/apps/zed.png",
} | {f"lib/{name}" for name in BUNDLED_LIBRARIES}


def check_archive(path):
    files = set()
    seen = set()
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or not name.parts:
                raise ValueError(f"Unsafe archive path: {member.name}")
            if name.parts[0] != "zed.app":
                raise ValueError(f"Unexpected archive root: {member.name}; expected zed.app/")
            if name in seen:
                raise ValueError(f"Duplicate archive path: {member.name}")
            seen.add(name)
            # The official bundle contains no links or special files. Reject
            # them before extraction, so later reads cannot follow a link.
            if not member.isfile() and not member.isdir():
                raise ValueError(f"Unsupported archive entry type: {member.name}")
            if member.isfile():
                files.add(str(name.relative_to("zed.app")))
    missing = REQUIRED_FILES - files
    if missing:
        raise ValueError(f"Missing bundle file: {sorted(missing)[0]}")
    unexpected = files - REQUIRED_FILES
    if unexpected:
        raise ValueError(f"Unexpected bundle file: {sorted(unexpected)[0]}")


def readelf(path, option):
    return subprocess.check_output(
        ["readelf", "--wide", option, str(path)], text=True
    )


def check_elf(path, architecture):
    with path.open("rb") as source:
        header = source.read(20)
    if header[:6] != b"\x7fELF\x02\x01" or len(header) != 20:
        raise ValueError(f"Expected a little-endian ELF64 file: {path}")
    machine = struct.unpack_from("<H", header, 18)[0]
    expected = {"amd64": 62, "arm64": 183}[architecture]
    if machine != expected:
        raise ValueError(f"Wrong ELF architecture in {path}: expected {architecture}, got {machine}")
    dynamic = readelf(path, "--dynamic")
    needed = set(re.findall(r"\(NEEDED\).*\[(.*?)\]", dynamic))
    return needed


def check_versions(path):
    # These ceilings match the Debian 13 runtime declared in control metadata.
    # A new toolchain baseline needs a deliberate compatibility review.
    limits = {"GLIBC": (2, 41), "GLIBCXX": (3, 4, 33), "CXXABI": (1, 3, 15)}
    versions = readelf(path, "--version-info")
    for family, version in re.findall(r"Name: (GLIBC|GLIBCXX|CXXABI)_([0-9.]+)", versions):
        if tuple(map(int, version.split("."))) > limits[family]:
            raise ValueError(f"Unsupported Debian 13 symbol version {family}_{version} in {path}")


def inspect_tree(root, architecture, dependency_file):
    mapping = {}
    for line in dependency_file.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            soname, dependency = line.split("|", 1)
            mapping[soname] = dependency

    # Discarded libraries are still checked for changed architecture or imports,
    # but their dependencies must not leak into the final package's Depends.
    binaries = [root / "bin/zed", root / "libexec/zed-editor"]
    dependencies = set()
    for path in binaries + [root / "lib" / name for name in sorted(BUNDLED_LIBRARIES)]:
        needed = check_elf(path, architecture)
        if path in binaries and not needed:
            raise ValueError(f"Missing ELF dependencies: {path}")
        for soname in sorted(needed):
            if soname not in mapping:
                raise ValueError(f"Unknown library {soname} required by {path}")
            if path in binaries:
                dependencies.add(mapping[soname])
        if path in binaries:
            check_versions(path)

    desktop = (root / "share/applications/dev.zed.Zed.desktop").read_text()
    for line in ("TryExec=zed", "Exec=zed %U", "Exec=zed --new %U", "Icon=zed"):
        if line not in desktop.splitlines():
            raise ValueError(f"Unexpected desktop entry: missing {line}")

    print(", ".join(sorted(dependencies)))


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    archive = commands.add_parser("archive")
    archive.add_argument("path", type=Path)
    tree = commands.add_parser("tree")
    tree.add_argument("root", type=Path)
    tree.add_argument("architecture", choices=("amd64", "arm64"))
    tree.add_argument("dependencies", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "archive":
            check_archive(args.path)
        else:
            inspect_tree(args.root, args.architecture, args.dependencies)
    except (OSError, ValueError, tarfile.TarError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"[zed] {error}\n")


if __name__ == "__main__":
    main()
