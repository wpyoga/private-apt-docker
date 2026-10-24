"""Validate an adapter's targets before any artifacts are built or published."""

import pathlib
import re
import subprocess
import sys


def main():
    architectures = set(sys.argv[2].split())
    seen = set()
    content = pathlib.Path(sys.argv[1]).read_bytes().decode("utf-8")
    if content and not content.endswith("\n"):
        raise SystemExit("targets.tsv must end with a newline")
    for number, line in enumerate(content.splitlines(keepends=True), 1):
        line = line.removesuffix("\n")
        fields = line.split("\t")
        if len(fields) != 2:
            raise SystemExit(f"Invalid target row {number}: expected VERSION<TAB>ARCH")
        version, architecture = fields
        if not re.fullmatch(r"[0-9][A-Za-z0-9.+:~\-]*", version):
            raise SystemExit(f"Invalid Debian version in row {number}: {version}")
        subprocess.run(["dpkg", "--validate-version", version], check=True)
        if architecture not in architectures:
            raise SystemExit(f"Unrequested architecture in row {number}: {architecture}")
        if architecture in seen:
            raise SystemExit(f"Multiple current releases for architecture: {architecture}")
        seen.add(architecture)
    # An empty file is valid: the adapter has no eligible releases.


if __name__ == "__main__":
    main()
