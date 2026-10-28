"""Offline imports of manuals within the GIMP 3.2 release family."""

import shutil
import subprocess

from tests.lib.publisher_test_support import ROOT, PublisherTestCase, fields
from gimp_help_support import create_help_fixtures


class GimpHelpTests(PublisherTestCase):
    def fixture(self, **kwargs):
        adapter = self.base / "adapters/gimp-help-3.2"
        shutil.copytree(ROOT / "packages/gimp-help-3.2", adapter, dirs_exist_ok=True)
        (adapter / "config").write_text('RELEASE_STREAM=gimp-help-3.2\nBINARY_PACKAGES=""\n')
        create_help_fixtures(self.base, adapter, **kwargs)
        import lzma
        records = []
        for line in (adapter / "help-assets").read_text().splitlines():
            name, version, digest, filename = line.split("|")
            records.append(f"Package: {name}\nVersion: {version}\nArchitecture: all\nSHA256: {digest}\nFilename: {filename}\n")
        (adapter / "Packages.xz").write_bytes(lzma.compress("\n".join(records).encode()))
        (adapter / "query").write_text(
            '#!/bin/bash\nset -Eeuo pipefail\n'
            'cp "$ADAPTER_DIR/Packages.xz" "$WORKSPACE/Packages.xz"\n'
            'python3 "$ADAPTER_DIR/help-metadata.py" query\n'
        )

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
            self.assertEqual(row["version"], "1:3.2.0+deb3-1")
            self.assertEqual(row["x-upstream-version"], "3.2.0-3")
            self.assertGreater(int(row["installed-size"]), 0)
            self.assertLess(int(row["installed-size"]), 999999)
            if row["package"] != "gimp-help-common":
                self.assertEqual(row["depends"], "gimp-help-common (= 1:3.2.0+deb3-1)")
            if row["package"] == "gimp-help-de":
                control = self.base / "imported-german-control"
                subprocess.run(["dpkg-deb", "--control", archive, control], check=True, capture_output=True)
                self.assertFalse((control / "postinst").exists())
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

    def test_manual_source_update_selects_new_version(self):
        self.fixture()
        self.run_update()
        self.fixture(version="3.2.0-4")
        self.run_update()
        self.assertEqual(self.versions("gimp-help-3.2"), {"1:3.2.0+deb3-1", "1:3.2.0+deb4-1"})
        latest = [fields(path) for path in self.artifacts() if fields(path)["version"] == "1:3.2.0+deb4-1"]
        self.assertEqual(len(latest), 3)
        self.assertTrue(all(row["x-upstream-version"] == "3.2.0-4" for row in latest))

    def test_recipe_change_rebuilds_same_manual_release(self):
        self.fixture()
        self.run_update()
        adapter = self.base / "adapters/gimp-help-3.2"
        with (adapter / "build").open("a") as stream:
            stream.write("\n# Changed packaging recipe\n")
        self.run_update()
        self.assertEqual(self.versions("gimp-help-3.2"),
                         {"1:3.2.0+deb3-1", "1:3.2.0+deb3-2"})
