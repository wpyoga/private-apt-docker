"""Preserve upstream Debian packages and keep import provenance outside their bytes."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def control(path):
    output = subprocess.check_output(["dpkg-deb", "--field", str(path)], text=True)
    return dict(line.split(": ", 1) for line in output.splitlines()
                if line and not line[0].isspace() and ": " in line)


def imports():
    path = Path(os.environ["WORKSPACE"]) / "imports.json"
    entries = json.loads(path.read_text())
    if not isinstance(entries, list):
        raise ValueError(f"{path}: expected an array of import records")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: invalid import record")
        for field in ("package", "version", "architecture", "url", "sha256"):
            if not isinstance(entry.get(field), str) or not entry[field]:
                raise ValueError(f"{path}: missing import field {field}")
        if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", entry["package"]):
            raise ValueError(f"{path}: invalid package {entry['package']}")
        if not re.fullmatch(r"[0-9][A-Za-z0-9.+:~\-]*", entry["version"]):
            raise ValueError(f"{path}: invalid version {entry['version']}")
        subprocess.run(["dpkg", "--validate-version", entry["version"]], check=True)
        if entry["architecture"] not in ("amd64", "arm64", "all"):
            raise ValueError(f"{path}: invalid architecture {entry['architecture']}")
        if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise ValueError(f"{path}: invalid SHA256 for {entry['package']}")
        if not entry["url"].startswith("https://") or any(c.isspace() for c in entry["url"]):
            raise ValueError(f"{path}: invalid URL for {entry['package']}")
        identity = (entry["package"], entry["version"], entry["architecture"])
        if identity in seen:
            raise ValueError(f"{path}: duplicate import {identity}")
        seen.add(identity)
    return entries


def filename(entry):
    return f"{entry['package']}_{entry['version']}_{entry['architecture']}.deb"


def record_path(package_path):
    repository = Path(os.environ["REPO_DIR"])
    relative = package_path.relative_to(repository / "pool/main")
    if len(relative.parts) != 2:
        raise ValueError(f"Unexpected imported package path: {package_path}")
    return repository / ".state/imports" / relative.parent / (relative.name + ".json")


def read_record(package_path):
    path = record_path(package_path)
    if not path.exists():
        return None
    record = json.loads(path.read_text())
    if record.get("sha256") != digest(package_path):
        raise ValueError(f"Import provenance digest mismatch: {package_path}")
    if record.get("stream") != package_path.parent.name:
        raise ValueError(f"Import provenance stream mismatch: {package_path}")
    return record


def selected_entries(entries, version, architecture):
    names = os.environ.get(f"BINARY_PACKAGES_{architecture.upper()}", "").split()
    names = names or os.environ["BINARY_PACKAGES"].split()
    selected = []
    for name in names:
        matches = [entry for entry in entries if entry["package"] == name
                   and entry["version"] == version
                   and entry["architecture"] in (architecture, "all")]
        if len(matches) != 1:
            raise ValueError(f"Expected one import for {name} {version} ({architecture})")
        selected.extend(matches)
    return selected


def resolve(targets):
    entries = imports()
    repository = Path(os.environ["REPO_DIR"])
    stream = os.environ["PUBLISHER_STREAM"]
    recipe = os.environ["BUILD_INPUTS_SHA256"]
    with (Path(os.environ["WORKSPACE"]) / "builds.tsv").open("w") as output:
        for version, architecture in targets:
            complete = True
            for entry in selected_entries(entries, version, architecture):
                path = repository / "pool/main" / stream / filename(entry)
                if not path.exists():
                    complete = False
                    continue
                if digest(path) != entry["sha256"]:
                    raise ValueError(f"Upstream changed bytes for {filename(entry)}; stored package preserved")
                record = read_record(path)
                if not record or record.get("recipe_sha256") != recipe or record.get("url") != entry["url"]:
                    complete = False
            output.write(f"{version}\t{architecture}\t{'complete' if complete else ''}\n")


def installed_size(path):
    # Estimate logical payload size without extracting or executing upstream files.
    process = subprocess.Popen(["dpkg-deb", "--fsys-tarfile", str(path)], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            size = sum(member.size for member in archive if member.isfile())
    finally:
        process.stdout.close()
        status = process.wait()
    if status:
        raise ValueError(f"Cannot read payload size: {path}")
    return (size + 1023) // 1024


def atomic_json(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            json.dump(record, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o644)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def store(version, architecture, output_directory):
    entries = selected_entries(imports(), version, architecture)
    if set(path.name for path in output_directory.iterdir()) != {filename(entry) for entry in entries}:
        raise ValueError("Import output must contain exactly the declared binary packages")
    repository = Path(os.environ["REPO_DIR"])
    stream = os.environ["PUBLISHER_STREAM"]
    pending = []
    for entry in entries:
        source = output_directory / filename(entry)
        if source.is_symlink() or not source.is_file() or digest(source) != entry["sha256"]:
            raise ValueError(f"Import SHA256 mismatch or invalid file: {source}")
        fields = control(source)
        for field, key in (("Package", "package"), ("Version", "version"), ("Architecture", "architecture")):
            if fields.get(field) != entry[key]:
                raise ValueError(f"{source}: unexpected {field}: {fields.get(field)}")
        # Compare every copy, including packages stored by another stream.
        for existing in (repository / "pool").rglob(f"{entry['package']}_*.deb"):
            existing_fields = control(existing)
            if all(existing_fields.get(field) == fields[field]
                   for field in ("Package", "Version", "Architecture")):
                if digest(existing) != entry["sha256"]:
                    raise ValueError(f"Conflicting bytes for {filename(entry)}: {existing}")
        destination = repository / "pool/main" / stream / filename(entry)
        record = {**entry, "stream": stream, "recipe_sha256": os.environ["BUILD_INPUTS_SHA256"],
                  "installed_size": installed_size(source)}
        pending.append((source, destination, record))

    # Validate the complete set before publishing anything. A record written before
    # its package is harmless; a failed import is retried under the repository lock.
    for source, destination, record in pending:
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(record_path(destination), record)
        if destination.exists():
            continue
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".package-", delete=False) as output:
                temporary = Path(output.name)
                with source.open("rb") as input_file:
                    shutil.copyfileobj(input_file, output)
                output.flush()
                os.fsync(output.fileno())
            temporary.chmod(0o644)
            os.link(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def enrich_index(path):
    paragraphs = []
    repository = Path(os.environ["REPO_DIR"])
    for paragraph in path.read_text().strip().split("\n\n"):
        if not paragraph:
            continue
        lines = paragraph.splitlines()
        fields = dict(line.split(": ", 1) for line in lines
                      if line and not line[0].isspace() and ": " in line)
        package_path = repository / fields["Filename"]
        record = read_record(package_path)
        if record is None and os.environ.get("REPOSITORY_MODE") == "redistribute":
            raise ValueError(f"Missing import provenance: {package_path}")
        if record is not None:
            additions = {"X-Publisher-Stream": record["stream"],
                         "X-Import-Recipe-SHA256": record["recipe_sha256"],
                         "X-Upstream-URL": record["url"],
                         "Installed-Size": str(record["installed_size"])}
            lines = [line for line in lines if line.split(":", 1)[0] not in additions]
            lines.extend(f"{key}: {value}" for key, value in additions.items())
        paragraphs.append("\n".join(lines))
    path.write_text("\n\n".join(paragraphs) + ("\n\n" if paragraphs else ""))


if __name__ == "__main__":
    try:
        if sys.argv[1] == "store":
            store(sys.argv[2], sys.argv[3], Path(sys.argv[4]))
        elif sys.argv[1] == "index":
            enrich_index(Path(sys.argv[2]))
        else:
            raise ValueError(f"Unknown redistribution action: {sys.argv[1]}")
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
