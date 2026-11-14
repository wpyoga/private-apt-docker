"""Validate the release tarball against its reviewed Git tree before extraction."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import tarfile


def git_hash(kind, data):
    header = f"{kind} {len(data)}\0".encode()
    return hashlib.sha1(header + data).digest()


def tree_hash(files):
    entries = []
    for name, value in files.items():
        if isinstance(value, dict):
            mode, digest, sort_name = b"40000", tree_hash(value), name + "/"
        else:
            mode, data = value
            digest, sort_name = git_hash("blob", data), name
        entry = mode + b" " + name.encode() + b"\0" + digest
        entries.append((sort_name.encode(), entry))
    return git_hash("tree", b"".join(entry for _, entry in sorted(entries)))


def validate(archive_path, metadata):
    expected_root = f"diffofdiffs-{metadata['version']}"
    files = {}
    seen = set()
    version = None
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive:
            name = member.name.rstrip("/")
            parts = PurePosixPath(name).parts
            if (not parts or parts[0] != expected_root or ".." in parts
                    or name != "/".join(parts) or name in seen):
                raise ValueError(f"diffofdiffs: unexpected or duplicate archive path {member.name}")
            seen.add(name)
            if member.isdir():
                continue
            if not member.isfile() or member.mode & 0o7000 or len(parts) < 2:
                raise ValueError(f"diffofdiffs: unsupported archive entry {member.name}")
            data = archive.extractfile(member).read()
            directory = files
            for part in parts[1:-1]:
                directory = directory.setdefault(part, {})
                if not isinstance(directory, dict):
                    raise ValueError(f"diffofdiffs: file used as directory {member.name}")
            mode = b"100755" if member.mode & 0o111 else b"100644"
            if parts[-1] in directory:
                raise ValueError(f"diffofdiffs: conflicting archive path {member.name}")
            directory[parts[-1]] = (mode, data)
            if parts[1:] == ("VERSION",):
                version = data.decode().strip()
    if version != metadata["version"]:
        raise ValueError(f"diffofdiffs: VERSION expected {metadata['version']}, got {version!r}")
    actual = tree_hash(files).hex()
    if actual != metadata["tree"]:
        raise ValueError(f"diffofdiffs: source tree checksum expected {metadata['tree']}, got {actual}")


if __name__ == "__main__":
    try:
        archive_path = Path(sys.argv[1])
        metadata = json.loads(Path(sys.argv[2]).read_text())
        validate(archive_path, metadata)
        if len(sys.argv) == 4:
            with tarfile.open(archive_path, "r:gz") as archive:
                archive.extractall(sys.argv[3], filter="data")
        print(hashlib.sha256(archive_path.read_bytes()).hexdigest())
    except (ValueError, OSError, tarfile.TarError) as error:
        raise SystemExit(str(error))
