"""Print a checksum of a stream's declared packaging inputs."""

import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
IGNORED_DIRECTORIES = {"__pycache__", ".git", ".pytest_cache", "build"}


def checksum(adapter):
    inputs = []
    for path in sorted(adapter.rglob("*")):
        relative = path.relative_to(adapter)
        if any(part in IGNORED_DIRECTORIES for part in relative.parts[:-1]):
            continue
        if path.is_dir() and path.name in IGNORED_DIRECTORIES:
            continue
        if relative == Path("stale-after-days") or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise SystemExit(f"Recipe symlinks are unsupported: {path}")
        if path.is_file():
            inputs.append((f"adapter/{relative.as_posix()}", path))
    inputs.append(("Dockerfile", ROOT / "Dockerfile"))
    records = []
    for name, path in inputs:
        executable_permissions = path.stat().st_mode & 0o111
        contents_checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append((name, executable_permissions, contents_checksum))
    environment = adapter / "revision-env"
    if environment.exists():
        for name in environment.read_text().splitlines():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise SystemExit(f"Invalid variable name in {environment}: {name}")
            records.append(("environment", name, os.environ.get(name)))
    return hashlib.sha256(json.dumps(records).encode()).hexdigest()


if __name__ == "__main__":
    print(checksum(Path(sys.argv[1])))
