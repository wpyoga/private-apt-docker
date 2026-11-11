"""Offline unchanged-import tests with real Debian archives and fixed ELF headers."""

import hashlib
import json
import shutil
import subprocess

from tests.lib.publisher_test_support import ROOT, PublisherTestCase, fields


class OpenShellTests(PublisherTestCase):
    def fixture(self, *, missing_arm64=False, missing_path=None, wrong_machine=False,
                installed_size=None, version="0.1.8-1", invalid_script=False):
        adapter = self.base / "adapters/openshell"
        if not adapter.exists():
            shutil.copytree(ROOT / "packages/redistribute/openshell", adapter)
        self.env["REPOSITORY_MODE"] = "redistribute"
        assets = []
        for architecture, machine in (("amd64", 62), ("arm64", 183)):
            if architecture == "arm64" and missing_arm64:
                continue
            stage = self.base / f"stage-{architecture}"
            shutil.rmtree(stage, ignore_errors=True)
            (stage / "DEBIAN").mkdir(parents=True)
            control = (
                f"Package: openshell\nVersion: {version}\nArchitecture: {architecture}\n"
                "Maintainer: NVIDIA <upstream@example.com>\n"
                "Pre-Depends: init-system-helpers (>= 1.54~)\n"
                "Description: OpenShell fixture\n")
            if installed_size is not None:
                control += f"Installed-Size: {installed_size}\n"
            (stage / "DEBIAN/control").write_text(control)
            (stage / "DEBIAN/postinst").write_text("#!/bin/sh\nexit 99\n")
            (stage / "DEBIAN/postinst").chmod(0o755)
            for name in ("usr/bin/openshell", "usr/bin/openshell-gateway", "usr/bin/openshell-prover",
                         "usr/libexec/openshell/openshell-driver-vm",
                         "usr/lib/systemd/user/openshell-gateway.service",
                         "usr/share/doc/openshell/copyright"):
                if name == missing_path:
                    continue
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                if name.startswith(("usr/bin", "usr/libexec")):
                    header = bytearray(20)
                    header[:6] = b"\x7fELF\x02\x01"
                    header[18:20] = (0 if wrong_machine else machine).to_bytes(2, "little")
                    path.write_bytes(header + b"x" * 2048)
                    path.chmod(0o755)
                else:
                    path.write_text("fixture\n")
            destination = self.base / f"downloads/openshell_{version}_{architecture}.deb"
            subprocess.run(["dpkg-deb", "--build", "--root-owner-group", str(stage), str(destination)],
                           check=True, capture_output=True)
            assets.append({"name": destination.name,
                           "browser_download_url": f"https://example.test/{destination.name}",
                           "digest": "sha256:" + hashlib.sha256(destination.read_bytes()).hexdigest()})
        release = {"tag_name": "v0.1.8", "draft": False, "prerelease": False,
                   "published_at": "2026-11-10T18:14:00Z", "assets": assets}
        (self.base / "downloads/release.json").write_text(json.dumps(release))
        return adapter

    def test_original_bytes_metadata_and_service_are_preserved(self):
        self.fixture()
        self.run_update()
        for path in self.artifacts():
            self.assertEqual(path.read_bytes(), (self.base / "downloads" / path.name).read_bytes())
            metadata = fields(path)
            self.assertEqual(metadata["version"], "0.1.8-1")
            self.assertEqual(metadata["maintainer"], "NVIDIA <upstream@example.com>")
            self.assertNotIn("installed-size", metadata)
            self.assertNotIn("x-publisher-stream", metadata)
        index = self.index()
        self.assertIn("X-Publisher-Stream: openshell", index)
        self.assertIn("X-Import-Recipe-SHA256: ", index)
        self.assertIn("X-Upstream-URL: https://example.test/", index)
        self.assertIn("Installed-Size: 9\n", index)
        records = list((self.base / "repo/.state/imports/openshell").glob("*.json"))
        self.assertEqual(len(records), 2)

    def test_recipe_change_revalidates_without_new_revision_and_then_settles(self):
        adapter = self.fixture(installed_size=999999)
        self.run_update()
        before = {path.name: path.read_bytes() for path in self.artifacts()}
        (adapter / "comment").write_text("Changed validation recipe\n")
        changed = self.run_update()
        self.assertIn("Stored:", changed.stdout)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.artifacts()})
        self.assertNotIn("Installed-Size: 999999", self.index())
        settled = self.run_update()
        self.assertIn("Already stored:", settled.stdout)

    def test_missing_architecture_is_added_later_without_rewriting_existing(self):
        self.fixture(missing_arm64=True)
        self.run_update()
        original = self.artifacts()[0].read_bytes()
        self.fixture()
        self.run_update()
        self.assertEqual(len(self.artifacts()), 2)
        self.assertEqual(self.artifacts()[0].read_bytes(), original)

    def test_changed_upstream_bytes_at_same_version_are_rejected(self):
        self.fixture()
        self.run_update()
        before = {path.name: path.read_bytes() for path in self.artifacts()}
        self.fixture(installed_size=12345)
        result = self.run_update(expected=1)
        self.assertIn("Upstream changed bytes", result.stderr)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.artifacts()})

    def test_corrupt_download_is_rejected(self):
        self.fixture()
        path = self.base / "downloads/openshell_0.1.8-1_amd64.deb"
        path.write_bytes(b"corrupted")
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_changed_layout_or_architecture_is_rejected(self):
        self.fixture(missing_path="usr/bin/openshell-prover")
        result = self.run_update(expected=1)
        self.assertIn("missing upstream paths", result.stderr)
        self.assertEqual(self.artifacts(), [])

    def test_wrong_elf_machine_is_rejected(self):
        self.fixture(wrong_machine=True)
        result = self.run_update(expected=1)
        self.assertIn("invalid amd64 executable", result.stderr)
        self.assertEqual(self.artifacts(), [])

    def test_missing_provenance_is_recovered_by_revalidation(self):
        self.fixture()
        self.run_update()
        record = next((self.base / "repo/.state/imports/openshell").glob("*.json"))
        record.unlink()
        self.run_update()
        self.assertTrue(record.exists())

    def test_invalid_release_digest_is_rejected(self):
        self.fixture()
        path = self.base / "downloads/release.json"
        release = json.loads(path.read_text())
        release["assets"][0]["digest"] = None
        path.write_text(json.dumps(release))
        result = self.run_update(expected=1)
        self.assertIn("Missing or invalid SHA256", result.stderr)

    def test_upstream_debian_revision_is_preserved(self):
        self.fixture(version="0.1.8-2")
        self.run_update()
        self.assertEqual({fields(path)["version"] for path in self.artifacts()}, {"0.1.8-2"})

    def test_duplicate_assets_are_rejected(self):
        self.fixture()
        path = self.base / "downloads/release.json"
        release = json.loads(path.read_text())
        release["assets"].append(release["assets"][0])
        path.write_text(json.dumps(release))
        result = self.run_update(expected=1)
        self.assertIn("Expected one Debian package", result.stderr)

    def test_corrupt_stored_bytes_prevent_publication(self):
        self.fixture()
        self.run_update()
        original_index = self.index()
        path = self.artifacts()[0]
        path.write_bytes(path.read_bytes() + b"changed")
        result = self.run_update(expected=1)
        self.assertIn("digest mismatch", result.stderr)
        self.assertEqual(self.index(), original_index)
