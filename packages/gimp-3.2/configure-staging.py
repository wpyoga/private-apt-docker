"""Apply native package defaults to the staged GIMP files."""

import configparser
import os
from pathlib import Path
import re


staging = Path(os.environ["STAGING_DIR"])
multiarch = os.environ["MULTIARCH"]
data = staging / "gimp-data"

# APT owns updates. The user setting alone cannot override package policy.
gimprc = data / "etc/gimp/3.0/gimprc"
text = gimprc.read_text()
text = re.sub(r"^[ \t]*\(check-updates\s+[^\n]*\)[ \t]*$", "", text, flags=re.M)
gimprc.write_text(text.rstrip() + "\n\n# Updates are delivered through APT.\n(check-updates no)\n")

release_file = data / "usr/share/gimp/3.0/gimp-release"
release = configparser.ConfigParser(interpolation=None)
release.read_string(release_file.read_text())
if not release.has_section("package"):
    raise SystemExit(f"[gimp-3.2] Missing [package] section in {release_file}")
release.set("package", "check-update", "false")
with release_file.open("w") as stream:
    release.write(stream)

# Debian 3.0 disables these examples with -Djavascript=disabled -Dlua=false.
# Exclude only their installed scripts; keep the C, Vala and Python examples.
extension = (staging / "gimp" / "usr/lib" / multiarch
             / "gimp/3.0/extensions/org.gimp.extension.goat-exercises")
metadata = extension / "org.gimp.extension.goat-exercises.metainfo.xml"
text = metadata.read_text()
pattern = r'(<value\s+key="GIMP::plug-in-path">)([^<]*)(</value>)'
matches = list(re.finditer(pattern, text))
if len(matches) != 1:
    raise SystemExit(f"[gimp-3.2] Expected one GIMP::plug-in-path field in {metadata}")
removed = {"goat-exercise-gjs.js", "goat-exercise-lua.lua"}
paths = matches[0].group(2).split(":")
for name in removed:
    (extension / name).unlink(missing_ok=True)
text = re.sub(pattern, lambda match: match[1] + ":".join(
    name for name in paths if name not in removed) + match[3], text)
metadata.write_text(text)

