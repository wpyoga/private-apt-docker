"""Assign persistent Debian revisions while the runner holds the repository lock."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
IGNORED_DIRECTORIES = {"__pycache__", ".git", ".pytest_cache", "build"}


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".revision-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as output:
            json.dump(data, output, indent=4, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def fingerprint(adapter):
    inputs = []
    for path in sorted(adapter.rglob("*")):
        relative = path.relative_to(adapter)
        if any(part in IGNORED_DIRECTORIES for part in relative.parts[:-1]):
            continue
        if path.is_dir() and path.name in IGNORED_DIRECTORIES:
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise SystemExit(f"Recipe symlinks are unsupported: {path}")
        if path.is_file():
            inputs.append((f"adapter/{relative.as_posix()}", path))
    inputs.extend((name, ROOT / name) for name in ("Dockerfile", "lib/revisions.py"))
    records = [
        (name, path.stat().st_mode & 0o111, hashlib.sha256(path.read_bytes()).hexdigest())
        for name, path in inputs
    ]
    # Adapters may declare environment variables that affect their package output.
    environment = adapter / "revision-env"
    if environment.exists():
        for name in environment.read_text().splitlines():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise SystemExit(f"Invalid variable name in {environment}: {name}")
            records.append(("environment", name, os.environ.get(name)))
    return hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()


def load_state(adapter):
    package = (adapter / "package-name").read_text().strip()
    path = (
        Path(os.environ["REPO_DIR"]) / ".state/revisions"
        / os.environ["CODENAME"] / f"{package}.json"
    )
    if not path.exists():
        return package, path, {"schema": 1, "releases": {}}
    state = json.loads(path.read_text())
    if (
        not isinstance(state, dict)
        or state.get("schema") != 1
        or not isinstance(state.get("releases"), dict)
    ):
        raise SystemExit(f"Unsupported revision state: {path}")
    for record in state["releases"].values():
        if (
            not isinstance(record, dict)
            or type(record.get("revision")) is not int
            or record["revision"] < 1
            or not re.fullmatch(r"[a-f0-9]{64}", str(record.get("fingerprint", "")))
            or not isinstance(record.get("published"), list)
            or not all(isinstance(arch, str) for arch in record["published"])
        ):
            raise SystemExit(f"Invalid revision state: {path}")
    return package, path, state


def published_revisions(package, upstream_versions):
    result = subprocess.run(
        ["reprepro", "-b", os.environ["REPO_DIR"], "list", os.environ["CODENAME"], package],
        check=True, capture_output=True, text=True,
    )
    highest = dict.fromkeys(upstream_versions, 0)
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 3 or fields[1] != package:
            raise SystemExit(f"Unexpected reprepro list output: {line}")
        upstream, separator, revision = fields[2].rpartition("-")
        if upstream in highest:
            if not separator or not re.fullmatch(r"[1-9][0-9]*", revision):
                raise SystemExit(f"Cannot migrate nonnumeric Debian revision: {fields[2]}")
            highest[upstream] = max(highest[upstream], int(revision))
    return highest


def resolve(adapter, targets_path):
    targets = [line.split("\t") for line in targets_path.read_text().splitlines()]
    if not targets:
        return
    package, state_path, state = load_state(adapter)
    recipe = fingerprint(adapter)
    highest = published_revisions(package, {version for version, _ in targets})
    versions = {}
    for upstream, published_revision in highest.items():
        record = state["releases"].get(upstream)
        if (
            record is None
            or record["fingerprint"] != recipe
            or record["revision"] < published_revision
        ):
            revision = max(published_revision, record["revision"] if record else 0) + 1
            record = {"revision": revision, "fingerprint": recipe, "published": []}
            state["releases"][upstream] = record
        versions[upstream] = f"{upstream}-{record['revision']}"

    # Reserve before building: unchanged retries reuse the same version even if
    # no architecture has published yet or the process dies during publication.
    atomic_json(state_path, state)
    targets_path.write_text("".join(
        f"{versions[upstream]}\t{architecture}\n" for upstream, architecture in targets
    ))


def mark_published(adapter, version, architecture):
    _, path, state = load_state(adapter)
    upstream, revision = version.rsplit("-", 1)
    record = state["releases"].get(upstream)
    if record is None or str(record["revision"]) != revision:
        raise SystemExit(f"No reserved revision for {version}")
    if architecture not in record["published"]:
        record["published"].append(architecture)
        record["published"].sort()
        atomic_json(path, state)


def main():
    command, directory, *arguments = sys.argv[1:]
    adapter = Path(directory)
    if command == "resolve":
        resolve(adapter, Path(arguments[0]))
    elif command == "published":
        mark_published(adapter, *arguments)
    else:
        raise SystemExit(f"Unknown revision operation: {command}")


if __name__ == "__main__":
    main()
