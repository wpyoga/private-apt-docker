"""Validate Cromite's fixed bundle and report dependencies without running its code."""

import argparse
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import tarfile


BUNDLED_LIBRARIES = {
    "libvk_swiftshader.so", "libvulkan.so.1", "libEGL.so", "libGLESv2.so",
    "libqt5_shim.so", "libqt6_shim.so",
}
REQUIRED_FILES = {
    "chrome", "chrome_sandbox", "chrome_crashpad_handler", "chrome-wrapper",
    "chrome_100_percent.pak", "chrome_200_percent.pak", "resources.pak",
    "icudtl.dat", "snapshot_blob.bin", "product_logo_48.png", "locales/en-US.pak",
} | BUNDLED_LIBRARIES


def check_archive(path):
    files = set()
    seen = set()
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or not name.parts:
                raise ValueError(f"Unsafe archive path: {member.name}")
            if name.parts[0] != "chrome-lin":
                raise ValueError(f"Unexpected archive root: {member.name}; expected chrome-lin/")
            if name in seen:
                raise ValueError(f"Duplicate archive path: {member.name}")
            seen.add(name)
            # The official bundle contains no links or special files. Reject
            # them before extraction, so later reads cannot follow a link.
            if not member.isfile() and not member.isdir():
                raise ValueError(f"Unsupported archive entry type: {member.name}")
            if member.isfile():
                files.add(str(name.relative_to("chrome-lin")))
    missing = REQUIRED_FILES - files
    if missing:
        raise ValueError(f"Missing bundle file: {sorted(missing)[0]}")
    unexpected = {name for name in files - REQUIRED_FILES
                  if not re.fullmatch(r"locales/[A-Za-z0-9_-]+\.pak(?:\.info)?", name)}
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

    dependencies = set()
    binaries = ["chrome", "chrome_sandbox", "chrome_crashpad_handler"]
    for name in binaries + sorted(BUNDLED_LIBRARIES):
        path = root / name
        if not path.stat().st_mode & 0o111:
            raise ValueError(f"Missing executable permission: {path}")
        needed = check_elf(path, architecture)
        if not needed:
            raise ValueError(f"Missing ELF dependencies: {path}")
        for soname in sorted(needed):
            if soname in BUNDLED_LIBRARIES:
                continue
            if soname not in mapping:
                raise ValueError(f"Unknown library {soname} required by {path}")
            # Qt shims are optional integrations loaded only on Qt desktops.
            if not name.startswith("libqt"):
                dependencies.add(mapping[soname])
        check_versions(path)
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
        parser.exit(1, f"[cromite] {error}\n")


if __name__ == "__main__":
    main()
