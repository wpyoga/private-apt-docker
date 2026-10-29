"""Offline Cromite release selection, archive checks, and publisher integration."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
from unittest.mock import patch

from tests.lib.publisher_test_support import ROOT, PublisherTestCase, fields

SPEC = importlib.util.spec_from_file_location("cromite_bundle", ROOT / "packages/cromite/inspect-bundle.py")
BUNDLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUNDLE)
TAG = "v153.0.8010.37-" + "1" * 40
VERSION = "153.0.8010.37+20260915115100.git" + "1" * 40


class CromiteTests(PublisherTestCase):
    def fixture(self, mutation=None):
        shutil.copytree(ROOT / "packages/cromite", self.base / "adapters/cromite")
        bundle = self.base / "source/chrome-lin"
        bundle.mkdir(parents=True)
        for name in BUNDLE.REQUIRED_FILES:
            path = bundle / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if name in BUNDLE.BUNDLED_LIBRARIES or name in ("chrome", "chrome_sandbox", "chrome_crashpad_handler"):
                shutil.copyfile("/bin/true", path)
                path.chmod(0o755)
            else:
                path.write_text("fixture\n")
        (bundle / "locales/en-US.pak.info").write_text("build metadata\n")
        (bundle / "locales/fr.pak").write_text("locale\n")
        if mutation:
            mutation(bundle)
        self.archive = self.base / "downloads/chrome-lin64.tar.gz"
        with tarfile.open(self.archive, "w:gz") as archive:
            archive.add(bundle, arcname="chrome-lin")
        self.release = {
            "tag_name": TAG, "published_at": "2026-09-15T11:51:00Z",
            "draft": False, "prerelease": False,
            "assets": [{"name": self.archive.name,
                        "digest": "sha256:" + hashlib.sha256(self.archive.read_bytes()).hexdigest(),
                        "browser_download_url": "https://fixtures.invalid/" + self.archive.name}],
        }
        self.save_release()

    def save_release(self):
        (self.base / "downloads/release.json").write_text(json.dumps(self.release))

    def query(self, success=True):
        workspace = self.base / "query"
        workspace.mkdir(exist_ok=True)
        env = {**self.env, "ADAPTER_DIR": str(self.base / "adapters/cromite"), "WORKSPACE": str(workspace)}
        result = subprocess.run([str(self.base / "adapters/cromite/query")], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return workspace

    def test_query_and_arm64_only(self):
        self.fixture()
        workspace = self.query()
        self.assertEqual((workspace / "targets.tsv").read_text(), VERSION + "\tamd64\n")
        self.env["ARCHES"] = "arm64"
        self.query()
        self.assertEqual((workspace / "targets.tsv").read_text(), "")
        self.assertEqual((workspace / "assets.json").read_text().strip(), "{}")

    def test_invalid_release(self):
        self.fixture()
        original = json.loads(json.dumps(self.release))
        changes = [
            {"tag_name": "v153.0.8010.37"}, {"published_at": "2026-09-15"},
            {"published_at": None}, {"draft": True}, {"prerelease": True},
            {"assets": None}, {"assets": original["assets"] * 2},
        ]
        for change in changes:
            with self.subTest(change=change):
                self.release = {**original, **change}
                self.save_release()
                self.query(False)

    def test_missing_and_invalid_asset(self):
        self.fixture()
        original = self.release["assets"][0].copy()
        for field, value in (("digest", None), ("digest", "sha256:bad"),
                             ("browser_download_url", "http://invalid/file")):
            with self.subTest(field=field, value=value):
                self.release["assets"] = [{**original, field: value}]
                self.save_release()
                self.query(False)
        self.release["assets"] = []
        self.save_release()
        self.assertEqual((self.query() / "targets.tsv").read_text(), "")

    def test_package_index_and_repeat_update(self):
        self.fixture()
        self.run_update()
        artifacts = self.artifacts("cromite")
        self.assertEqual(len(artifacts), 1)
        package = artifacts[0]
        metadata = fields(package)
        self.assertEqual(metadata["version"], VERSION + "-1")
        self.assertEqual(metadata["architecture"], "amd64")
        self.assertIn("Installed-Size: " + metadata["installed-size"], self.index())
        self.assertNotIn("Package: cromite\n", self.index("arm64"))
        destination = self.base / "unpacked"
        subprocess.run(["dpkg-deb", "-x", str(package), str(destination)], check=True, capture_output=True)
        self.assertEqual(list(destination.rglob("*.pak.info")), [])
        root = destination / "usr/lib/cromite"
        self.assertFalse((root / "chrome-wrapper").exists())
        self.assertTrue((root / "locales/fr.pak").is_file())
        for name in BUNDLE.BUNDLED_LIBRARIES:
            self.assertTrue((root / name).is_file())
        self.assertEqual((root / "chrome_sandbox").stat().st_mode & 0o6000, 0)
        size = subprocess.check_output(["du", "--summarize", "--block-size=1024", str(destination)], text=True).split()[0]
        self.assertEqual(metadata["installed-size"], size)
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        self.run_update()
        self.assertEqual(hashlib.sha256(package.read_bytes()).hexdigest(), digest)
        # A recipe change rebuilds only the current version at the next revision.
        with (self.base / "adapters/cromite/control.in").open("a") as output:
            output.write("X-Test-Recipe: changed\n")
        self.run_update()
        self.assertEqual(self.versions("cromite"), {VERSION + "-1", VERSION + "-2"})

    def test_checksum_failure(self):
        self.fixture()
        self.release["assets"][0]["digest"] = "sha256:" + "0" * 64
        self.save_release()
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_missing_runtime(self):
        self.fixture(lambda bundle: (bundle / "resources.pak").unlink())
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_archive_rejects_links_paths_and_extra_files(self):
        self.fixture()
        for name, kind in (("../escape", tarfile.REGTYPE), ("other/file", tarfile.REGTYPE),
                           ("chrome-lin/link", tarfile.SYMTYPE), ("chrome-lin/device", tarfile.CHRTYPE),
                           ("chrome-lin/new-runtime", tarfile.REGTYPE)):
            with self.subTest(name=name):
                archive_path = self.base / "bad.tar.gz"
                with tarfile.open(self.archive) as source, tarfile.open(archive_path, "w:gz") as output:
                    for member in source:
                        output.addfile(member, source.extractfile(member) if member.isfile() else None)
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    member.linkname = "/etc/passwd" if kind == tarfile.SYMTYPE else ""
                    output.addfile(member, io.BytesIO())
                with self.assertRaises(ValueError):
                    BUNDLE.check_archive(archive_path)

    def test_wrong_architecture_and_unknown_dependency(self):
        self.fixture()
        path = self.base / "source/chrome-lin/chrome"
        data = bytearray(path.read_bytes())
        struct.pack_into("<H", data, 18, 183)
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "Wrong ELF architecture"):
            BUNDLE.check_elf(path, "amd64")
        if shutil.which("patchelf"):
            shutil.copyfile("/bin/true", path)
            subprocess.run(["patchelf", "--add-needed", "libunknown.so.1", str(path)], check=True, capture_output=True)
            with self.assertRaisesRegex(ValueError, "Unknown library"):
                BUNDLE.inspect_tree(path.parent, "amd64", ROOT / "packages/cromite/runtime-dependencies")

    def test_launcher_arguments_and_desktop(self):
        launcher = (ROOT / "packages/cromite/launcher.in").read_text()
        fake = self.base / "chrome"
        fake.write_text('#!/bin/bash\nprintf "%s\\n" "$CHROME_WRAPPER" "$CHROME_DESKTOP" "$@"\n')
        fake.chmod(0o755)
        script = self.base / "launcher"
        script.write_text(launcher.replace("exec /usr/lib/cromite/chrome", 'exec "' + str(fake) + '"'))
        output = subprocess.check_output(["bash", str(script), "two words", "", "https://example.org/?a=b&c=d"], text=True)
        self.assertEqual(output.splitlines(), ["/usr/bin/cromite", "cromite.desktop", "two words", "", "https://example.org/?a=b&c=d"])
        desktop = (ROOT / "packages/cromite/desktop.in").read_text()
        self.assertIn("Exec=cromite %U\n", desktop)
        self.assertIn("Icon=cromite\n", desktop)

    def test_symbol_baseline(self):
        with patch.object(BUNDLE, "readelf", return_value="Name: GLIBC_2.42"):
            with self.assertRaisesRegex(ValueError, "Unsupported Debian 13 symbol"):
                BUNDLE.check_versions(Path("fixture"))

    def test_duplicate_archive_path(self):
        self.fixture()
        path = self.base / "duplicate.tar.gz"
        with tarfile.open(self.archive) as source, tarfile.open(path, "w:gz") as output:
            for member in source:
                output.addfile(member, source.extractfile(member) if member.isfile() else None)
            member = tarfile.TarInfo("chrome-lin/chrome")
            output.addfile(member, io.BytesIO())
        with self.assertRaisesRegex(ValueError, "Duplicate archive path"):
            BUNDLE.check_archive(path)

    def test_build_rejects_arm64_and_inconsistent_asset(self):
        self.fixture()
        workspace = self.query()
        output = self.base / "output"
        output.mkdir()
        env = {**self.env, "ADAPTER_DIR": str(self.base / "adapters/cromite"),
               "WORKSPACE": str(workspace), "PUBLISHER_STREAM": "cromite",
               "BUILD_INPUTS_SHA256": "a" * 64}
        for arch, version, message in (("arm64", VERSION + "-1", "Unsupported Linux architecture"),
                                       ("amd64", "1.0-1", "Inconsistent asset")):
            result = subprocess.run([str(self.base / "adapters/cromite/build"), version, arch, str(output)],
                                    env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(message, result.stderr)
        self.assertEqual(list(output.iterdir()), [])
