"""Replace publisher-owned fields while retaining upstream control metadata."""

import os
from pathlib import Path
import sys


def rewrite_fields(text, replacements):
    replacement_names = {name.lower() for name in replacements}
    retained_lines = []
    replacing_field = False

    for line in text.splitlines(keepends=True):
        if not line.startswith((" ", "\t")):
            field_name = line.split(":", 1)[0].lower()
            replacing_field = field_name in replacement_names

        # Continuation lines belong to the preceding field.
        if not replacing_field:
            retained_lines.append(line)

    result = "".join(retained_lines).rstrip("\n") + "\n"
    for name, value in replacements.items():
        result += f"{name}: {value}\n"
    return result


def main():
    path = Path(sys.argv[1])
    replacements = {
        "Version": sys.argv[2],
        "Installed-Size": sys.argv[3],
        "Maintainer": os.environ["MAINTAINER"],
        "X-Build-Inputs-SHA256": os.environ["BUILD_INPUTS_SHA256"],
        "X-Publisher-Stream": os.environ["PUBLISHER_STREAM"],
    }
    for index in range(4, len(sys.argv), 2):
        replacements[sys.argv[index]] = sys.argv[index + 1]
    path.write_text(rewrite_fields(path.read_text(), replacements))


if __name__ == "__main__":
    main()
