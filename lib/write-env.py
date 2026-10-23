"""Update setup-owned dotenv entries without replacing unrelated settings."""

import os
import pathlib
import re
import sys
import tempfile


def main():
    path = pathlib.Path(sys.argv[1])
    updates = dict(zip(("REPO_UID", "REPO_GID", "GPG_KEY"), sys.argv[2:], strict=True))
    lines = path.read_text().splitlines() if path.exists() else []
    kept = []
    for line in lines:
        match = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if not match or match[1] not in updates:
            kept.append(line)
    kept.extend(f"{key}={value}" for key, value in updates.items())
    descriptor, temporary = tempfile.mkstemp(prefix=".env-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as output:
            output.write("\n".join(kept) + "\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    main()
