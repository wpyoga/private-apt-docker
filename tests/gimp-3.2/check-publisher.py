"""Check the isolated live publisher's limits, packages, and published indexes."""

import json
import os
from pathlib import Path
import subprocess
import sys


def fields(text):
    result = {}
    for line in text.splitlines():
        if line and not line[0].isspace() and ": " in line:
            name, value = line.split(": ", 1)
            result[name.lower()] = value
    return result


context = Path(sys.argv[1])
state = json.loads((context / "container.json").read_text())[0]
assert state["HostConfig"]["Memory"] == 256 * 1024 * 1024
assert state["HostConfig"]["PidsLimit"] == 128
assert "ALL" in state["HostConfig"]["CapDrop"]
assert "no-new-privileges:true" in state["HostConfig"]["SecurityOpt"]
assert state["HostConfig"]["Init"]
assert state["Config"]["User"] == f"{os.getuid()}:{os.getgid()}"
assert not state["State"]["OOMKilled"]
assert state["State"]["ExitCode"] == 0
events = dict(line.split() for line in (context / "memory.events").read_text().splitlines())
assert int(events["oom_kill"]) == 0, events

indexes = {}
for architecture in ("amd64", "arm64"):
    path = context / f"repo/dists/trixie/main/binary-{architecture}/Packages"
    indexes[architecture] = {
        (row["package"], row["version"], row["architecture"]): row
        for row in (fields(record) for record in path.read_text().strip().split("\n\n"))
    }

archives = list((context / "repo/pool").rglob("*.deb"))
assert archives, "No packages stored"
for archive in archives:
    row = fields(subprocess.check_output(["dpkg-deb", "--field", archive], text=True))
    key = (row["package"], row["version"], row["architecture"])
    stream = row["x-publisher-stream"]
    workspace = context / "workspaces" / stream
    if stream == "gimp-help-3.2":
        staged = workspace / "help-staging" / row["package"]
    else:
        architecture = row["architecture"] if row["architecture"] != "all" else "amd64"
        staged = workspace / f"staging-{architecture}" / row["package"]
    size = subprocess.check_output([
        "du", "--summarize", "--block-size=1024", "--exclude=DEBIAN", staged,
    ], text=True).split()[0]
    assert int(row["installed-size"]) > 0
    assert row["installed-size"] == size, (archive, size, row["installed-size"])
    for architecture, index in indexes.items():
        if row["architecture"] not in (architecture, "all"):
            continue
        published = index[key]
        for field in ("installed-size", "depends", "x-publisher-stream", "x-build-inputs-sha256"):
            assert row.get(field) == published.get(field), (archive, field)
        assert published["filename"] == str(archive.relative_to(context / "repo"))
    assert archive.stat().st_uid == os.getuid(), archive

for architecture in os.environ.get("ARCHES", "amd64 arm64").split():
    index = indexes[architecture]
    assert len(index) == 41, (architecture, len(index))
    assert sum(key[0].startswith("gimp-help-") for key in index) == 33
print(f"Verified {len(archives)} stored packages and both published indexes")
print(f"Memory peak: {(context / 'memory.peak').read_text().strip()} bytes; OOM kills: 0")
