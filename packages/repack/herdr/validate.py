"""Check the upstream static Linux binary without execution."""

from pathlib import Path
import subprocess
import sys


binary, architecture = sys.argv[1:]
with Path(binary).open("rb") as source:
    header = source.read(20)
machine = {"amd64": 62, "arm64": 183}[architecture]
if (len(header) != 20 or header[:6] != b"\x7fELF\x02\x01"
        or int.from_bytes(header[18:20], "little") != machine):
    raise SystemExit(f"{binary}: invalid {architecture} ELF binary")

# Current releases use musl and have no external shared libraries.
dynamic = subprocess.check_output(["readelf", "--dynamic", binary], text=True)
programs = subprocess.check_output(["readelf", "--program-headers", binary], text=True)
if "(NEEDED)" in dynamic or "INTERP" in programs:
    raise SystemExit(f"{binary}: expected a static Linux binary")
