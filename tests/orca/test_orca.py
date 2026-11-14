"""Offline Orca repack tests using real Debian packages and architecture fixtures."""

import hashlib
import io
import json
import shutil
import subprocess
import tarfile

from tests.lib.publisher_test_support import ROOT, PublisherTestCase, fields


class OrcaTests(PublisherTestCase):
    def fixture(self, *, missing_arm64=False, missing_path=None, wrong_machine=False,
                installed_size=None, package="orca-ide", version="1.4.258", link=False):
        adapter = self.base / "adapters/orca"
        if not adapter.exists():
            shutil.copytree(ROOT / "packages/repack/orca", adapter)
        assets = []
        for architecture, machine in (("amd64", 62), ("arm64", 183)):
            if architecture == "arm64" and missing_arm64:
                continue
            stage = self.base / f"stage-{architecture}"
            shutil.rmtree(stage, ignore_errors=True)
            (stage / "DEBIAN").mkdir(parents=True)
            control = (
                f"Package: {package}\nVersion: {version}\nArchitecture: {architecture}\n"
                "Maintainer: stablyai\nDepends: libgtk-3-0, python3\n"
                "Recommends: libappindicator3-1\n"
                "Description: Orca fixture\n Continued description\n")
            if installed_size is not None:
                control += f"Installed-Size: {installed_size}\n"
            (stage / "DEBIAN/control").write_text(control)
            (stage / "DEBIAN/postinst").write_text("#!/bin/bash\nexit 99\n")
            (stage / "DEBIAN/postinst").chmod(0o755)
            names = (
                "opt/Orca/orca-ide", "opt/Orca/chrome-sandbox",
                "opt/Orca/resources/bin/orca-ide", "opt/Orca/resources/app.asar",
                "opt/Orca/LICENSE.electron.txt", "opt/Orca/LICENSES.chromium.html",
                "usr/share/applications/orca-ide.desktop",
                "usr/share/icons/hicolor/256x256/apps/orca-ide.png",
                "usr/share/doc/orca-ide/changelog.gz",
            )
            for name in names:
                if name == missing_path:
                    continue
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                if name in ("opt/Orca/orca-ide", "opt/Orca/chrome-sandbox"):
                    header = bytearray(20)
                    header[:6] = b"\x7fELF\x02\x01"
                    header[18:20] = (0 if wrong_machine else machine).to_bytes(2, "little")
                    path.write_bytes(header + b"x" * 2048)
                    path.chmod(0o777)
                else:
                    path.write_text("fixture\n")
                    path.chmod(0o777 if name.endswith("bin/orca-ide") else 0o666)
            if link:
                (stage / "opt/Orca/external").symlink_to("/tmp/outside-orca")
            destination = self.base / f"downloads/orca-ide_1.4.258_{architecture}.deb"
            subprocess.run(["dpkg-deb", "--build", "--root-owner-group", str(stage), str(destination)],
                           check=True, capture_output=True)
            assets.append({"name": destination.name,
                           "browser_download_url": f"https://example.test/{destination.name}",
                           "digest": "sha256:" + hashlib.sha256(destination.read_bytes()).hexdigest()})
        release = {"tag_name": "v1.4.258", "draft": False, "prerelease": False,
                   "published_at": "2026-11-13T08:14:00Z", "assets": assets}
        (self.base / "downloads/release.json").write_text(json.dumps(release))
        return adapter

    def test_permissions_metadata_integration_and_index(self):
        self.fixture()
        self.run_update()
        self.assertEqual(len(self.artifacts()), 2)
        for artifact in self.artifacts():
            metadata = fields(artifact)
            self.assertEqual(metadata["version"], "1.4.258-1")
            self.assertEqual(metadata["maintainer"], self.env["MAINTAINER"])
            self.assertEqual(metadata["depends"], "libgtk-3-0, python3")
            self.assertEqual(metadata["recommends"], "libappindicator3-1")
            self.assertEqual(metadata["x-publisher-stream"], "stably-orca")
            self.assertGreater(int(metadata["installed-size"]), 0)
            self.assertIn(f"Installed-Size: {metadata['installed-size']}\n",
                          self.index(metadata["architecture"]))
            payload = subprocess.check_output(["dpkg-deb", "--fsys-tarfile", str(artifact)])
            with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
                for member in archive:
                    self.assertEqual(member.mode & 0o6022, 0, member.name)
                self.assertEqual(archive.getmember("./opt/Orca/orca-ide").mode, 0o755)
                self.assertEqual(archive.getmember("./opt/Orca/resources/bin/orca-ide").mode, 0o755)
                self.assertIn(b"MIT License", archive.extractfile(
                    "./usr/share/doc/orca-ide/copyright").read())
            control = self.base / f"control-{metadata['architecture']}"
            subprocess.run(["dpkg-deb", "--control", str(artifact), str(control)], check=True)
            self.assertEqual((control / "postinst").read_text(), "#!/bin/bash\nexit 99\n")

    def test_stale_installed_size_is_recalculated(self):
        self.fixture(installed_size=999999)
        self.run_update()
        for artifact in self.artifacts():
            self.assertLess(int(fields(artifact)["installed-size"]), 999999)
        self.assertNotIn("Installed-Size: 999999", self.index())

    def test_missing_architecture_can_resume_and_repeat_update_settles(self):
        self.fixture(missing_arm64=True)
        self.run_update()
        original = self.artifacts()[0].read_bytes()
        self.fixture()
        self.run_update()
        self.assertEqual(len(self.artifacts()), 2)
        self.assertEqual(self.artifacts()[0].read_bytes(), original)
        self.assertIn("Already stored:", self.run_update().stdout)

    def test_recipe_change_rebuilds_current_release(self):
        adapter = self.fixture()
        self.run_update()
        (adapter / "comment").write_text("Changed recipe\n")
        self.run_update()
        self.assertEqual({fields(path)["version"] for path in self.artifacts()},
                         {"1.4.258-1", "1.4.258-2"})

    def test_changed_layout_is_rejected(self):
        self.fixture(missing_path="opt/Orca/resources/app.asar")
        result = self.run_update(expected=1)
        self.assertIn("missing upstream paths", result.stderr)
        self.assertEqual(self.artifacts(), [])

    def test_wrong_machine_is_rejected(self):
        self.fixture(wrong_machine=True)
        result = self.run_update(expected=1)
        self.assertIn("invalid amd64 executable", result.stderr)
        self.assertEqual(self.artifacts(), [])

    def test_links_are_rejected_before_extracting(self):
        self.fixture(link=True)
        result = self.run_update(expected=1)
        self.assertIn("unexpected payload type", result.stderr)
        self.assertEqual(self.artifacts(), [])

    def test_wrong_package_identity_is_rejected(self):
        self.fixture(package="orca")
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_wrong_package_version_is_rejected(self):
        self.fixture(version="9.9.9")
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_corrupt_download_is_rejected(self):
        self.fixture()
        (self.base / "downloads/orca-ide_1.4.258_amd64.deb").write_bytes(b"corrupt")
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_invalid_release_metadata_is_rejected(self):
        self.fixture()
        path = self.base / "downloads/release.json"
        original = path.read_text()
        for change in ("tag", "prerelease", "digest", "url", "duplicate"):
            with self.subTest(change=change):
                release = json.loads(original)
                if change == "tag":
                    release["tag_name"] = "v1.4.258-rc.1"
                elif change == "prerelease":
                    release["prerelease"] = True
                elif change == "digest":
                    release["assets"][0]["digest"] = None
                elif change == "url":
                    release["assets"][0]["browser_download_url"] = "http://invalid/package.deb"
                else:
                    release["assets"].append(release["assets"][0])
                path.write_text(json.dumps(release))
                self.run_update(expected=1)
                self.assertEqual(self.artifacts(), [])

    def test_only_requested_architecture_is_built(self):
        self.fixture()
        self.env["ARCHES"] = "arm64"
        self.run_update()
        self.assertEqual([fields(path)["architecture"] for path in self.artifacts()], ["arm64"])
