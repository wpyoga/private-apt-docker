"""Validate the fixed HTML archive layout before extracting it with tar."""

from pathlib import PurePosixPath
import sys
import tarfile


archive, version = sys.argv[1:]
prefix = f"gimp-api-docs-{version}"
with tarfile.open(archive) as stream:
    members = stream.getmembers()
    for member in members:
        path = PurePosixPath(member.name)
        if (path.is_absolute() or ".." in path.parts or not path.parts
                or path.parts[0] != prefix or not (member.isdir() or member.isfile())
                or member.mode & 0o7000):
            raise SystemExit(f"Unexpected API documentation archive member: {member.name}")
    names = {member.name for member in members if member.isfile()}
    if f"{prefix}/reference/libgimp-3.0/index.html" not in names:
        raise SystemExit(f"Missing generated libgimp HTML index in {archive}")
