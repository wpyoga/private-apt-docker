"""Offline imports of Debian's precompiled GIMP help, with real .deb files."""

import hashlib
import lzma
from pathlib import Path
import shutil
import subprocess

from publisher_test_support import ROOT, PublisherTestCase, fields


class GimpHelpTests(PublisherTestCase):
    def fixture(self, *, version="3.2.0-3", architecture="all", dependency=None,
                installed_size="999999"):
        adapter = self.base / "adapters/gimp-help-3.2"
        shutil.copytree(ROOT / "packages/gimp-help-3.2", adapter, dirs_exist_ok=True)
        names = ("gimp-help-common", "gimp-help-en", "gimp-help-de")
        (adapter / "config").write_text(
            'RELEASE_STREAM=gimp-help-3.2\nBINARY_PACKAGES="' + " ".join(names) + '"\n')
        paragraphs = []
        for name in names:
            root = self.base / "upstream" / name
            (root / "DEBIAN").mkdir(parents=True, exist_ok=True)
            language = "images" if name == "gimp-help-common" else name.removeprefix("gimp-help-")
            payload = root / "usr/share/gimp/3.0/help" / language
            payload.mkdir(parents=True, exist_ok=True)
            (payload / "index.html").write_text("<html>Manual fixture</html>\n")
            copyright_path = root / "usr/share/doc" / name / "copyright"
            copyright_path.parent.mkdir(parents=True, exist_ok=True)
            copyright_path.write_text("Upstream documentation license fixture\n")
            depends = "" if name == "gimp-help-common" else (
                dependency or f"gimp-help-common (= {version})")
            control = (f"Package: {name}\nVersion: {version}\nArchitecture: {architecture}\n"
                       "Maintainer: Debian Fixture <test@example.invalid>\n"
                       "Description: Precompiled manual fixture\n A continuation line.\n")
            if installed_size:
                control += f"Installed-Size: {installed_size}\n"
            if depends:
                control += f"Depends: {depends}\n"
            (root / "DEBIAN/control").write_text(control)
            archive = self.base / "downloads" / f"{name}_{version}_{architecture}.deb"
            subprocess.run(["dpkg-deb", "--build", root, archive], check=True, capture_output=True)
            paragraphs.append(control + f"Filename: pool/main/g/gimp-help/{archive.name}\n"
                              f"SHA256: {hashlib.sha256(archive.read_bytes()).hexdigest()}\n")
        index = self.base / "downloads/Packages.xz"
        index.write_bytes(lzma.compress(("\n".join(paragraphs) + "\n").encode()))

    def test_import_all_packages_once_for_both_indexes_and_resume(self):
        self.check_import("999999")

    def test_import_recalculates_missing_installed_size(self):
        self.check_import(None)

    def check_import(self, installed_size):
        self.fixture(installed_size=installed_size)
        self.run_update()
        self.assertEqual(len(self.artifacts()), 3)
        for archive in self.artifacts():
            row = fields(archive)
            self.assertEqual(row["architecture"], "all")
            self.assertEqual(row["version"], "3.2.0-3-1")
            self.assertGreater(int(row["installed-size"]), 0)
            self.assertLess(int(row["installed-size"]), 999999)
            if row["package"] != "gimp-help-common":
                self.assertEqual(row["depends"], "gimp-help-common (= 3.2.0-3-1)")
            for arch in ("amd64", "arm64"):
                self.assertIn(f"Filename: pool/main/gimp-help-3.2/{archive.name}", self.index(arch))
                self.assertIn(f"Installed-Size: {row['installed-size']}\n", self.index(arch))
        original = {path: path.read_bytes() for path in self.artifacts()}
        self.run_update()
        self.assertEqual({path: path.read_bytes() for path in self.artifacts()}, original)

    def test_reject_changed_dependencies_architecture_and_new_series(self):
        for kwargs in ({"dependency": "libc6"}, {"architecture": "amd64"}, {"version": "3.4.0-1"}):
            with self.subTest(kwargs=kwargs):
                self.fixture(**kwargs)
                self.run_update(expected=1)
                self.assertEqual(self.artifacts(), [])

    def test_reject_changed_download(self):
        self.fixture()
        with (self.base / "downloads/gimp-help-en_3.2.0-3_all.deb").open("ab") as stream:
            stream.write(b"tampered")
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])
