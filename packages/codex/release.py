"""Resolve stable Codex release assets into package targets and build metadata."""

import json
import pathlib
import re
import sys

TARGETS = {
    "amd64": "x86_64-unknown-linux-musl",
    "arm64": "aarch64-unknown-linux-musl",
}


def main():
    workspace = pathlib.Path(sys.argv[1])
    release = json.loads((workspace / "release.json").read_text())
    tag = release["tag_name"]
    if (
        release.get("draft")
        or release.get("prerelease")
        or not re.fullmatch(r"rust-v\d+\.\d+\.\d+", tag)
    ):
        raise SystemExit(f"Unexpected release tag: {tag}")

    version = tag.removeprefix("rust-v")
    assets = {asset["name"]: asset for asset in release["assets"]}
    selected = {}
    for architecture in sys.argv[2].split():
        if architecture not in TARGETS:
            raise SystemExit(f"Unsupported architecture: {architecture}")
        name = f"codex-package-{TARGETS[architecture]}.tar.gz"
        asset = assets.get(name)
        if not asset or not re.fullmatch(
            r"sha256:[0-9a-fA-F]{64}", asset.get("digest") or ""
        ):
            raise SystemExit(f"Missing archive or SHA256 digest in GitHub release: {name}")
        url = asset["browser_download_url"]
        if not url.startswith("https://") or any(c.isspace() for c in url):
            raise SystemExit(f"Invalid asset URL: {name}")
        selected[architecture] = {
            "version": version,
            "name": name,
            "url": url,
            "sha256": asset["digest"][7:],
        }

    (workspace / "assets.json").write_text(json.dumps(selected, indent=4) + "\n")
    (workspace / "targets.tsv").write_text(
        "".join(f"{version}\t{architecture}\n" for architecture in selected)
    )


if __name__ == "__main__":
    main()
