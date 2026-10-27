"""Test suite selection, explicit discovery, and logged shell coordination."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest import mock

from tests.lib.publisher_test_support import ROOT, PublisherTestCase
from tests.run import discover_tests, select_directories


class RunnerTests(PublisherTestCase):
    def discovery_fixture(self):
        root = self.base / "discovery"
        for name in ("codex", "gimp-3.2"):
            (root / "packages" / name).mkdir(parents=True)
            (root / "tests" / name).mkdir(parents=True)
        for directory, name in ((root / "tests", "framework"),
                                (root / "tests/codex", "codex"),
                                (root / "tests/gimp-3.2", "gimp")):
            (directory / f"test_runner_fixture_{name}.py").write_text(
                "import unittest\nclass Example(unittest.TestCase):\n"
                "    def test_example(self):\n        self.assertTrue(True)\n")
        return root

    def test_discovery_includes_hyphenated_stream_once_and_isolates_selection(self):
        root = self.discovery_fixture()
        for arguments, expected in (({"offline": True}, 3), ({"framework": True}, 1), ({}, 1)):
            packages = ["gimp-3.2"] if not arguments else []
            with self.subTest(arguments=arguments):
                with mock.patch.dict(sys.modules), mock.patch.object(sys, "path", sys.path.copy()):
                    suite = discover_tests(select_directories(root, packages, **arguments))
                    self.assertEqual(suite.countTestCases(), expected)
                    suite.debug()

    def test_unknown_missing_and_conflicting_selectors_fail_before_discovery(self):
        root = self.discovery_fixture()
        with self.assertRaisesRegex(ValueError, "Unknown package"):
            select_directories(root, ["../codex"])
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            select_directories(root, ["codex"], offline=True)
        shutil.rmtree(root / "tests/codex")
        with self.assertRaisesRegex(ValueError, "Missing regression tests"):
            select_directories(root, [], offline=True)

    def shell_fixture(self):
        root = self.base / "shell"
        (root / "tests/lib").mkdir(parents=True)
        (root / "packages").mkdir()
        (root / "update.sh").touch()
        shutil.copyfile(ROOT / "tests/run.sh", root / "tests/run.sh")
        shutil.copyfile(ROOT / "tests/lib/common.sh", root / "tests/lib/common.sh")
        for name, label in (("python3", "python"), ("bash", "signing")):
            stub = self.base / "bin" / name
            stub.write_text(f'#!/bin/sh\nprintf "{label} %s\\n" "$*" >> "$TEST_CALLS"\n')
            stub.chmod(0o755)
        environment = {**self.env, "TEST_CALLS": str(self.base / "calls")}
        return root, environment

    def test_only_full_suite_invokes_signing(self):
        root, environment = self.shell_fixture()
        for arguments in ([], ["--offline"], ["--framework"], ["gimp-3.2"], ["codex", "zed"]):
            with self.subTest(arguments=arguments):
                calls = Path(environment["TEST_CALLS"])
                calls.unlink(missing_ok=True)
                result = subprocess.run(["/bin/bash", root / "tests/run.sh", *arguments],
                                        cwd=root, env=environment, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                commands = calls.read_text().splitlines()
                self.assertEqual(any(line.startswith("signing ") for line in commands), not arguments)
                expected = " ".join(arguments or ["--offline"])
                self.assertEqual(commands[0], f"python -m tests.run {expected}")

    def test_logged_failure_keeps_output_and_exit_status(self):
        log = self.base / "failed.log"
        command = ('source "$FRAMEWORK_DIR/tests/lib/common.sh"\n'
                   'run_logged "$TEST_LOG" 5s /bin/bash -c "echo failure-evidence; exit 7"\n')
        result = subprocess.run(["/bin/bash", "-c", command],
                                env={**self.env, "FRAMEWORK_DIR": str(ROOT), "TEST_LOG": str(log)},
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 7)
        self.assertIn("failure-evidence", log.read_text())
        self.assertNotIn("failure-evidence", result.stdout + result.stderr)

    def test_logged_command_timeout_is_bounded(self):
        command = ('source "$FRAMEWORK_DIR/tests/lib/common.sh"\n'
                   'run_logged "$TEST_LOG" 0.1s sleep 5\n')
        result = subprocess.run(["/bin/bash", "-c", command], timeout=3,
                                env={**self.env, "FRAMEWORK_DIR": str(ROOT),
                                     "TEST_LOG": str(self.base / "timeout.log")},
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 124)
