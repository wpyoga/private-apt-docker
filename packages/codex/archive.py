"""Safely extract and validate the upstream Codex package layout."""

import json
import pathlib
import sys
import tarfile


def main():
    archive, destination, version = sys.argv[1:]
    root = pathlib.Path(destination)
    with tarfile.open(archive, "r:gz") as source:
        source.extractall(root, filter="data")

    if not (root / "bin/codex").is_file():
        directories = [path for path in root.iterdir() if path.is_dir()]
        if len(directories) != 1 or not (directories[0] / "bin/codex").is_file():
            raise SystemExit("Unexpected package layout")
        root = directories[0]

    for required in ("bin/codex", "bin/codex-code-mode-host", "codex-package.json"):
        if not (root / required).is_file():
            raise SystemExit(f"Missing {required}")
    metadata = json.loads((root / "codex-package.json").read_text())
    if not str(metadata.get("version", "")).startswith(version):
        raise SystemExit(f"Package metadata version mismatch: {metadata.get('version')} != {version}")
    if metadata.get("entrypoint") != "bin/codex":
        raise SystemExit(f"Unexpected entrypoint: {metadata.get('entrypoint')}")
    print(root)


if __name__ == "__main__":
    main()
