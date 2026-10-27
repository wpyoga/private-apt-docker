"""Offline tests for stream processing, revisions, and repository publication."""

from datetime import datetime, timezone
import hashlib
import subprocess
import unittest

from tests.lib.publisher_test_support import KEY, ROOT, PublisherTestCase, fields


class PublisherTests(PublisherTestCase):
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

    def test_architecture_independent_outputs_are_shared_and_resumed(self):
        directory = self.adapter(package="example-cli example-common")
        path = directory / "build"
        script = path.read_text().replace(
            'for PACKAGE_NAME in $BINARY_PACKAGES; do',
            'for PACKAGE_NAME in $BINARY_PACKAGES; do\n'
            '    PACKAGE_ARCHITECTURE="$ARCHITECTURE"\n'
            '    if [[ "$PACKAGE_NAME" == example-common ]]; then PACKAGE_ARCHITECTURE=all; fi')
        script = script.replace('Architecture: $ARCHITECTURE', 'Architecture: $PACKAGE_ARCHITECTURE')
        script = script.replace('${VERSION}_${ARCHITECTURE}.deb', '${VERSION}_${PACKAGE_ARCHITECTURE}.deb')
        path.write_text(script)
        self.run_update()
        self.assertEqual(len(self.artifacts()), 3)
        common = next(path for path in self.artifacts() if fields(path)["architecture"] == "all")
        for arch in ("amd64", "arm64"):
            self.assertIn(common.name, self.index(arch))
        common.unlink()
        self.run_update()
        self.assertEqual(len(self.artifacts()), 3)
        self.run_update()
        self.assertEqual(len(self.artifacts()), 3)

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
        self.assertIn("ERROR: [bad-build] Build failed for 1.2.3-1 (amd64)", result.stderr)
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
            "bash", str(self.publisher / "lib/store-packages.sh"),
            version, architecture, str(output),
        ], env=build_environment, text=True, capture_output=True)
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
        self.run_update()
        self.env["MAINTAINER"] = "New Maintainer <new@example.com>"
        self.run_update()
        (directory / "config").chmod(0o755)
        self.run_update()
        dockerfile = self.publisher / "Dockerfile"
        dockerfile.write_text(dockerfile.read_text() + "\n# Environment change\n")
        self.run_update()
        helper = self.publisher / "lib/resolve-builds.py"
        helper.write_text(helper.read_text() + "\n# Not a packaging input\n")
        self.run_update()
        self.assertEqual(self.versions("first"), {f"1.2.3-{number}" for number in range(1, 5)})

    def test_global_maintainer_change_rebuilds_every_stream(self):
        self.adapter("first")
        self.adapter("second")
        self.run_update()
        maintainer = "New Maintainer <new@example.com>"
        self.env["MAINTAINER"] = maintainer
        self.run_update()
        self.run_update()
        for stream in ("first", "second"):
            self.assertEqual(self.versions(stream), {"1.2.3-1", "1.2.3-2"})
            for artifact in self.artifacts(stream):
                metadata = fields(artifact)
                if metadata["version"] == "1.2.3-2":
                    self.assertEqual(metadata["maintainer"], maintainer)

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

    def test_central_repository_config_controls_published_identity(self):
        self.adapter()
        self.run_update()
        before = self.artifacts()
        self.env["REPO_NAME"] = "Another Repository"
        self.run_update()
        release = (self.base / "repo/dists/trixie/Release").read_text()
        self.assertIn("Origin: Another Repository", release)
        self.assertIn("Label: Another Repository", release)
        self.assertEqual(self.artifacts(), before)
        self.env["GPG_KEY"] = "invalid-fingerprint"
        self.run_update(expected=1)

    def test_missing_global_configuration_fails_before_writing(self):
        for variable in ("MAINTAINER", "REPO_NAME", "PACKAGES_DIR", "REPO_DIR"):
            for value in (None, ""):
                with self.subTest(variable=variable, value=value):
                    environment = dict(self.env)
                    environment.pop(variable, None)
                    if value is not None:
                        environment[variable] = value
                    result = subprocess.run(
                        ["bash", str(self.publisher / "update.sh")],
                        env=environment,
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(f"{variable} must", result.stderr)
                    self.assertFalse((self.base / "repo").exists())
        self.env["PACKAGES_DIR"] = str(self.base / "missing-adapters")
        result = self.run_update(expected=1)
        self.assertIn("PACKAGES_DIR does not exist", result.stderr)
        self.assertFalse((self.base / "repo").exists())

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

if __name__ == "__main__":
    unittest.main()
