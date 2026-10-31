"""Validate USBImager's fixed archive layout and ELF dependencies as data."""

import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile
import zipfile


resources = {
    "bin/usbimager",
    "share/applications/usbimager.desktop",
    "share/man/man8/usbimager.8.gz",
    *(f"share/icons/hicolor/{size}x{size}/apps/usbimager.png" for size in (16, 32, 64, 128)),
}


def check_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError(f"Unsafe archive path: {name}")


def check_deb(path):
    # Reject links and special files before extraction or any payload reads.
    for option in ("--fsys-tarfile", "--ctrl-tarfile"):
        process = subprocess.Popen(["dpkg-deb", option, str(path)], stdout=subprocess.PIPE)
        try:
            with tarfile.open(fileobj=process.stdout, mode="r|*") as archive:
                for member in archive:
                    check_path(member.name)
                    if not (member.isfile() or member.isdir()):
                        raise ValueError(f"Unsupported Debian archive entry: {member.name}")
        finally:
            process.stdout.close()
            status = process.wait()
        if status:
            raise ValueError(f"Cannot read Debian archive: {path}")


def extract_zip(path, destination):
    with zipfile.ZipFile(path) as archive:
        files = set()
        names = set()
        for member in archive.infolist():
            check_path(member.filename)
            if member.filename in names:
                raise ValueError(f"Duplicate ZIP entry: {member.filename}")
            names.add(member.filename)
            mode = member.external_attr >> 16
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError(f"Unsupported ZIP entry: {member.filename}")
            if not member.is_dir():
                files.add(member.filename)
            else:
                prefix = member.filename.rstrip("/") + "/"
                if not any(name.startswith(prefix) for name in resources):
                    raise ValueError(f"Unexpected ZIP directory: {member.filename}")
        if files != resources:
            raise ValueError(f"Unexpected ZIP layout; missing {sorted(resources - files)}, extra {sorted(files - resources)}")
        archive.extractall(destination)


def check_tree(root, architecture):
    for path in root.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError(f"Unsupported staged file type: {path}")
    for name in resources:
        path = root / "usr" / name
        if not path.is_file():
            raise ValueError(f"Missing required package file: usr/{name}")
    binary = root / "usr/bin/usbimager"
    environment = {**os.environ, "LC_ALL": "C"}
    header = subprocess.check_output(["readelf", "--file-header", str(binary)], env=environment, text=True)
    machine = {"amd64": "Advanced Micro Devices X86-64", "arm64": "AArch64"}[architecture]
    if not re.search(rf"Machine:\s+{re.escape(machine)}\s*$", header, re.MULTILINE) or "ELF64" not in header:
        raise ValueError(f"Wrong ELF architecture for {architecture}: {binary}")
    dynamic = subprocess.check_output(["readelf", "--dynamic", str(binary)], env=environment, text=True)
    needed = set(re.findall(r"\(NEEDED\).*\[(.*?)\]", dynamic))
    allowed = {"libc.so.6", "libX11.so.6"} if architecture == "arm64" else {
        "libc.so.6", "libgtk-3.so.0", "libgio-2.0.so.0", "libgobject-2.0.so.0",
        "libglib-2.0.so.0", "libudisks2.so.0",
    }
    if not needed or needed - allowed:
        raise ValueError(f"Unexpected ELF dependencies for {architecture}: {sorted(needed)}")
    if re.search(r"\((RPATH|RUNPATH)\)", dynamic):
        raise ValueError(f"Unexpected ELF library search path: {binary}")
    symbols = subprocess.check_output(["readelf", "--version-info", str(binary)], env=environment, text=True)
    for version in re.findall(r"GLIBC_([0-9]+\.[0-9]+(?:\.[0-9]+)?)", symbols):
        if tuple(map(int, version.split("."))) > (2, 41):
            raise ValueError(f"Unsupported GLIBC_{version} for Debian Trixie: {binary}")
    desktop = (root / "usr/share/applications/usbimager.desktop").read_text()
    for line in ("Type=Application", "Exec=/usr/bin/usbimager", "Icon=usbimager"):
        if line not in desktop.splitlines():
            raise ValueError(f"Unexpected desktop field: expected {line}")


try:
    command = sys.argv[1]
    if command == "deb":
        check_deb(Path(sys.argv[2]))
    elif command == "zip":
        extract_zip(Path(sys.argv[2]), Path(sys.argv[3]))
    elif command == "tree":
        check_tree(Path(sys.argv[2]), sys.argv[3])
    else:
        raise ValueError(f"Unknown validation command: {command}")
except (ValueError, OSError, tarfile.TarError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
    raise SystemExit(f"[usbimager] {error}")
