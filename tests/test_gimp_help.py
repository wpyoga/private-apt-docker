"""Offline imports of manuals within the GIMP 3.2 release family."""

import hashlib
import shutil
import subprocess

from publisher_test_support import ROOT, PublisherTestCase, fields


def create_help_fixtures(base, adapter, *, version="3.2.0-3", architecture="all",
                         dependency=None, installed_size="999999"):
    names = ("gimp-help-common", "gimp-help-en", "gimp-help-de")
    manifest = []
    for name in names:
        root = base / "upstream-help" / name
        (root / "DEBIAN").mkdir(parents=True, exist_ok=True)
        if name != "gimp-help-common":
            payload = root / "usr/share/gimp/3.0/help" / name.removeprefix("gimp-help-")
            payload.mkdir(parents=True, exist_ok=True)
            (payload / "index.html").write_text("<html>Manual fixture</html>\n")
        copyright_path = root / "usr/share/doc" / name / "copyright"
        copyright_path.parent.mkdir(parents=True, exist_ok=True)
        copyright_path.write_text("Upstream documentation license fixture\n")
        html_link = copyright_path.parent / "html"
        if not html_link.is_symlink():
            html_link.symlink_to("../../gimp/3.0/help")
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
        if name == "gimp-help-de":
            script = root / "DEBIAN/postinst"
            script.write_text("#!/bin/sh\n# Verified upstream migration fixture\nexit 0\n")
            script.chmod(0o755)
        archive = base / "downloads" / f"{name}_{version}_{architecture}.deb"
        existing = subprocess.check_output(["dpkg-deb", "--field", archive], text=True) if archive.exists() else ""
        if existing.strip() != control.strip():
            subprocess.run(["dpkg-deb", "--build", root, archive], check=True, capture_output=True)
        manifest.append("|".join((name, version, hashlib.sha256(archive.read_bytes()).hexdigest(),
                                   f"pool/main/g/gimp-help/{archive.name}")))
    (adapter / "help-assets").write_text("\n".join(manifest) + "\n")
    config = adapter / "config"
    original = config.read_text().split('BINARY_PACKAGES="')[1].split('"')[0].split()
    packages = [name for name in original if not name.startswith("gimp-help-")]
    config.write_text('RELEASE_STREAM=gimp-3.2\nBINARY_PACKAGES="' +
                      " ".join(packages + list(names)) + '"\n')


class GimpHelpTests(PublisherTestCase):
    def fixture(self, **kwargs):
        adapter = self.base / "adapters/gimp-3.2"
        shutil.copytree(ROOT / "packages/gimp-3.2", adapter, dirs_exist_ok=True)
        (adapter / "config").write_text('RELEASE_STREAM=gimp-3.2\nBINARY_PACKAGES=""\n')
        create_help_fixtures(self.base, adapter, **kwargs)
        # Test helpers alone here; test_gimp covers their combined outputs.
        (adapter / "query").write_text(
            '#!/bin/bash\nset -Eeuo pipefail\n'
            'python3 "$ADAPTER_DIR/help-metadata.py" query\n'
            'for ARCH in $ARCHES; do printf "3.2.6\\t%s\\n" "$ARCH"; done > "$WORKSPACE/targets.tsv"\n')
        (adapter / "build").write_text(
            '#!/bin/bash\nset -Eeuo pipefail\nbash "$ADAPTER_DIR/build-help" "$@"\n')

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
            self.assertEqual(row["version"], "3.2.6-1")
            self.assertEqual(row["x-upstream-version"], "3.2.0-3")
            self.assertGreater(int(row["installed-size"]), 0)
            self.assertLess(int(row["installed-size"]), 999999)
            if row["package"] != "gimp-help-common":
                self.assertEqual(row["depends"], "gimp-help-common (= 3.2.6-1)")
            if row["package"] == "gimp-help-de":
                control = self.base / "imported-german-control"
                subprocess.run(["dpkg-deb", "--control", archive, control], check=True, capture_output=True)
                self.assertFalse((control / "postinst").exists())
            for arch in ("amd64", "arm64"):
                self.assertIn(f"Filename: pool/main/gimp-3.2/{archive.name}", self.index(arch))
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

    def test_new_language_requires_explicit_package_declaration(self):
        self.fixture()
        manifest = self.base / "adapters/gimp-3.2/help-assets"
        extra = manifest.read_text().splitlines()[1].replace("gimp-help-en", "gimp-help-fr")
        with manifest.open("a") as stream:
            stream.write(extra + "\n")
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_manual_source_update_rebuilds_the_current_gimp_version(self):
        self.fixture()
        self.run_update()
        self.fixture(version="3.2.0-4")
        self.run_update()
        self.assertEqual(self.versions("gimp-3.2"), {"3.2.6-1", "3.2.6-2"})
        latest = [fields(path) for path in self.artifacts() if fields(path)["version"] == "3.2.6-2"]
        self.assertEqual(len(latest), 3)
        self.assertTrue(all(row["x-upstream-version"] == "3.2.0-4" for row in latest))
