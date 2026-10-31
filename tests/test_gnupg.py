"""Reject GnuPG socket fallback to persistent host storage."""

import os
import subprocess
import unittest

from tests.lib.publisher_test_support import ROOT, PublisherTestCase


class GnuPGTests(PublisherTestCase):
    def setUp(self):
        super().setUp()
        command = self.base / "bin/gpgconf"
        command.write_text('''#!/bin/bash
set -Eeuo pipefail
if [[ "$1" == --create-socketdir ]]; then
    exit "${TEST_CREATE_STATUS:-0}"
fi
printf '%s\n' "$TEST_SOCKET_DIR"
''')
        command.chmod(0o755)

    def prepare(self, socket_dir, **settings):
        return subprocess.run(
            ["bash", "-c", 'set -Eeuo pipefail; source "$FRAMEWORK_DIR/lib/gnupg.sh"; '
             'prepare_gnupg_socket_directory'],
            env={**self.env, "TEST_SOCKET_DIR": socket_dir, **settings},
            capture_output=True, text=True,
        )

    def test_private_runtime_socket_directory_is_accepted(self):
        result = self.prepare(f"/run/user/{os.getuid()}/gnupg/d.fixture")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_fallback_and_other_users_directories_are_rejected(self):
        for directory in (self.env["GNUPGHOME"], "/gnupg", "/run/user/999999/gnupg",
                          f"/run/user/{os.getuid()}/gnupg-shared"):
            with self.subTest(directory=directory):
                result = self.prepare(directory)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("check the container tmpfs mount", result.stderr)

    def test_socket_creation_failure_stops_startup(self):
        result = self.prepare(f"/run/user/{os.getuid()}/gnupg", TEST_CREATE_STATUS="1")
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
