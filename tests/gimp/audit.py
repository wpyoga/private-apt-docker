"""Check the installed repack's ELF dependencies and symbol relocations."""

from pathlib import Path
import subprocess


files = subprocess.check_output([
    "dpkg-query", "--listfiles", "gimp", "libgimp-3.0-0", "gimp-bundled-runtime",
], text=True).splitlines()
checked = 0
failures = []
with Path("/test/elf-resolution.log").open("w") as log:
    for filename in sorted(set(files)):
        path = Path(filename)
        if not path.is_file() or path.is_symlink():
            continue
        with path.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                continue
        result = subprocess.run(["ldd", "-r", path], text=True, capture_output=True)
        text = result.stdout + result.stderr
        log.write(f"{path}\n{text}\n")
        checked += 1
        if result.returncode or any(word in text for word in (
                "not found", "undefined symbol", "error while loading")):
            failures.append(f"{path}\n{text}")
if failures:
    raise SystemExit("\n".join(failures))
print(f"ELF_RESOLUTION_PASS: {checked} installed objects")
