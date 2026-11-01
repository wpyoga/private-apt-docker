"""Select Debian's newest 1.9 source, retaining its complete source revision."""

import os
from pathlib import Path
import re
import subprocess
import sys


def select_version(text):
    selected = None
    for paragraph in text.strip().split("\n\n"):
        fields = {}
        for line in paragraph.splitlines():
            if line and not line[0].isspace() and ": " in line:
                name, value = line.split(": ", 1)
                if name in fields:
                    raise ValueError(f"libgit2: duplicate source field {name}")
                fields[name] = value
        if fields.get("Package") != "libgit2":
            continue
        version = fields.get("Version", "")
        if not version:
            raise ValueError("libgit2: missing source Version")
        subprocess.run(["dpkg", "--validate-version", version], check=True)
        if not re.fullmatch(r"1\.9\.\d+\+ds-\d+(?:\+\w+)?", version):
            continue
        if selected is None or subprocess.run(
            ["dpkg", "--compare-versions", version, "gt", selected]
        ).returncode == 0:
            selected = version
    return selected


def prepare_targets(workspace, architectures):
    version = (workspace / "source-version").read_text().strip()
    descriptors = list((workspace / "source").glob("libgit2_*.dsc"))
    if len(descriptors) != 1:
        raise ValueError("libgit2: expected exactly one source descriptor")
    lines = descriptors[0].read_text().splitlines()
    if [line for line in lines if line.startswith("Version:")] != [f"Version: {version}"]:
        raise ValueError(f"libgit2: source descriptor Version does not match {version}")
    if [line for line in lines if line.startswith("Source:")] != ["Source: libgit2"]:
        raise ValueError("libgit2: unexpected source descriptor Source")
    (workspace / "source-descriptor").write_text(str(descriptors[0]) + "\n")
    (workspace / "targets.tsv").write_text("".join(
        f"{version}+local\t{architecture}\n" for architecture in architectures))


if __name__ == "__main__":
    workspace = Path(os.environ["WORKSPACE"])
    if sys.argv[1] == "select":
        version = select_version((workspace / "sources").read_text())
        (workspace / "source-version").write_text(version + "\n" if version else "")
        (workspace / "targets.tsv").write_text("")
    elif sys.argv[1] == "targets":
        prepare_targets(workspace, os.environ["ARCHES"].split())
    else:
        raise ValueError("libgit2: expected select or targets")
