"""Replace publisher-owned fields while retaining upstream control metadata."""
import os
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
replacements = {
    "Version": sys.argv[2],
    "Maintainer": os.environ["MAINTAINER"],
    "X-Build-Inputs-SHA256": os.environ["BUILD_INPUTS_SHA256"],
    "X-Publisher-Stream": os.environ["PUBLISHER_STREAM"],
}
text = path.read_text()
for field, value in replacements.items():
    text = re.sub(r"^" + re.escape(field) + r":[^\n]*\n(?:[ \t][^\n]*\n)*", "", text, flags=re.M | re.I)
    text = text.rstrip("\n") + f"\n{field}: {value}\n"
path.write_text(text)
