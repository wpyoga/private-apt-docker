"""Offline integration tests with real package/index tools and fixture downloads."""

from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
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


class PublisherTests(unittest.TestCase):
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

    def test_entry_points_require_nonempty_framework_directory(self):
        scripts = ("entrypoint.sh", "update.sh")
        for script in scripts:
            for value in (None, ""):
                with self.subTest(script=script, value=value):
                    environment = dict(self.env)
                    environment.pop("FRAMEWORK_DIR", None)
                    if value is not None:
                        environment["FRAMEWORK_DIR"] = value
                    result = subprocess.run(
                        ["bash", str(ROOT / script)],
                        env=environment,
                        text=True,
                        capture_output=True,
                        timeout=3,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("FRAMEWORK_DIR must", result.stderr)

    def test_shell_test_entry_points_reject_wrong_working_directory(self):
        environment = dict(self.env)
        environment.pop("FRAMEWORK_DIR", None)
        for script in ("tests/run.sh", "tests/test-signed-repo.sh"):
            with self.subTest(script=script):
                result = subprocess.run(
                    ["bash", str(ROOT / script)],
                    cwd=self.base,
                    env=environment,
                    text=True,
                    capture_output=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Run tests from the project root", result.stderr)

    def test_query_requires_nonempty_caller_context_before_downloading(self):
        workspace = self.base / "query-workspace"
        workspace.mkdir()
        context = {
            **self.env,
            "ADAPTER_DIR": str(ROOT / "packages/codex"),
            "WORKSPACE": str(workspace),
        }
        for variable in ("ADAPTER_DIR", "WORKSPACE", "ARCHES"):
            for value in (None, ""):
                with self.subTest(variable=variable, value=value):
                    environment = dict(context)
                    environment.pop(variable, None)
                    if value is not None:
                        environment[variable] = value
                    result = subprocess.run(
                        ["bash", str(ROOT / "packages/codex/query")],
                        env=environment,
                        text=True,
                        capture_output=True,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(f"{variable} must", result.stderr)
                    self.assertFalse((workspace / "release.json").exists())

    def test_directory_discovery_is_sequential_and_ignores_old_registry(self):
        self.adapter("second")
        self.adapter("first")
        self.env["PACKAGES"] = "does-not-exist"
        self.run_update()
        events = (self.base / "events").read_text().splitlines()
        self.assertEqual(events, [
            "first/query", "first/build", "first/build",
            "second/query", "second/build", "second/build",
        ])
        self.run_update()
        self.assertEqual(len(self.artifacts()), 4)
        self.assertFalse((self.base / "repo/.state/revisions").exists())

    def test_framework_exports_adapter_directory_to_both_hooks(self):
        directory = self.adapter("A directory with spaces", package="example-cli", stream="example-stable")
        (directory / "expected-directory").write_text(str(directory) + "\n")
        for hook in ("query", "build"):
            path = directory / hook
            script = path.read_text()
            check = (
                'EXPECTED_DIR=$(cat "$ADAPTER_DIR/expected-directory")\n'
                '[[ "$ADAPTER_DIR" == "$EXPECTED_DIR" ]]\n'
                '[[ -f "$FRAMEWORK_DIR/update.sh" ]]\n'
                '[[ -d "$WORKSPACE" ]]\n'
            )
            expected_arguments = 0 if hook == "query" else 3
            check += f'[[ "$#" == {expected_arguments} ]]\n'
            script = script.replace("set -Eeuo pipefail\n", "set -Eeuo pipefail\n" + check, 1)
            path.write_text(script)
        result = subprocess.run(
            ["bash", str(self.publisher / "update.sh")],
            cwd=self.base / "downloads",
            env=self.env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self.artifacts("example-stable")), 2)

    def test_directory_rename_does_not_change_identity_or_revision(self):
        directory = self.adapter("alice-bob-charlie", package="example-cli", stream="example-stable")
        self.run_update()
        original = {path: path.read_bytes() for path in self.artifacts()}
        directory.rename(directory.with_name("A descriptive directory"))
        self.run_update()
        self.assertEqual(self.versions("example-stable"), {"1.2.3-1"})
        self.assertEqual({path: path.read_bytes() for path in self.artifacts()}, original)
        self.assertEqual((self.base / "events").read_text().count("/build"), 2)

    def test_multiple_outputs_share_revision_and_resume_missing_package(self):
        self.adapter(package="example-cli example-common", stream="example-stable")
        self.run_update()
        self.assertEqual(len(self.artifacts()), 4)
        events = (self.base / "events").read_text()
        self.assertEqual(events.count("/build"), 2)
        missing = next(path for path in self.artifacts() if path.name.startswith("example-common_") and path.name.endswith("amd64.deb"))
        missing.unlink()
        retained = {path: path.read_bytes() for path in self.artifacts()}
        self.run_update()
        self.assertEqual(len(self.artifacts()), 4)
        self.assertEqual(self.versions("example-stable"), {"1.2.3-1"})
        self.assertEqual({path: path.read_bytes() for path in retained}, retained)
        self.assertEqual((self.base / "events").read_text().count("/build"), 3)
        self.run_update()
        self.assertEqual((self.base / "events").read_text().count("/build"), 3)

    def test_revision_allocation_considers_every_binary_package(self):
        self.adapter(package="example-cli example-common", stream="example-stable")
        self.legacy("example-common", "1.2.3-7", "amd64")
        self.run_update()
        self.assertEqual(self.versions("example-stable"), {"1.2.3-8"})

    def test_config_is_validated_without_executing_shell(self):
        directory = self.adapter()
        marker = self.base / "executed"
        invalid = [
            "release_stream=first\nbinary_packages=first-cli\n",
            f"RELEASE_STREAM=$(touch {marker})\nBINARY_PACKAGES=first-cli\n",
            "RELEASE_STREAM=first\nBINARY_PACKAGES=first-cli first-cli\n",
            "RELEASE_STREAM=first\nRELEASE_STREAM=second\nBINARY_PACKAGES=first-cli\n",
            "RELEASE_STREAM=first\nBINARY_PACKAGES=first-cli\nunknown=value\n",
            "RELEASE_STREAM=first\n",
        ]
        for config in invalid:
            with self.subTest(config=config):
                (directory / "config").write_text(config)
                self.run_update(expected=1)
                self.assertFalse(marker.exists())
                self.assertEqual(self.artifacts(), [])
        self.assertFalse((self.base / "events").exists())

    def test_duplicate_stream_identity_is_reported(self):
        self.adapter("first", stream="shared-stable")
        self.adapter("second", stream="shared-stable")
        result = self.run_update(expected=1)
        self.assertIn("Duplicate RELEASE_STREAM", result.stderr)
        self.assertNotIn("second/query", (self.base / "events").read_text())

    def test_incomplete_output_set_is_not_stored(self):
        directory = self.adapter(package="example-cli example-common")
        path = directory / "build"
        path.write_text(path.read_text().replace('for PACKAGE_NAME in $BINARY_PACKAGES;', 'for PACKAGE_NAME in example-cli;'))
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_invalid_second_output_does_not_store_first(self):
        directory = self.adapter(package="example-cli example-common")
        path = directory / "build"
        path.write_text(path.read_text().replace(
            "X-Build-Inputs-SHA256: $BUILD_INPUTS_SHA256",
            'X-Build-Inputs-SHA256: $(if [[ "$PACKAGE_NAME" == example-common ]]; then echo invalid; else echo "$BUILD_INPUTS_SHA256"; fi)',
        ))
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_same_name_streams_publish_multiple_versions(self):
        self.adapter("gimp-3.2", package="gimp", version="3.2.1")
        self.adapter("gimp-3.4", package="gimp", version="3.4.0")
        self.run_update()
        self.assertEqual(len(self.artifacts()), 4)
        for arch in ("amd64", "arm64"):
            self.assertIn("Version: 3.2.1-1", self.index(arch))
            self.assertIn("Version: 3.4.0-1", self.index(arch))
        self.run_update()
        self.assertEqual(len(self.artifacts()), 4)

    def test_same_name_same_upstream_streams_do_not_increment_forever(self):
        self.adapter("first", package="shared")
        self.adapter("second", package="shared")
        self.run_update()
        self.assertEqual(self.versions("first"), {"1.2.3-1"})
        self.assertEqual(self.versions("second"), {"1.2.3-2"})
        self.run_update()
        self.assertEqual(len(self.artifacts()), 4)

    def test_query_and_build_failures_do_not_block_other_streams(self):
        self.adapter("bad-query", query="exit 7\n")
        self.adapter("bad-build", build="exit 7\n")
        self.adapter()
        result = self.run_update(expected=1)
        self.assertIn("[bad-query] Update failed", result.stderr)
        self.assertIn("[bad-build] Update failed", result.stderr)
        self.assertEqual(len(self.artifacts()), 2)
        self.assertIn("Version: 1.2.3-1", self.index())

    def test_incomplete_directory_fails_without_blocking_valid_stream(self):
        (self.base / "adapters/broken").mkdir()
        self.adapter()
        self.run_update(expected=1)
        self.assertEqual(len(self.artifacts()), 2)

    def test_invalid_manifest_is_rejected_before_build(self):
        self.adapter(query="printf '1.2.3\\tamd64\\n1.2.3\\tmips\\n' > \"$WORKSPACE/targets.tsv\"\n")
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_multiple_versions_per_architecture_are_rejected(self):
        self.adapter(query="printf '1.2.3\\tamd64\\n1.2.4\\tamd64\\n' > \"$WORKSPACE/targets.tsv\"\n")
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_unterminated_manifest_is_rejected(self):
        self.adapter(query="printf '1.2.3\\tamd64' > \"$WORKSPACE/targets.tsv\"\n")
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_failed_build_does_not_store_leftover_artifact(self):
        self.adapter(build='touch "$3/leftover.deb"\nexit 7\n')
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_incorrect_package_or_checksum_metadata_is_rejected(self):
        directory = self.adapter()
        path = directory / "build"
        original = path.read_text()
        invalid_builds = [
            original.replace("Package: $PACKAGE_NAME", "Package: wrong-cli"),
            original.replace("$BUILD_INPUTS_SHA256", "wrong-checksum"),
        ]
        for replacement in invalid_builds:
            path.write_text(replacement)
            self.run_update(expected=1)
            self.assertEqual(self.artifacts(), [])

    def test_existing_artifact_cannot_be_overwritten(self):
        directory = self.adapter()
        self.run_update()
        existing = self.artifacts("first")[0]
        original_bytes = existing.read_bytes()
        metadata = fields(existing)
        architecture = metadata["architecture"]
        version = metadata["version"]
        checksum = metadata["x-build-inputs-sha256"]

        workspace = self.base / "changed-build"
        workspace.mkdir()
        output = workspace / "outputs"
        output.mkdir()
        replacement = output / existing.name
        build_environment = {
            **self.env,
            "ADAPTER_DIR": str(directory),
            "WORKSPACE": str(workspace),
            "PUBLISHER_STREAM": "first",
            "BINARY_PACKAGES": "first-cli",
            "BUILD_INPUTS_SHA256": checksum,
        }
        subprocess.run([
            str(directory / "build"), version, architecture, str(output),
        ], env=build_environment, check=True, capture_output=True)
        package_dir = workspace / f"package-first-cli-{architecture}"
        payload = package_dir / "usr/share/first-cli/stream"
        payload.write_text("different contents\n")
        subprocess.run([
            "dpkg-deb", "--build", str(package_dir), str(replacement),
        ], check=True, capture_output=True)

        result = subprocess.run([
            "python3", str(self.publisher / "lib/package-files.py"), "store",
            str(directory), version, architecture, checksum, str(output),
        ], env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(existing.read_bytes(), original_bytes)

    def test_revisions_are_automatic_without_policy_file(self):
        directory = self.adapter()
        self.assertFalse((directory / "revision-policy").exists())
        self.run_update()
        self.run_update()
        self.assertEqual(len(self.artifacts()), 2)
        self.assertEqual(self.versions("first"), {"1.2.3-1"})

    def test_checksum_ignores_timestamps_caches_and_monitoring_settings(self):
        directory = self.adapter()
        self.run_update()
        for path in directory.iterdir():
            path.touch()
        (directory / "__pycache__").mkdir()
        (directory / "__pycache__/ignored.pyc").write_bytes(b"cache")
        (directory / "stale-after-days").write_text("30\n")
        self.run_update()
        self.assertEqual(len(self.artifacts()), 2)
        self.assertEqual(self.versions("first"), {"1.2.3-1"})

    def test_recipe_changes_and_reverts_increment_and_retain_old_packages(self):
        directory = self.adapter()
        path = directory / "build"
        original = path.read_text()
        self.run_update()
        path.write_text(original + "\n# Changed recipe\n")
        self.run_update()
        self.run_update()
        self.assertEqual(self.versions("first"), {"1.2.3-1", "1.2.3-2"})
        path.write_text(original)
        self.run_update()
        self.assertEqual(self.versions("first"), {"1.2.3-1", "1.2.3-2", "1.2.3-3"})
        self.assertEqual(self.index().count("Package: first-cli\n"), 3)

    def test_configuration_permissions_and_dockerfile_affect_checksum(self):
        directory = self.adapter()
        (directory / "revision-env").write_text("TEST_BUILD_OPTION\n")
        self.env["TEST_BUILD_OPTION"] = "one"
        self.run_update()
        self.env["TEST_BUILD_OPTION"] = "two"
        self.run_update()
        (directory / "config").chmod(0o755)
        self.run_update()
        dockerfile = self.publisher / "Dockerfile"
        dockerfile.write_text(dockerfile.read_text() + "\n# Environment change\n")
        self.run_update()
        helper = self.publisher / "lib/package-files.py"
        helper.write_text(helper.read_text() + "\n# Not a packaging input\n")
        self.run_update()
        self.assertEqual(self.versions("first"), {f"1.2.3-{number}" for number in range(1, 5)})

    def test_new_upstream_resets_revision_without_rebuilding_history(self):
        directory = self.adapter()
        self.run_update()
        self.env["TEST_VERSION"] = "1.2.4"
        self.run_update()
        path = directory / "build"
        path.write_text(path.read_text() + "\n# Changed recipe\n")
        self.run_update()
        self.assertEqual(self.versions("first"), {"1.2.3-1", "1.2.4-1", "1.2.4-2"})

    def test_partial_build_resumes_from_embedded_metadata(self):
        self.adapter()
        self.env["TEST_FAIL_ARCH"] = "arm64"
        self.run_update(expected=1)
        self.assertEqual(len(self.artifacts()), 1)
        self.env.pop("TEST_FAIL_ARCH")
        self.run_update()
        self.assertEqual(len(self.artifacts()), 2)
        self.assertEqual(self.versions("first"), {"1.2.3-1"})

    def test_completely_failed_attempt_retries_same_next_revision(self):
        self.adapter()
        self.env["TEST_FAIL_ARCH"] = "amd64"
        self.run_update(expected=1)
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])
        self.env.pop("TEST_FAIL_ARCH")
        self.run_update()
        self.assertEqual(self.versions("first"), {"1.2.3-1"})

    def test_legacy_files_and_json_are_preserved(self):
        self.adapter(package="shared")
        old = self.legacy("shared", "1.2.3-3", "amd64")
        state = self.base / "repo/.state/revisions/trixie/shared.json"
        state.parent.mkdir(parents=True)
        state.write_text("legacy JSON is deliberately not read")
        self.run_update()
        self.assertTrue(old.exists())
        self.assertEqual(state.read_text(), "legacy JSON is deliberately not read")
        self.assertEqual(self.versions("first"), {"1.2.3-4"})
        self.assertIn("Version: 1.2.3-3", self.index())
        self.assertIn("Version: 1.2.3-4", self.index())

    def test_legacy_epoch_omitted_from_filename(self):
        self.adapter(version="1:1.2.3")
        old = self.legacy("first-cli", "1:1.2.3-3", "amd64")
        old.rename(old.with_name(old.name.replace("1:", "")))
        self.run_update()
        self.assertEqual(self.versions("first"), {"1:1.2.3-4"})

    def test_signing_failure_leaves_live_indexes_unchanged(self):
        self.adapter()
        self.run_update()
        distribution = self.base / "repo/dists/trixie"
        before = {}
        for path in distribution.rglob("*"):
            if path.is_file():
                before[path.relative_to(distribution)] = path.read_bytes()
        self.env["TEST_VERSION"] = "1.2.4"
        self.env["TEST_FAIL_SIGN"] = "1"
        self.run_update(expected=1)
        after = {}
        for path in distribution.rglob("*"):
            if path.is_file():
                after[path.relative_to(distribution)] = path.read_bytes()
        self.assertEqual(before, after)
        self.env.pop("TEST_FAIL_SIGN")
        self.run_update()
        self.assertEqual(len(self.artifacts()), 4)
        self.assertIn("Version: 1.2.4-1", self.index())

    def test_previous_by_hash_indexes_remain_available(self):
        self.adapter()
        self.run_update()
        path = self.base / "repo/dists/trixie/main/binary-amd64/Packages"
        digest = hashlib.sha512(path.read_bytes()).hexdigest()
        previous = path.read_bytes()
        self.env["TEST_VERSION"] = "1.2.4"
        self.run_update()
        self.assertEqual((path.parent / f"by-hash/SHA512/{digest}").read_bytes(), previous)
        self.assertIn("Acquire-By-Hash: yes", (self.base / "repo/dists/trixie/Release").read_text())

    def test_existing_identity_and_configuration_are_preserved(self):
        self.adapter()
        self.run_update()
        configuration = self.base / "repo/conf/distributions"
        original = configuration.read_text().replace("Private APT Repository", "Private Codex Repository")
        configuration.write_text(original)
        self.env["REPO_ORIGIN"] = "Ignored override"
        self.run_update()
        self.assertEqual(configuration.read_text(), original)
        release = self.base / "repo/dists/trixie/Release"
        self.assertIn("Origin: Private Codex Repository", release.read_text())
        self.env["GPG_KEY"] = "B" * 40
        self.run_update(expected=1)

    def test_architecture_selector_keeps_other_published_architecture(self):
        self.adapter()
        self.run_update()
        self.env["ARCHES"] = "amd64"
        self.env["TEST_VERSION"] = "1.2.4"
        self.run_update()
        self.assertIn("Version: 1.2.3-1", self.index("arm64"))
        self.assertNotIn("Version: 1.2.4-1", self.index("arm64"))

    def test_lock_prevents_overlapping_update(self):
        import fcntl

        self.adapter()
        state = self.base / "repo/.state"
        state.mkdir(parents=True)
        with (state / "update.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_update()
        self.assertIn("Update already running", result.stdout)
        self.assertEqual(self.artifacts(), [])

    def test_inactivity_warns_every_cycle_but_continues_processing(self):
        directory = self.adapter()
        (directory / "stale-after-days").write_text("30\n")
        for version in ("1.2.3", "1.2.4"):
            self.env["TEST_VERSION"] = version
            result = self.run_update()
            self.assertIn("UPSTREAM STREAM MAY BE INACTIVE", result.stderr)
        self.assertEqual(self.versions("first"), {"1.2.3-1", "1.2.4-1"})
        self.env["TEST_RELEASE_DATE"] = datetime.now(timezone.utc).isoformat()
        self.assertNotIn("UPSTREAM STREAM MAY BE INACTIVE", self.run_update().stderr)

    def test_invalid_monitoring_data_does_not_block_publication(self):
        directory = self.adapter()
        (directory / "stale-after-days").write_text("30\n")
        self.env["TEST_RELEASE_DATE"] = "not-a-date"
        self.assertIn("Cannot assess upstream activity", self.run_update().stderr)
        self.assertEqual(len(self.artifacts()), 2)

    def codex_fixture(
        self,
        *,
        wrapped=False,
        metadata_version="1.2.3",
        corrupt_digest=False,
        missing_arm64=False,
    ):
        shutil.copytree(
            ROOT / "packages/codex",
            self.base / "adapters/codex",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        assets = []
        for target in ("x86_64-unknown-linux-musl", "aarch64-unknown-linux-musl"):
            if missing_arm64 and target.startswith("aarch64"):
                continue
            name = f"codex-package-{target}.tar.gz"
            path = self.base / "downloads" / name
            prefix = "wrapper/" if wrapped else ""
            files = {
                "bin/codex": b"#!/bin/sh\necho fixture\n",
                "bin/codex-code-mode-host": b"#!/bin/sh\necho host\n",
                "codex-resources/bwrap": b"bundled bwrap",
                "codex-path/rg": b"bundled rg",
                "codex-package.json": json.dumps({
                    "version": metadata_version,
                    "entrypoint": "bin/codex",
                }).encode(),
            }
            with tarfile.open(path, "w:gz") as archive:
                for relative, data in files.items():
                    entry = tarfile.TarInfo(prefix + relative)
                    entry.size = len(data)
                    entry.mode = 0o644
                    archive.addfile(entry, io.BytesIO(data))
            digest = "0" * 64 if corrupt_digest else hashlib.sha256(path.read_bytes()).hexdigest()
            assets.append({
                "name": name,
                "digest": "sha256:" + digest,
                "browser_download_url": "https://fixtures.invalid/" + name,
            })
        (self.base / "downloads/release.json").write_text(json.dumps({
            "tag_name": "rust-v1.2.3", "draft": False, "prerelease": False,
            "published_at": "2000-01-01T00:00:00Z", "assets": assets,
        }))

    def run_codex_query(self, success=True):
        workspace = self.base / "codex-query"
        workspace.mkdir(exist_ok=True)
        adapter = self.base / "adapters/codex"
        environment = {
            **self.env,
            "ADAPTER_DIR": str(adapter),
            "WORKSPACE": str(workspace),
        }
        result = subprocess.run(
            [str(adapter / "query")],
            env=environment,
            text=True,
            capture_output=True,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_codex_query_rejects_malformed_json(self):
        self.codex_fixture()
        (self.base / "downloads/release.json").write_text("{not valid JSON")
        self.run_codex_query(success=False)
        self.assertFalse((self.base / "codex-query/targets.tsv").exists())

    def test_codex_query_rejects_invalid_release_tags(self):
        self.codex_fixture()
        path = self.base / "downloads/release.json"
        release = json.loads(path.read_text())
        for tag in ("v1.2.3", "rust-v1.2", "rust-v1.2.3-beta"):
            with self.subTest(tag=tag):
                release["tag_name"] = tag
                path.write_text(json.dumps(release))
                result = self.run_codex_query(success=False)
                self.assertIn("Unexpected release tag", result.stderr)

    def test_codex_query_rejects_missing_or_invalid_digests(self):
        self.codex_fixture()
        path = self.base / "downloads/release.json"
        original = path.read_text()
        invalid_digests = (
            None,
            "sha256:abc",
            "md5:" + "a" * 64,
            "sha256:" + "a" * 64 + "\n",
        )
        for digest in invalid_digests:
            with self.subTest(digest=digest):
                release = json.loads(original)
                asset = release["assets"][0]
                if digest is None:
                    del asset["digest"]
                else:
                    asset["digest"] = digest
                path.write_text(json.dumps(release))
                result = self.run_codex_query(success=False)
                self.assertIn("Missing or invalid SHA256 digest", result.stderr)

    def test_codex_query_rejects_invalid_download_urls(self):
        self.codex_fixture()
        path = self.base / "downloads/release.json"
        release = json.loads(path.read_text())
        invalid_urls = (
            "http://fixtures.invalid/archive.tar.gz",
            "https://fixtures.invalid/bad url.tar.gz",
            "https://fixtures.invalid/archive.tar.gz\n",
        )
        for url in invalid_urls:
            with self.subTest(url=url):
                release["assets"][0]["browser_download_url"] = url
                path.write_text(json.dumps(release))
                result = self.run_codex_query(success=False)
                self.assertIn("Invalid asset URL", result.stderr)

    def test_codex_query_returns_only_requested_architectures(self):
        self.codex_fixture()
        self.env["ARCHES"] = "arm64"
        self.run_codex_query()
        workspace = self.base / "codex-query"
        self.assertEqual((workspace / "targets.tsv").read_text(), "1.2.3\tarm64\n")
        self.assertEqual((workspace / "release-date").read_text(), "2000-01-01T00:00:00Z\n")
        downloads = json.loads((workspace / "assets.json").read_text())
        self.assertEqual(set(downloads), {"arm64"})
        self.assertEqual(downloads["arm64"]["version"], "1.2.3")
        self.assertRegex(downloads["arm64"]["sha256"], r"^[a-f0-9]{64}$")

    def test_codex_query_handles_no_matching_downloads(self):
        self.codex_fixture()
        path = self.base / "downloads/release.json"
        release = json.loads(path.read_text())
        release["assets"] = []
        path.write_text(json.dumps(release))
        result = self.run_codex_query()
        self.assertIn("No upstream archive for amd64", result.stderr)
        self.assertIn("No upstream archive for arm64", result.stderr)
        workspace = self.base / "codex-query"
        self.assertEqual((workspace / "targets.tsv").read_text(), "")
        self.assertEqual(json.loads((workspace / "assets.json").read_text()), {})

    def test_codex_layout_dependencies_and_embedded_metadata(self):
        self.codex_fixture()
        self.run_update()
        artifact = next(path for path in self.artifacts("codex") if path.name.endswith("amd64.deb"))
        metadata = fields(artifact)
        self.assertEqual(metadata["depends"], "bubblewrap, ripgrep")
        self.assertEqual(metadata["recommends"], "git")
        self.assertEqual(metadata["x-publisher-stream"], "codex")
        self.assertRegex(metadata["x-build-inputs-sha256"], r"^[a-f0-9]{64}$")
        contents = subprocess.check_output(["dpkg-deb", "--fsys-tarfile", str(artifact)])
        with tarfile.open(fileobj=io.BytesIO(contents)) as archive:
            for name in ("codex", "codex-code-mode-host"):
                link = archive.getmember(f"./usr/bin/{name}")
                self.assertEqual(link.linkname, f"../lib/openai-codex/bin/{name}")
                binary = archive.getmember(f"./usr/lib/openai-codex/bin/{name}")
                self.assertEqual(binary.mode, 0o755)
                self.assertEqual((binary.uid, binary.gid), (0, 0))
            for relative, executable in (("codex-resources/bwrap", "bwrap"), ("codex-path/rg", "rg")):
                wrapper = archive.extractfile(f"./usr/lib/openai-codex/{relative}")
                expected = f'#!/bin/sh\nexec /usr/bin/{executable} "$@"\n'
                self.assertEqual(wrapper.read(), expected.encode())
        self.assertIn(metadata["x-build-inputs-sha256"], self.index())

    def test_codex_missing_architecture_can_be_published_later(self):
        self.codex_fixture(missing_arm64=True)
        result = self.run_update()
        self.assertIn("No current upstream package for arm64", result.stderr)
        self.assertEqual(len(self.artifacts()), 1)
        self.codex_fixture()
        self.run_update()
        self.assertEqual(len(self.artifacts()), 2)
        self.assertEqual(self.versions("codex"), {"1.2.3-1"})

    def test_codex_wrapper_layout(self):
        self.codex_fixture(wrapped=True)
        self.run_update()
        self.assertEqual(len(self.artifacts()), 2)

    def test_codex_checksum_and_metadata_failures(self):
        self.codex_fixture(corrupt_digest=True)
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])
        self.codex_fixture(metadata_version="9.9.9")
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_codex_prereleases_are_rejected(self):
        self.codex_fixture()
        path = self.base / "downloads/release.json"
        release = json.loads(path.read_text())
        release["prerelease"] = True
        path.write_text(json.dumps(release))
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_archive_path_traversal_is_rejected(self):
        path = self.base / "unsafe.tar.gz"
        with tarfile.open(path, "w:gz") as archive:
            entry = tarfile.TarInfo("../escaped")
            entry.size = 1
            archive.addfile(entry, io.BytesIO(b"x"))
        result = subprocess.run([
            "python3", str(ROOT / "packages/codex/archive.py"),
            str(path), str(self.base / "extracted"), "1.2.3",
        ], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.base / "escaped").exists())

    def test_env_updates_preserve_unrelated_settings(self):
        path = self.base / ".env"
        path.write_text("# Settings\nCODEX_UID=42\nPACKAGES=codex\nREPO_UID=old\nGPG_KEY=old\n")
        command = ["python3", str(ROOT / "lib/write-env.py"), str(path), "123", "456", KEY]
        subprocess.run(command, check=True)
        subprocess.run(command, check=True)
        expected = (
            "# Settings\nCODEX_UID=42\nPACKAGES=codex\n"
            f"REPO_UID=123\nREPO_GID=456\nGPG_KEY={KEY}\n"
        )
        self.assertEqual(path.read_text(), expected)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
