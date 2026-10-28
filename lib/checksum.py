"""Print a checksum of a stream's packaging inputs."""

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(os.environ["FRAMEWORK_DIR"])
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

    declaration = adapter / "helper-inputs"
    if declaration.exists():
        seen = set()
        for line in declaration.read_text().splitlines():
            name = line.strip()
            if not name or name.startswith("#"):
                continue
            relative = Path(name)
            path = ROOT / "lib" / relative
            if (relative.is_absolute() or ".." in relative.parts or name in seen
                    or not path.is_file()
                    or any(part.is_symlink() for part in (path, *path.parents))):
                raise SystemExit(f"Invalid shared helper input: {name}")
            seen.add(name)
            inputs.append((f"lib/{name}", path))
        inputs.sort(key=lambda item: item[0])

    inputs.append(("Dockerfile", ROOT / "Dockerfile"))

    records = []
    for name, path in inputs:
        executable_permissions = path.stat().st_mode & 0o111
        contents_checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append((name, executable_permissions, contents_checksum))

    records.append(("environment", "MAINTAINER", os.environ["MAINTAINER"]))
    return hashlib.sha256(json.dumps(records).encode()).hexdigest()


if __name__ == "__main__":
    print(checksum(Path(os.environ["ADAPTER_DIR"])))
