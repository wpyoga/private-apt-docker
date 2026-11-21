"""Inspect the fixed upstream payload without extracting or running its code."""

from pathlib import PurePosixPath
import subprocess
import sys
import tarfile

package, architecture = sys.argv[1:]
machines = {"amd64": 62, "arm64": 183}
executables = {
    "opt/Ovis/ovis", "opt/Ovis/chrome-sandbox",
    "opt/Ovis/resources/ovis/bin/bun", "opt/Ovis/resources/ovis/bin/herdr-core",
    "opt/Ovis/resources/ovis/server/bin/ovis-pty-sidecar",
}
required = executables | {
    "opt/Ovis/resources/ovis/LICENSE",
    "opt/Ovis/resources/ovis/THIRD_PARTY_NOTICES.md",
    "opt/Ovis/resources/ovis/licenses/bun/LICENSE.md",
    "opt/Ovis/resources/ovis/licenses/herdr-core/LICENSE",
    "opt/Ovis/resources/ovis/licenses/herdr-core/THIRD-PARTY-NOTICES",

    "opt/Ovis/resources/app.asar", "opt/Ovis/resources/apparmor-profile",
    "opt/Ovis/resources/ovis/server/dist/index.html",
    "opt/Ovis/resources/ovis/server/dist/THIRD_PARTY_NOTICES.md",
    "opt/Ovis/LICENSE.electron.txt", "opt/Ovis/LICENSES.chromium.html",
    "usr/share/applications/ovis.desktop",
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
            if name in found or not member.isfile() or member.size == 0:
                raise ValueError(f"{package}: expected one regular file at {name}")
            found.add(name)
            if name in executables:
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
