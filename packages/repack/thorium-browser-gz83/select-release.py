"""Select exact CPU assets; GitHub's latest flag also marks announcements."""

import json
import os
from pathlib import Path
import re
import sys


def selected_asset(asset):
    name = asset["name"]
    digest = asset.get("digest")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        raise ValueError(f"{name}: missing or invalid SHA256 digest")
    url = asset.get("browser_download_url")
    if not isinstance(url, str) or not url.startswith("https://") or re.search(r"\s", url):
        raise ValueError(f"{name}: invalid download URL")
    return {"name": name, "url": url, "sha256": digest[7:]}


def select():
    workspace = Path(os.environ["WORKSPACE"])
    repository = os.environ["UPSTREAM_REPOSITORY"]
    releases = []
    for page in sorted((workspace / "releases").glob("*.json")):
        for release in json.loads(page.read_text()):
            if not isinstance(release.get("draft"), bool):
                raise ValueError(f"{repository}: missing draft flag")
            if not isinstance(release.get("prerelease"), bool):
                raise ValueError(f"{repository}: missing prerelease flag")
            assets = release.get("assets")
            if not isinstance(assets, list) or not all(isinstance(a, dict) for a in assets):
                raise ValueError(f"{repository}: invalid assets list")
            if release["draft"]:
                continue
            tag = release.get("tag_name", "")
            match = re.fullmatch(r"M(\d+\.\d+\.\d+\.\d+)", tag)
            if not match:
                continue
            if os.environ["ALLOW_BETA"] == "false":
                if release["prerelease"] or re.search(
                    r"beta|alpha|preview|pre-release", release.get("name") or "", re.I
                ):
                    continue
            version = match[1]
            releases.append((tuple(map(int, version.split("."))), version, release))
    releases.sort(key=lambda item: item[0], reverse=True)

    selected = {}
    for arch in os.environ["ARCHES"].split():
        if arch not in ("amd64", "arm64"):
            raise ValueError(f"Unsupported architecture: {arch}")
        stream = os.environ["PUBLISHER_STREAM"]
        tiers = ("SSE3", "SSE4", "AVX", "AVX2")
        if arch == "arm64":
            if repository != "gz83/thorium":
                continue
            tiers = ("arm64",)
        for _, version, release in releases:
            assets = {}
            for tier in tiers:
                name = f"thorium-browser_{version}_{tier}.deb"
                matches = [asset for asset in release["assets"] if asset.get("name") == name]
                if len(matches) > 1:
                    raise ValueError(f"{repository}: duplicate asset {name}")
                if matches:
                    package = stream if tier == "arm64" else f"{stream}-{tier.lower()}"
                    assets[package] = selected_asset(matches[0])
            if len(assets) == len(tiers):
                selected[arch] = {
                    "version": version, "assets": assets,
                    "published_at": release.get("published_at"),
                }
                break
            if assets:
                print(f"WARNING: [{stream}] Incomplete {version} CPU asset set for {arch}; "
                      "looking for the latest complete release", file=sys.stderr)
    (workspace / "assets.json").write_text(json.dumps(selected) + "\n")
    (workspace / "targets.tsv").write_text("".join(
        f"{asset['version']}\t{arch}\n" for arch, asset in selected.items()
    ))
    if selected:
        latest = max(selected.values(), key=lambda a: tuple(map(int, a["version"].split("."))))
        if isinstance(latest["published_at"], str):
            (workspace / "release-date").write_text(latest["published_at"] + "\n")


if __name__ == "__main__":
    try:
        select()
    except (ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"Thorium release selection: {error}") from error
