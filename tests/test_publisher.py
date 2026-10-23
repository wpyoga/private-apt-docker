"""Offline integration tests. All downloads, signing and publication are stubbed."""

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

# The stub preserves package/version/architecture data across runner processes.
STUB = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

command = Path(sys.argv[0]).name
args = sys.argv[1:]
state = Path(os.environ["TEST_STATE"])
if command == "gpg":
    sys.exit(0)
if command == "curl":
    destination = args[args.index("-o") + 1]
    url = next(arg for arg in args if arg.startswith("https://"))
    name = "release.json" if url.endswith("/releases/latest") else url.rsplit("/", 1)[1]
    shutil.copyfile(Path(os.environ["TEST_DOWNLOADS"]) / name, destination)
    sys.exit(0)
operation = args[2]
packages = json.loads(state.read_text()) if state.exists() else []
with open(os.environ["TEST_EVENTS"], "a") as events:
    events.write(operation + "\n")
if operation == "list":
    for package in packages:
        if package["name"] == args[4]:
            print(f"{args[3]}|main|{package['arch']}: {package['name']} {package['version']}")
elif operation == "includedeb":
    artifact = args[4]
    values = [subprocess.check_output(["dpkg-deb", "-f", artifact, field], text=True).strip()
              for field in ("Package", "Version", "Architecture")]
    package = dict(zip(("name", "version", "arch"), values))
    packages = [p for p in packages if (p["name"], p["arch"]) != (package["name"], package["arch"])]
    packages.append(package)
    state.write_text(json.dumps(packages))
    shutil.copyfile(artifact, Path(os.environ["TEST_ARTIFACTS"]) / Path(artifact).name)
elif operation == "export":
    sys.exit(int(os.environ.get("TEST_FAIL_EXPORT", "0")))
else:
    raise SystemExit(f"Unexpected reprepro invocation: {args}")
'''


class PublisherTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "build").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="test-", dir=ROOT / "build")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        for directory in ("bin", "adapters", "downloads", "artifacts", "tmp"):
            (self.base / directory).mkdir()
        for command in ("gpg", "reprepro", "curl"):
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
            "REPO_DIR": str(self.base / "repo"),
            "PACKAGES_DIR": str(self.base / "adapters"),
            "PACKAGES": "first",
            "ARCHES": "amd64 arm64",
            "CODENAME": "trixie",
            "GPG_KEY": KEY,
            "GNUPGHOME": str(self.base / "unused-keyring"),
            "TMPDIR": str(self.base / "tmp"),
            "TEST_STATE": str(self.base / "state.json"),
            "TEST_EVENTS": str(self.base / "events"),
            "TEST_DOWNLOADS": str(self.base / "downloads"),
            "TEST_ARTIFACTS": str(self.base / "artifacts"),
        }

    def adapter(self, name="first", *, query=None, build=None, package=None):
        directory = self.base / "adapters" / name
        directory.mkdir()
        package = package or f"{name}-cli"
        (directory / "package-name").write_text(package + "\n")
        scripts = {
            "query": query if query is not None else "printf '1.2.3-1\\tamd64\\n1.2.3-1\\tarm64\\n' > \"$1/targets.tsv\"\n",
            "build": build if build is not None else f'''
mkdir -p "$1/build-$3/DEBIAN"
cat > "$1/build-$3/DEBIAN/control" <<CONTROL
Package: {package}
Version: $2
Architecture: $3
Maintainer: Test <test@localhost>
Description: Test fixture
CONTROL
dpkg-deb --build --root-owner-group "$1/build-$3" "$4"
''',
        }
        for hook, body in scripts.items():
            path = directory / hook
            path.write_text("#!/bin/bash\nset -Eeuo pipefail\n" + body)
            path.chmod(0o755)
        return directory

    def run_update(self, expected=0):
        result = subprocess.run(
            ["bash", str(self.publisher / "update.sh")], env=self.env, text=True, capture_output=True
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertEqual(list((self.base / "tmp").iterdir()), [], "Workspace leaked")
        return result

    def published(self):
        path = self.base / "state.json"
        return json.loads(path.read_text()) if path.exists() else []

    def test_multiple_adapters_and_duplicate_detection_per_architecture(self):
        self.adapter()
        self.adapter("second")
        self.env["PACKAGES"] = "first second"
        (self.base / "state.json").write_text(json.dumps([
            {"name": "first-cli", "version": "1.2.3-1", "arch": "amd64"}
        ]))
        self.run_update()
        self.assertEqual(len(self.published()), 4)
        self.assertEqual(len(list((self.base / "artifacts").glob("*.deb"))), 3)
        self.run_update()
        events = (self.base / "events").read_text().splitlines()
        self.assertEqual(events.count("includedeb"), 3)
        self.assertEqual(events.count("export"), 2)

    def test_query_and_build_failures_do_not_block_other_adapters(self):
        for stage in ("query", "build"):
            with self.subTest(stage=stage):
                name = f"bad-{stage}"
                self.adapter(name, **{stage: "exit 7\n"})
        self.adapter()
        self.env["PACKAGES"] = "bad-query bad-build first"
        result = self.run_update(expected=1)
        self.assertIn("[bad-query] Update failed", result.stderr)
        self.assertIn("[bad-build] Update failed", result.stderr)
        self.assertEqual(len(self.published()), 2)
        self.assertIn("export", (self.base / "events").read_text())

    def test_failed_build_with_leftover_artifact_is_not_published(self):
        self.adapter(build='touch "$4"\nexit 7\n')
        self.run_update(expected=1)
        self.assertEqual(self.published(), [])

    def test_invalid_artifact_metadata_is_rejected(self):
        directory = self.adapter()
        path = directory / "build"
        path.write_text(path.read_text().replace("Package: first-cli", "Package: wrong-cli"))
        self.run_update(expected=1)
        self.assertEqual(self.published(), [])

    def test_invalid_target_manifest_is_rejected_before_build(self):
        self.adapter(query="printf '1.2.3-1\\tamd64\\n1.2.3-1\\tmips\\n' > \"$1/targets.tsv\"\n")
        self.run_update(expected=1)
        self.assertEqual(self.published(), [])

    def test_target_manifest_requires_complete_rows(self):
        self.adapter(query="printf '1.2.3-1\\tamd64' > \"$1/targets.tsv\"\n")
        self.run_update(expected=1)
        self.assertEqual(self.published(), [])

    def test_unknown_adapter_is_rejected_before_repository_initialization(self):
        self.env["PACKAGES"] = "../unknown"
        self.run_update(expected=1)
        self.assertFalse((self.base / "repo/conf/distributions").exists())

    def test_duplicate_package_names_are_rejected(self):
        self.adapter()
        self.adapter("second", package="first-cli")
        self.env["PACKAGES"] = "first second"
        self.run_update(expected=1)
        self.assertFalse((self.base / "repo/conf/distributions").exists())

    def test_empty_targets_are_a_successful_noop(self):
        self.adapter(query=': > "$1/targets.tsv"\n')
        self.run_update()
        self.assertEqual(self.published(), [])

    def test_existing_repository_identity_is_preserved(self):
        self.adapter()
        self.run_update()
        configuration = self.base / "repo/conf/distributions"
        original = configuration.read_text().replace("Private APT Repository", "Private Codex Repository")
        configuration.write_text(original)
        self.env["REPO_ORIGIN"] = "Changed identity"
        self.run_update()
        self.assertEqual(configuration.read_text(), original)

    def test_signing_key_or_architecture_mismatch_is_rejected(self):
        self.adapter()
        self.run_update()
        self.env["GPG_KEY"] = "B" * 40
        self.run_update(expected=1)
        self.env["GPG_KEY"] = KEY
        self.env["ARCHES"] = "amd64 arm64 mips"
        self.run_update(expected=1)

    def test_export_failure_marks_cycle_failed(self):
        self.adapter()
        self.env["TEST_FAIL_EXPORT"] = "1"
        self.run_update(expected=1)
        self.assertEqual(len(self.published()), 2)

    def test_repository_lock_prevents_second_updater(self):
        import fcntl

        self.adapter()
        state = self.base / "repo/.state"
        state.mkdir(parents=True)
        with (state / "update.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_update()
        self.assertIn("Update already running", result.stdout)
        self.assertEqual(self.published(), [])

    def codex_fixture(self, *, wrapped=False, metadata_version=None, corrupt_digest=False, version="1.2.3"):
        adapter = self.base / "adapters/codex"
        if not adapter.exists():
            shutil.copytree(ROOT / "packages/codex", adapter, ignore=shutil.ignore_patterns("__pycache__"))
        self.env["PACKAGES"] = "codex"
        if metadata_version is None:
            metadata_version = version
        assets = []
        for target in ("x86_64-unknown-linux-musl", "aarch64-unknown-linux-musl"):
            name = f"codex-package-{target}.tar.gz"
            path = self.base / "downloads" / name
            prefix = "wrapper/" if wrapped else ""
            files = {
                "bin/codex": b"#!/bin/sh\necho fixture\n",
                "bin/codex-code-mode-host": b"#!/bin/sh\necho host\n",
                "codex-resources/bwrap": b"bundled bwrap",
                "codex-path/rg": b"bundled rg",
                "codex-package.json": json.dumps({
                    "version": metadata_version, "entrypoint": "bin/codex"
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
            "tag_name": f"rust-v{version}", "draft": False, "prerelease": False, "assets": assets
        }))

    def test_codex_build_layout_metadata_and_system_tools(self):
        self.codex_fixture()
        self.run_update()
        self.assertEqual(len(self.published()), 2)
        artifact = self.base / "artifacts/codex-cli_1.2.3-1_amd64.deb"
        control = subprocess.check_output(["dpkg-deb", "-f", str(artifact)], text=True)
        self.assertIn("Depends: bubblewrap, ripgrep", control)
        self.assertIn("Recommends: git", control)
        contents = subprocess.check_output(["dpkg-deb", "--fsys-tarfile", str(artifact)])
        with tarfile.open(fileobj=io.BytesIO(contents)) as archive:
            for name in ("codex", "codex-code-mode-host"):
                link = archive.getmember(f"./usr/bin/{name}")
                self.assertTrue(link.issym())
                self.assertEqual(link.linkname, f"../lib/openai-codex/bin/{name}")
                binary = archive.getmember(f"./usr/lib/openai-codex/bin/{name}")
                self.assertEqual(binary.mode, 0o755)
                self.assertEqual((binary.uid, binary.gid), (0, 0))
            for relative, executable in (("codex-resources/bwrap", "bwrap"), ("codex-path/rg", "rg")):
                path = f"./usr/lib/openai-codex/{relative}"
                self.assertEqual(archive.getmember(path).mode, 0o755)
                self.assertEqual(archive.extractfile(path).read(), f'#!/bin/sh\nexec /usr/bin/{executable} "$@"\n'.encode())

    def test_codex_single_wrapper_directory(self):
        self.codex_fixture(wrapped=True)
        self.run_update()
        self.assertEqual(len(self.published()), 2)

    def test_codex_checksum_failure(self):
        self.codex_fixture(corrupt_digest=True)
        self.run_update(expected=1)
        self.assertEqual(self.published(), [])

    def test_codex_metadata_version_mismatch(self):
        self.codex_fixture(metadata_version="9.9.9")
        self.run_update(expected=1)
        self.assertEqual(self.published(), [])

    def test_codex_prerelease_or_missing_digest_rejected(self):
        self.codex_fixture()
        path = self.base / "downloads/release.json"
        release = json.loads(path.read_text())
        release["prerelease"] = True
        path.write_text(json.dumps(release))
        self.run_update(expected=1)
        release["prerelease"] = False
        del release["assets"][0]["digest"]
        path.write_text(json.dumps(release))
        self.run_update(expected=1)
        self.assertEqual(self.published(), [])

    def revision_state(self):
        path = self.base / "repo/.state/revisions/trixie/codex-cli.json"
        return json.loads(path.read_text())["releases"]

    def published_versions(self):
        return {package["arch"]: package["version"] for package in self.published()}

    def test_automatic_revision_stable_across_polls_and_timestamps(self):
        self.codex_fixture()
        self.run_update()
        self.assertEqual(self.published_versions(), {"amd64": "1.2.3-1", "arm64": "1.2.3-1"})
        adapter = self.base / "adapters/codex"
        for path in adapter.iterdir():
            path.touch()
        (adapter / "__pycache__").mkdir()
        (adapter / "__pycache__/ignored.pyc").write_bytes(b"cache")
        self.run_update()
        self.assertEqual((self.base / "events").read_text().splitlines().count("includedeb"), 2)
        record = self.revision_state()["1.2.3"]
        self.assertEqual(record["revision"], 1)
        self.assertEqual(record["published"], ["amd64", "arm64"])

    def test_packaging_change_increments_revision_for_both_architectures(self):
        self.codex_fixture()
        self.run_update()
        path = self.base / "adapters/codex/build"
        original = path.read_text()
        path.write_text(original + "\n# Changed packaging recipe\n")
        self.run_update()
        self.assertEqual(self.published_versions(), {"amd64": "1.2.3-2", "arm64": "1.2.3-2"})
        self.run_update()
        self.assertEqual(self.revision_state()["1.2.3"]["revision"], 2)
        # Reverting a recipe still needs a newer Debian version.
        path.write_text(original)
        self.run_update()
        self.assertEqual(self.revision_state()["1.2.3"]["revision"], 3)

    def test_automatic_revisions_are_isolated_between_packages(self):
        for name in ("first", "second"):
            directory = self.adapter(name, query="printf '1.2.3\\tamd64\\n' > \"$1/targets.tsv\"\n")
            (directory / "revision-policy").write_text("automatic\n")
        self.env["PACKAGES"] = "first second"
        self.run_update()
        path = self.base / "adapters/first/build"
        path.write_text(path.read_text() + "\n# Changed first package\n")
        self.run_update()
        versions = {package["name"]: package["version"] for package in self.published()}
        self.assertEqual(versions, {"first-cli": "1.2.3-2", "second-cli": "1.2.3-1"})

    def test_executable_permission_change_increments_revision(self):
        self.codex_fixture()
        self.run_update()
        path = self.base / "adapters/codex/archive.py"
        path.chmod(0o755)
        self.run_update()
        self.assertEqual(self.revision_state()["1.2.3"]["revision"], 2)

    def test_build_environment_and_declared_configuration_changes_increment_revision(self):
        self.codex_fixture()
        (self.base / "adapters/codex/revision-env").write_text("TEST_BUILD_OPTION\n")
        self.env["TEST_BUILD_OPTION"] = "one"
        self.run_update()
        self.env["TEST_BUILD_OPTION"] = "two"
        self.run_update()
        self.assertEqual(self.revision_state()["1.2.3"]["revision"], 2)
        dockerfile = self.publisher / "Dockerfile"
        dockerfile.write_text(dockerfile.read_text() + "\n# Changed environment\n")
        self.run_update()
        self.assertEqual(self.revision_state()["1.2.3"]["revision"], 3)

    def test_new_upstream_release_resets_revision(self):
        self.codex_fixture()
        self.run_update()
        path = self.base / "adapters/codex/build"
        path.write_text(path.read_text() + "\n# Packaging change\n")
        self.run_update()
        self.codex_fixture(version="1.2.4")
        self.run_update()
        self.assertEqual(self.published_versions(), {"amd64": "1.2.4-1", "arm64": "1.2.4-1"})
        self.assertEqual(self.revision_state()["1.2.3"]["revision"], 2)
        self.assertEqual(self.revision_state()["1.2.4"]["revision"], 1)

    def test_migration_uses_highest_published_revision_across_architectures(self):
        self.codex_fixture()
        (self.base / "state.json").write_text(json.dumps([
            {"name": "codex-cli", "version": "1.2.3-2", "arch": "amd64"},
            {"name": "codex-cli", "version": "1.2.3-3", "arch": "arm64"},
        ]))
        # Legacy environment settings no longer override automatic revisions.
        self.env["DEB_REVISION"] = "3"
        self.run_update()
        self.assertEqual(self.published_versions(), {"amd64": "1.2.3-4", "arm64": "1.2.3-4"})
        self.run_update()
        self.assertEqual(self.revision_state()["1.2.3"]["revision"], 4)

    def test_failed_build_reuses_reserved_revision(self):
        self.codex_fixture(corrupt_digest=True)
        self.run_update(expected=1)
        reserved = self.revision_state()["1.2.3"]
        self.assertEqual(reserved["revision"], 1)
        self.assertEqual(reserved["published"], [])
        self.run_update(expected=1)
        self.assertEqual(self.revision_state()["1.2.3"], reserved)
        self.codex_fixture()
        self.run_update()
        self.assertEqual(self.revision_state()["1.2.3"]["revision"], 1)
        self.assertEqual(len(self.published()), 2)

    def test_partial_publication_resumes_same_revision(self):
        self.codex_fixture()
        path = self.base / "adapters/codex/build"
        path.write_text(path.read_text().replace(
            'output=$4',
            'output=$4\nif [[ "$arch" == arm64 && "${TEST_FAIL_ARM64:-}" == 1 ]]; then exit 7; fi'
        ))
        self.env["TEST_FAIL_ARM64"] = "1"
        self.run_update(expected=1)
        self.assertEqual(self.published_versions(), {"amd64": "1.2.3-1"})
        self.assertEqual(self.revision_state()["1.2.3"]["published"], ["amd64"])
        self.env["TEST_FAIL_ARM64"] = "0"
        self.run_update()
        self.assertEqual(self.published_versions(), {"amd64": "1.2.3-1", "arm64": "1.2.3-1"})
        self.assertEqual((self.base / "events").read_text().splitlines().count("includedeb"), 2)

    def test_new_architecture_reuses_existing_revision(self):
        self.codex_fixture()
        self.env["ARCHES"] = "amd64"
        self.run_update()
        configuration = self.base / "repo/conf/distributions"
        configuration.write_text(configuration.read_text().replace("Architectures: amd64", "Architectures: amd64 arm64"))
        self.env["ARCHES"] = "amd64 arm64"
        self.run_update()
        self.assertEqual(self.published_versions(), {"amd64": "1.2.3-1", "arm64": "1.2.3-1"})

    def test_missing_publication_record_is_recovered_from_repository(self):
        self.codex_fixture()
        self.run_update()
        path = self.base / "repo/.state/revisions/trixie/codex-cli.json"
        state = json.loads(path.read_text())
        state["releases"]["1.2.3"]["published"] = []
        path.write_text(json.dumps(state))
        self.run_update()
        self.assertEqual(self.revision_state()["1.2.3"]["published"], ["amd64", "arm64"])
        self.assertEqual((self.base / "events").read_text().splitlines().count("includedeb"), 2)

    def test_corrupt_revision_state_fails_without_republishing(self):
        self.codex_fixture()
        self.run_update()
        path = self.base / "repo/.state/revisions/trixie/codex-cli.json"
        path.write_text('{"schema": 999, "releases": {}}')
        self.run_update(expected=1)
        self.assertEqual((self.base / "events").read_text().splitlines().count("includedeb"), 2)

    def test_archive_path_traversal_is_rejected(self):
        path = self.base / "unsafe.tar.gz"
        with tarfile.open(path, "w:gz") as archive:
            entry = tarfile.TarInfo("../escaped")
            entry.size = 1
            archive.addfile(entry, io.BytesIO(b"x"))
        result = subprocess.run([
            "python3", str(ROOT / "packages/codex/archive.py"), str(path),
            str(self.base / "extracted"), "1.2.3",
        ], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.base / "escaped").exists())

    def test_env_update_preserves_existing_settings(self):
        path = self.base / ".env"
        path.write_text("# Existing settings\nCODEX_UID=42\nPACKAGES=codex\nREPO_UID=old\nGPG_KEY=old\n")
        command = ["python3", str(ROOT / "lib/write-env.py"), str(path), "123", "456", KEY]
        subprocess.run(command, check=True)
        subprocess.run(command, check=True)
        self.assertEqual(path.read_text(),
            f"# Existing settings\nCODEX_UID=42\nPACKAGES=codex\nREPO_UID=123\nREPO_GID=456\nGPG_KEY={KEY}\n")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
