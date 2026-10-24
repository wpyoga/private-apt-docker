"""Report old upstream releases; inactivity never stops publication."""

from datetime import datetime, timezone
from pathlib import Path
import sys


def check(adapter, workspace):
    setting = adapter / "stale-after-days"
    if not setting.exists():
        return
    try:
        threshold = int(setting.read_text().strip())
        if threshold <= 0:
            raise ValueError("stale-after-days must be a positive integer")
        value = (workspace / "release-date").read_text().strip()
        released = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if released.tzinfo is None:
            raise ValueError("release-date must include a timezone")
        age = datetime.now(timezone.utc) - released
        if age.total_seconds() < 0:
            raise ValueError("release-date is in the future")
    except (OSError, ValueError) as error:
        print(f"WARNING: [{adapter.name}] Cannot assess upstream activity: {error}", file=sys.stderr)
        return
    if age.total_seconds() > threshold * 86400:
        print(
            f"WARNING: [{adapter.name}] UPSTREAM STREAM MAY BE INACTIVE\n"
            f"Latest upstream release: {value} ({age.days} days ago).\n"
            f"Configured inactivity threshold: {threshold} days.\n"
            "Publication and monitoring will continue.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    check(Path(sys.argv[1]), Path(sys.argv[2]))
