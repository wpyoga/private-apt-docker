"""Check Orca's fixed Debian payload before extracting or changing permissions."""

from pathlib import PurePosixPath
import subprocess
import sys
import tarfile


def validate(package, architecture):
    machines = {"amd64": 62, "arm64": 183}
    executables = {"opt/Orca/orca-ide", "opt/Orca/chrome-sandbox"}
    required = executables | {
        "opt/Orca/resources/bin/orca-ide",
        "opt/Orca/resources/app.asar",
        "opt/Orca/LICENSE.electron.txt",
        "opt/Orca/LICENSES.chromium.html",
        "usr/share/applications/orca-ide.desktop",
        "usr/share/icons/hicolor/256x256/apps/orca-ide.png",
        "usr/share/doc/orca-ide/changelog.gz",
    }
    found = set()
    process = subprocess.Popen(["dpkg-deb", "--fsys-tarfile", package], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError(f"{package}: unsafe payload path {member.name}")
                # The verified upstream packages have only directories and regular
                # files. Reject new links or special files before recursive chmod.
                if not (member.isfile() or member.isdir()):
                    raise ValueError(f"{package}: unexpected payload type: {member.name}")
                name = str(path)
                if name not in required:
                    continue
                if name in found or not member.isfile() or member.size == 0:
                    raise ValueError(f"{package}: expected one nonempty regular file at {name}")
                found.add(name)
                if name in executables:
                    header = archive.extractfile(member).read(20)
                    if (len(header) != 20 or header[:6] != b"\x7fELF\x02\x01"
                            or int.from_bytes(header[18:20], "little") != machines[architecture]
                            or not member.mode & 0o111):
                        raise ValueError(f"{package}: invalid {architecture} executable {name}")
                elif name == "opt/Orca/resources/bin/orca-ide":
                    if not member.mode & 0o111:
                        raise ValueError(f"{package}: CLI shim is not executable: {name}")
        if found != required:
            raise ValueError(f"{package}: missing upstream paths: {sorted(required - found)}")
    finally:
        process.stdout.close()
        status = process.wait()
    if status:
        raise ValueError(f"{package}: cannot read upstream payload")


if __name__ == "__main__":
    validate(*sys.argv[1:])
