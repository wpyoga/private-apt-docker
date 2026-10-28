"""Select the newest numbered release from upstream's binary checksum manifest."""

import json
import os
from pathlib import Path
import re


workspace = Path(os.environ["WORKSPACE"])
checksums = {}
versions = set()
for number, line in enumerate((workspace / "sha256checksums.txt").read_text().splitlines(), 1):
    if not line.strip():
        continue
    match = re.fullmatch(r"([0-9a-fA-F]{64})  (usbimager_[A-Za-z0-9_.-]+)", line)
    if not match:
        raise SystemExit(f"[usbimager] Invalid checksum manifest row {number}")
    digest, name = match.groups()
    if name in checksums:
        raise SystemExit(f"[usbimager] Duplicate checksum entry: {name}")
    checksums[name] = digest.lower()
    release = re.fullmatch(r"usbimager_([0-9]+\.[0-9]+\.[0-9]+)[_-].+", name)
    if release:
        versions.add(release[1])

if not versions:
    raise SystemExit("[usbimager] No stable numbered releases in checksum manifest")
version = max(versions, key=lambda value: tuple(map(int, value.split("."))))
suffixes = {"amd64": "-amd64.deb", "arm64": "_uf-aarch64-linux-x11.zip"}
assets = {}
for architecture in os.environ["ARCHES"].split():
    if architecture not in suffixes:
        raise SystemExit(f"[usbimager] Unsupported architecture: {architecture}")
    name = f"usbimager_{version}{suffixes[architecture]}"
    if name in checksums:
        assets[architecture] = {
            "version": version,
            "name": name,
            "url": f"https://gitlab.com/bztsrc/usbimager/-/raw/binaries/{name}",
            "sha256": checksums[name],
        }

(workspace / "assets.json").write_text(json.dumps(assets) + "\n")
(workspace / "targets.tsv").write_text("".join(
    f"{version}\t{architecture}\n" for architecture in assets
))
