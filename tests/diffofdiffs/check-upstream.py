"""Run upstream checks using Bash for symbolic signal-name conversion."""

from pathlib import Path
import subprocess
import sys


source = Path(sys.argv[1])
makefile = source / "Makefile"
text = makefile.read_text()
original = '\t$(Q)tests/run-one.sh tests/$*'
if text.count(original) != 2:
    raise SystemExit("Unexpected upstream test-runner commands in Makefile")
# Dash's kill builtin rejects `kill -l XFSZ`. The runner's inner sh -c
# wrappers remain unchanged, retaining their 512-byte file-limit units.
makefile.write_text(text.replace(original, '\t$(Q)bash tests/run-one.sh tests/$*'))
subprocess.run(["make", "-C", str(source), "check", "V=1", "-j2"], check=True)
