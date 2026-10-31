"""Retain the complete Debian source version in publisher targets."""
import os
from pathlib import Path
import subprocess


def prepare_targets(workspace, architectures):
    descriptors = list((workspace / "source").glob("xfce4-terminal_*.dsc"))
    if len(descriptors) != 1:
        raise ValueError("xfce4-terminal: expected exactly one source descriptor")
    versions = [line.removeprefix("Version: ") for line in descriptors[0].read_text().splitlines()
                if line.startswith("Version: ")]
    if len(versions) != 1:
        raise ValueError("xfce4-terminal: missing or duplicate source Version")
    version = versions[0]
    subprocess.run(["dpkg", "--validate-version", version], check=True)
    (workspace / "source-version").write_text(version + "\n")
    (workspace / "source-descriptor").write_text(str(descriptors[0]) + "\n")
    (workspace / "targets.tsv").write_text("".join(
        f"{version}+local\t{architecture}\n" for architecture in architectures))


if __name__ == "__main__":
    prepare_targets(Path(os.environ["WORKSPACE"]), os.environ["ARCHES"].split())
