"""Backport the known Debian 14 recipe to Trixie's debhelper 13."""

from pathlib import Path
import sys


def prepare_source(source):
    control = source / "debian/control"
    text = control.read_text()
    if text.count("debhelper-compat (= 14)") != 1:
        raise ValueError("libgit2: unexpected debhelper-compat in debian/control")
    text = text.replace("debhelper-compat (= 14)", "debhelper-compat (= 13)")
    expected = {"libgit2-1.9", "libgit2-dev", "libgit2-experimental1.9",
                "libgit2-experimental-dev", "libgit2-fixtures"}
    found = set()
    paragraphs = []
    for paragraph in text.strip().split("\n\n"):
        if paragraph.startswith("Package: "):
            name = paragraph.splitlines()[0].removeprefix("Package: ")
            if name not in expected or name in found:
                raise ValueError(f"libgit2: unexpected binary package {name}")
            found.add(name)
            # Compat 14 supplies these automatically; compat 13 requires fields.
            if "${misc:Depends}" in paragraph or "${shlibs:Depends}" in paragraph:
                raise ValueError(f"libgit2: changed dependency substitutions for {name}")
            dependencies = " ${misc:Depends},\n"
            if name in {"libgit2-1.9", "libgit2-experimental1.9"}:
                dependencies += " ${shlibs:Depends},\n"
            if "\nDepends:\n" in paragraph:
                paragraph = paragraph.replace("\nDepends:\n", "\nDepends:\n" + dependencies, 1)
            else:
                paragraph = paragraph.replace("\nDescription:", "\nDepends:\n" + dependencies + "Description:", 1)
        paragraphs.append(paragraph)
    if found != expected:
        raise ValueError(f"libgit2: missing binary packages: {sorted(expected - found)}")
    control.write_text("\n\n".join(paragraphs) + "\n")


if __name__ == "__main__":
    prepare_source(Path(sys.argv[1]))
