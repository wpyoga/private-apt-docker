"""Exercise setup with temporary storage and fake sudo/Docker commands."""

import json
import os
import subprocess
import unittest

from tests.lib.publisher_test_support import KEY, ROOT, PublisherTestCase


class SetupTests(PublisherTestCase):
    def setUp(self):
        super().setUp()
        sudo = self.base / "bin/sudo"
        sudo.write_text('''#!/bin/bash
set -Eeuo pipefail
case "$1" in
    install) exec "$@" ;;
    *) exit 1 ;;
esac
''')
        sudo.chmod(0o755)

        # Any accidental host GPG invocation must fail, including key listing.
        (self.base / "bin/gpg").write_text("#!/bin/bash\nexit 99\n")
        docker = self.base / "bin/docker"
        docker.write_text('''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
with open(os.environ["TEST_DOCKER_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
if os.environ.get("TEST_DOCKER_FAIL"):
    sys.exit("Fixture Docker failure")
if args[0] == "build":
    sys.exit(0)
assert args[0] == "run"
mount = args[args.index("--mount") + 1]
fingerprint = "B" * 40 if "/rebuild-gnupg," in mount else "A" * 40
if "--list-secret-keys" in args:
    marker = Path(os.environ["TEST_DOCKER_LOG"] + fingerprint)
    if not os.environ.get("TEST_GENERATE_KEYS") or marker.exists():
        print("sec:-:\\nfpr:::::::::" + fingerprint + ":")
elif "--quick-generate-key" in args:
    Path(os.environ["TEST_DOCKER_LOG"] + fingerprint).touch()
else:
    assert "--export" in args
    print("Test public key")
''')
        docker.chmod(0o755)
        self.env["TEST_DOCKER_LOG"] = str(self.base / "docker.jsonl")

    def write_settings(self):
        user = subprocess.check_output(["id", "-un"], text=True).strip()
        settings = (
            "# Settings\nCODEX_UID=42\nPACKAGES=codex\n"
            f"REPACK_REPO_DIR='{self.base / 'storage/repo'}'\n"
            f"REBUILD_REPO_DIR='{self.base / 'storage/rebuild'}'\n"
            f"REPACK_GNUPG_DIR='{self.base / 'repack-gnupg'}'\n"
            f"REBUILD_GNUPG_DIR='{self.base / 'rebuild-gnupg'}'\n"
            f"REPO_USER={user}\nREPO_DATA_DIR='{self.base / 'storage'}'\n"
            "MAINTAINER='Test <test@example.com>'\nREPO_NAME='Test Repository'\n"
            "GPG_KEY_NAME='Test Key'\nGPG_KEY_TYPE=ed25519\nGPG_KEY_VALIDITY=1d\n"
        )
        path = self.base / ".env"
        path.write_text(settings + "REPO_UID=old\nexport REPO_GID=old\nGPG_KEY=old\n")
        return path, settings

    def test_env_updates_preserve_unrelated_settings(self):
        path, settings = self.write_settings()
        environment = {**self.env, "FRAMEWORK_DIR": str(self.base)}
        command = ["bash", str(ROOT / "codex-repo-setup.sh")]
        automatic_environment = dict(environment)
        automatic_environment.pop("FRAMEWORK_DIR", None)
        subprocess.run(command, env=automatic_environment, cwd=self.base,
                       check=True, capture_output=True)
        subprocess.run(command, env=environment, check=True, capture_output=True)

        expected = settings + (
            f"REPO_UID={os.getuid()}\nREPO_GID={os.getgid()}\nREPACK_GPG_KEY={KEY}\nREBUILD_GPG_KEY={'B'*40}\n"
        )
        self.assertEqual(path.read_text(), expected)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.base / "repack-pubkey.asc").read_text(), "Test public key\n")
        self.assertEqual(list(self.base.glob(".env-*")), [])

        calls = [json.loads(line) for line in
                 (self.base / "docker.jsonl").read_text().splitlines()]
        runs = [args for args in calls if args[0] == "run"]
        self.assertEqual(len(runs), 12)
        for args in runs:
            self.assertIn("--rm", args)
            self.assertIn("--init", args)
            self.assertEqual(args[args.index("--user") + 1],
                             f"{os.getuid()}:{os.getgid()}")
            self.assertEqual(args[args.index("--tmpfs") + 1],
                             f"/run/user/{os.getuid()}:rw,noexec,nosuid,nodev,"
                             f"mode=0700,uid={os.getuid()},gid={os.getgid()}")
            self.assertIn("dst=/gnupg", args[args.index("--mount") + 1])

    def test_missing_keys_are_generated_inside_containers(self):
        self.write_settings()
        subprocess.run(
            ["bash", str(ROOT / "codex-repo-setup.sh")],
            env={**self.env, "FRAMEWORK_DIR": str(self.base),
                 "TEST_GENERATE_KEYS": "1"},
            check=True, capture_output=True,
        )
        calls = [json.loads(line) for line in
                 (self.base / "docker.jsonl").read_text().splitlines()]
        generations = [args for args in calls if "--quick-generate-key" in args]
        self.assertEqual(len(generations), 2)
        self.assertTrue((self.base / "repack-pubkey.asc").is_file())
        self.assertTrue((self.base / "rebuild-pubkey.asc").is_file())

    def test_docker_failure_preserves_configuration(self):
        path, _ = self.write_settings()
        original = path.read_bytes()
        result = subprocess.run(
            ["bash", str(ROOT / "codex-repo-setup.sh")],
            env={**self.env, "FRAMEWORK_DIR": str(self.base),
                 "TEST_DOCKER_FAIL": "1"},
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Fixture Docker failure", result.stderr)
        self.assertEqual(path.read_bytes(), original)

    def test_same_output_directories_fail_before_setup(self):
        settings = (
            "REPO_USER=test\nREPACK_GNUPG_DIR=/unused/repack-key\nREBUILD_GNUPG_DIR=/unused/rebuild-key\n"
            "REPACK_REPO_DIR=/unused/repo\nREBUILD_REPO_DIR=/unused/repo/../repo\n"
            "MAINTAINER='Test <test@localhost>'\nREPO_NAME=Test\n"
            "GPG_KEY_NAME=Test\nGPG_KEY_TYPE=ed25519\nGPG_KEY_VALIDITY=1d\n"
        )
        path = self.base / ".env"
        path.write_text(settings)
        result = subprocess.run(
            ["bash", str(ROOT / "codex-repo-setup.sh")],
            env={**self.env, "FRAMEWORK_DIR": str(self.base)},
            capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be different directories", result.stderr)
        self.assertEqual(path.read_text(), settings)


if __name__ == "__main__":
    unittest.main()
