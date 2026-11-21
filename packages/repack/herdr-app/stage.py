"""Check fixed archive paths and stage files without executing upstream code."""

from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile


archive_path, architecture, destination = sys.argv[1:]
destination = Path(destination)
paths = {
    'herdr-app/herdr-app': 'usr/bin/herdr-app',
    'herdr-app/LICENSE': 'usr/share/doc/herdr-app/copyright',
    'herdr-app/THIRD-PARTY-NOTICES': 'usr/share/doc/herdr-app/THIRD-PARTY-NOTICES',
    'herdr-app/herdr-app.svg': 'usr/share/icons/hicolor/scalable/apps/herdr-app.svg',
}
binary_name = 'herdr-app/herdr-app'
found = set()
with tarfile.open(archive_path, "r:gz") as archive:
    for member in archive:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"{archive_path}: unsafe path: {member.name}")
        name = str(path)
        if member.isdir() and name in {'herdr-app'}:
            continue
        if name not in paths or not member.isfile() or member.size == 0 or name in found:
            raise ValueError(f"{archive_path}: unexpected file or type: {member.name}")
        found.add(name)
        target = destination / paths[name]
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.extractfile(member) as source, target.open("wb") as output:
            shutil.copyfileobj(source, output)
        target.chmod(0o755 if name == binary_name else 0o644)
        if name == binary_name and not member.mode & 0o111:
            raise ValueError(f"{archive_path}: binary is not executable: {name}")
if found != paths.keys():
    raise ValueError(f"{archive_path}: missing upstream paths: {sorted(paths.keys() - found)}")

binary = destination / paths[binary_name]
with binary.open("rb") as source:
    header = source.read(20)
machine = {"amd64": 62, "arm64": 183}[architecture]
if (len(header) != 20 or header[:6] != b"\x7fELF\x02\x01"
        or int.from_bytes(header[18:20], "little") != machine):
    raise ValueError(f"{archive_path}: invalid {architecture} ELF binary")
dynamic = subprocess.check_output(["readelf", "--dynamic", str(binary)], text=True)
needed = set(re.findall(r"\(NEEDED\).*\[(.*?)\]", dynamic))
allowed = {"libxcb.so.1", "libxkbcommon.so.0", "libfontconfig.so.1",
           "libgcc_s.so.1", "libm.so.6", "libc.so.6"}
if architecture == "amd64":
    allowed.add("ld-linux-x86-64.so.2")
if needed - allowed:
    raise ValueError(f"{archive_path}: unknown shared libraries: {sorted(needed - allowed)}")
versions = subprocess.check_output(["readelf", "--version-info", str(binary)], text=True)
for version in re.findall(r"Name: GLIBC_(\d+\.\d+)", versions):
    if tuple(map(int, version.split("."))) > (2, 41):
        raise ValueError(f"{archive_path}: GLIBC_{version} exceeds Debian 13")
