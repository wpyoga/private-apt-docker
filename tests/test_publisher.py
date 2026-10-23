"""Offline integration tests. All downloads, signing and publication are stubbed."""

import hashlib
import io
import json
import os
from pathlib import Path
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
            ["bash", str(ROOT / "update.sh")], env=self.env, text=True, capture_output=True
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

    def codex_fixture(self, *, wrapped=False, metadata_version="1.2.3", corrupt_digest=False):
        self.env["PACKAGES_DIR"] = str(ROOT / "packages")
        self.env["PACKAGES"] = "codex"
        self.env["DEB_REVISION"] = "3"
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
            "tag_name": "rust-v1.2.3", "draft": False, "prerelease": False, "assets": assets
        }))

    def test_codex_build_layout_metadata_and_system_tools(self):
        self.codex_fixture()
        self.run_update()
        self.assertEqual(len(self.published()), 2)
        artifact = self.base / "artifacts/codex-cli_1.2.3-3_amd64.deb"
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
