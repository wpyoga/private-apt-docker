"""Exercise setup with temporary storage and fake sudo/GPG commands."""

import os
import subprocess
import unittest

from tests.lib.publisher_test_support import KEY, ROOT, PublisherTestCase


class SetupTests(PublisherTestCase):
    def test_env_updates_preserve_unrelated_settings(self):
        sudo = self.base / "bin/sudo"
        sudo.write_text('''#!/bin/bash
set -Eeuo pipefail
if [[ "$1" == "-u" ]]; then
    shift 2
fi
case "$1" in
    install|gpg) exec "$@" ;;
    *) exit 1 ;;
esac
''')
        sudo.chmod(0o755)

        gpg = self.base / "bin/gpg"
        gpg.write_text(f'''#!/bin/bash
set -Eeuo pipefail
FINGERPRINT={KEY}
if [[ " $* " == *"/rebuild-gnupg "* ]]; then FINGERPRINT={'B'*40}; fi
if [[ " $* " == *" --list-secret-keys "* ]]; then
    printf 'sec:-:\\nfpr:::::::::%s:\\n' "$FINGERPRINT"
else
    printf 'Test public key\\n'
fi
''')
        gpg.chmod(0o755)

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
