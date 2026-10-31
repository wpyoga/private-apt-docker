"""Keep upstream rebuilds distinct and ordered without publisher counters."""
import datetime
import json
from pathlib import Path
import re
import sys

try:
    release = json.loads(Path(sys.argv[1]).read_text())
    tag = release["tag_name"]
    match = re.fullmatch(r"v([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)-([0-9a-f]{40})", tag)
    if not match:
        raise ValueError(f"Unexpected Cromite release tag: {tag}")
    date = datetime.datetime.fromisoformat(release["published_at"].replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("Cromite published_at must include a timezone")
    timestamp = date.astimezone(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    print(f"{match[1]}+{timestamp}.git{match[2]}")
except (KeyError, TypeError, ValueError) as error:
    sys.exit(f"[cromite] Invalid release metadata: {error}")
