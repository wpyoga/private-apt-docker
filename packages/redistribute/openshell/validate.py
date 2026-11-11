"""Inspect the fixed upstream payload without extracting or running its code."""

from pathlib import PurePosixPath
import subprocess
import sys
import tarfile

package, architecture = sys.argv[1:]
machines = {"amd64": 62, "arm64": 183}
required = {
    "usr/bin/openshell", "usr/bin/openshell-gateway", "usr/bin/openshell-prover",
    "usr/libexec/openshell/openshell-driver-vm",
    "usr/lib/systemd/user/openshell-gateway.service",
    "usr/share/doc/openshell/copyright",
}
found = set()
process = subprocess.Popen(["dpkg-deb", "--fsys-tarfile", package], stdout=subprocess.PIPE)
try:
    with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"{package}: unsafe payload path {member.name}")
            name = str(path)
            if name not in required:
                continue
            if name in found or not member.isfile():
                raise ValueError(f"{package}: expected one regular file at {name}")
            found.add(name)
            if name.startswith(("usr/bin/", "usr/libexec/")):
                header = archive.extractfile(member).read(20)
                if (len(header) != 20 or header[:6] != b"\x7fELF\x02\x01"
                        or int.from_bytes(header[18:20], "little") != machines[architecture]
                        or not member.mode & 0o111):
                    raise ValueError(f"{package}: invalid {architecture} executable {name}")
    if found != required:
        raise ValueError(f"{package}: missing upstream paths: {sorted(required - found)}")
finally:
    process.stdout.close()
    status = process.wait()
if status:
    raise SystemExit(f"{package}: cannot read upstream payload")
