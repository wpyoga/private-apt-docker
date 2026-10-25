"""Shared temporary repository and download fixtures for offline tests."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
KEY = "A" * 40

STUB = r'''#!/usr/bin/env python3
import os
from pathlib import Path
import shutil
import sys

args = sys.argv[1:]
if Path(sys.argv[0]).name == "curl":
    destination = args[args.index("-o") + 1]
    url = next(arg for arg in args if arg.startswith("https://"))
    name = "release.json" if url.endswith("/releases/latest") else url.rsplit("/", 1)[1]
    shutil.copyfile(Path(os.environ["TEST_DOWNLOADS"]) / name, destination)
elif os.environ.get("TEST_REAL_GPG"):
    os.execv(os.environ["TEST_GPG_COMMAND"], [os.environ["TEST_GPG_COMMAND"], *args])
elif "--output" in args:
    if os.environ.get("TEST_FAIL_SIGN"):
        raise SystemExit("Fixture signing failure")
    shutil.copyfile(args[-1], args[args.index("--output") + 1])
'''


def fields(path):
    text = subprocess.check_output(["dpkg-deb", "--field", str(path)], text=True)
    metadata = {}
    for line in text.splitlines():
        if not line or line[0].isspace() or ":" not in line:
            continue
        name, value = line.split(":", 1)
        metadata[name.lower()] = value.strip()
    return metadata


class PublisherTestCase(unittest.TestCase):
    def setUp(self):
        (ROOT / "build").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="test-", dir=ROOT / "build")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        for directory in ("bin", "adapters", "downloads", "tmp"):
            (self.base / directory).mkdir()
        for command in ("gpg", "curl"):
            stub = self.base / "bin" / command
            stub.write_text(STUB)
            stub.chmod(0o755)
        self.publisher = self.base / "publisher"
        self.publisher.mkdir()
        for name in ("update.sh", "Dockerfile"):
            shutil.copyfile(ROOT / name, self.publisher / name)
        shutil.copytree(ROOT / "lib", self.publisher / "lib", ignore=shutil.ignore_patterns("__pycache__"))
        self.env = {
            **os.environ,
            "PATH": f"{self.base / 'bin'}:{os.environ['PATH']}",
            "FRAMEWORK_DIR": str(self.publisher),
            "REPO_DIR": str(self.base / "repo"),
            "PACKAGES_DIR": str(self.base / "adapters"),
            "ARCHES": "amd64 arm64",
            "REPO_ARCHITECTURES": "amd64 arm64",
            "CHECK_INTERVAL": "21600",
            "MAINTAINER": "Repository Test <test@localhost>",
            "REPO_NAME": "Test APT Repository",
            "REPO_DESCRIPTION": "Repository integration fixtures",
            "CODENAME": "trixie",
            "GPG_KEY": KEY,
            "GNUPGHOME": str(self.base / "keyring"),
            "TMPDIR": str(self.base / "tmp"),
            "TEST_EVENTS": str(self.base / "events"),
            "TEST_DOWNLOADS": str(self.base / "downloads"),
            "TEST_GPG_COMMAND": shutil.which("gpg"),
        }
        for name in ("TEST_REAL_GPG", "TEST_FAIL_SIGN", "TEST_FAIL_ARCH", "TEST_VERSION"):
            self.env.pop(name, None)

    def adapter(
        self,
        name="first",
        *,
        package=None,
        stream=None,
        version="1.2.3",
        query=None,
        build=None,
    ):
        directory = self.base / "adapters" / name
        directory.mkdir()
        package_name = package or f"{name}-cli"
        (directory / "config").write_text(
            f'RELEASE_STREAM={stream or name}\nBINARY_PACKAGES="{package_name}"\n'
        )
        (directory / "upstream-version").write_text(version + "\n")

        for hook, custom_body in (("query", query), ("build", build)):
            if custom_body is None:
                script = (ROOT / "tests/fixtures/stream" / hook).read_text()
            else:
                script = "#!/bin/bash\nset -Eeuo pipefail\n" + custom_body

            event = f'printf "%s\\n" "{name}/{hook}" >> "$TEST_EVENTS"\n'
            script = script.replace("set -Eeuo pipefail\n", "set -Eeuo pipefail\n" + event, 1)
            path = directory / hook
            path.write_text(script)
            path.chmod(0o755)

        return directory

    def run_update(self, expected=0):
        result = subprocess.run(
            ["bash", str(self.publisher / "update.sh")], env=self.env, text=True, capture_output=True
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertEqual(list((self.base / "tmp").iterdir()), [], "Workspace leaked")
        return result

    def artifacts(self, stream=None):
        paths = sorted((self.base / "repo/pool").rglob("*.deb"))
        if stream is not None:
            paths = [path for path in paths if fields(path).get("x-publisher-stream") == stream]
        return paths

    def versions(self, stream):
        return {fields(path)["version"] for path in self.artifacts(stream)}

    def index(self, arch="amd64"):
        return (self.base / f"repo/dists/trixie/main/binary-{arch}/Packages").read_text()

    def legacy(self, package, version, arch):
        root = self.base / f"legacy-{package}-{arch}"
        (root / "DEBIAN").mkdir(parents=True, exist_ok=True)
        (root / "DEBIAN/control").write_text(
            f"Package: {package}\nVersion: {version}\nArchitecture: {arch}\n"
            "Maintainer: Test <test@localhost>\nDescription: Legacy fixture\n"
        )
        destination = self.base / f"repo/pool/main/legacy/{package}_{version}_{arch}.deb"
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["dpkg-deb", "--build", str(root), str(destination)], check=True, capture_output=True)
        return destination
