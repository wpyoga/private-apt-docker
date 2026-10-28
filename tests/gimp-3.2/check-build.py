"""Verify real GIMP build metadata and inspection indexes for both architectures.

Usage: python3 tests/gimp-3.2/check-build.py WORKSPACE
The workspace is the one supplied to the adapter's query/build hooks.
"""

import json
import io
from pathlib import Path
import re
import subprocess
import sys
import tarfile


def fields(text):
    result = {}
    for line in text.splitlines():
        if line and not line[0].isspace():
            key, value = line.split(":", 1)
            result[key.lower()] = value.strip()
    return result


workspace = Path(sys.argv[1])
assets = json.loads((workspace / "assets.json").read_text())
names = {"gimp", "gimp-data", "libgimp-3.0-0", "gir1.2-gimp-3.0", "gimp-bundled-runtime",
         "libgimp-3.0-bin", "libgimp-3.0-dev", "libgimp-3.0-doc"}
fingerprints = set()
for arch in ("amd64", "arm64"):
    owners = {}
    output = workspace / "output" / arch
    index_text = subprocess.check_output([
        "dpkg-scanpackages", "--multiversion", ".", "/dev/null",
    ], cwd=output, text=True)
    (workspace / f"Packages-{arch}").write_text(index_text)
    index = {row["package"]: row for row in
             (fields(stanza) for stanza in index_text.strip().split("\n\n"))}
    assert set(index) == names, index.keys()
    archives = list(output.glob("*.deb"))
    assert len(archives) == len(names), archives
    for archive in archives:
        control = fields(subprocess.check_output(["dpkg-deb", "--field", archive], text=True))
        name = control["package"]
        independent = name == "libgimp-3.0-doc" or name.startswith("gimp-help-")
        assert control["architecture"] == ("all" if independent else arch), control
        assert control["version"].rsplit("-", 1)[0] == assets[arch]["version"], control
        assert control["x-publisher-stream"] == "gimp-3.2", control
        digest = control["x-build-inputs-sha256"]
        assert re.fullmatch(r"[0-9a-f]{64}", digest), digest
        fingerprints.add(digest)
        staged = workspace / f"staging-{arch}" / name
        process = subprocess.Popen(["dpkg-deb", "--fsys-tarfile", archive], stdout=subprocess.PIPE)
        with tarfile.open(fileobj=process.stdout, mode="r|") as stream:
            for member in stream:
                if member.isdir():
                    continue
                path = member.name.removeprefix("./")
                assert path not in owners, (arch, path, owners.get(path), name)
                owners[path] = name
        process.stdout.read()
        process.stdout.close()
        assert process.wait() == 0, archive
        usage = subprocess.check_output([
            "du", "--summarize", "--block-size=1024", "--exclude=DEBIAN",
            staged,
        ], text=True)
        assert int(control["installed-size"]) == int(usage.split()[0]), (name, usage, control)
        for key in ("version", "architecture", "installed-size", "depends",
                    "x-publisher-stream", "x-build-inputs-sha256"):
            assert control.get(key) == index[name].get(key), (name, key)
        print(f"REAL_PACKAGE_CHECK_PASS: {name} {arch} {control['version']} "
              f"Installed-Size={control['installed-size']} KiB")
assert len(fingerprints) == 1, fingerprints
print(f"REAL_BUILD_CHECK_PASS: {len(names)} outputs per architecture, matching index metadata")
