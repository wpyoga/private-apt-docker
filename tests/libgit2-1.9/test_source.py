"""Offline release selection, backporting, packaging and index checks."""

import importlib.util
from pathlib import Path
import shutil
import subprocess

from tests.lib.publisher_test_support import ROOT, PublisherTestCase, fields

ADAPTER = ROOT / "packages/rebuild/libgit2-1.9"


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ADAPTER / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


METADATA = load_module("source-metadata")
PREPARE = load_module("prepare-source")


class SourceTests(PublisherTestCase):
    def test_selects_highest_stable_19_source(self):
        text = "\n\n".join(f"Package: libgit2\nVersion: {version}" for version in
                             ["1.9.6+ds-1", "2.0.0+ds-1", "1.9.7+ds-2", "1.9.7+ds-1",
                              "1.9.8~rc1+ds-1", "1.8.4+ds-1"])
        self.assertEqual(METADATA.select_version(text), "1.9.7+ds-2")
        self.assertIsNone(METADATA.select_version("Package: libgit2\nVersion: 2.0.0+ds-1"))

    def test_invalid_source_metadata_fails(self):
        for text in ["Package: libgit2", "Package: libgit2\nVersion: 1.9.7+ds-1\nVersion: 2.0"]:
            with self.assertRaises(ValueError):
                METADATA.select_version(text)

    def test_descriptor_must_match_selected_source(self):
        (self.base / "source").mkdir()
        (self.base / "source-version").write_text("1.9.7+ds-1\n")
        descriptor = self.base / "source/libgit2_1.9.7+ds-1.dsc"
        descriptor.write_text("Source: libgit2\nVersion: 1.9.7+ds-1\n")
        METADATA.prepare_targets(self.base, ["amd64", "arm64"])
        self.assertEqual((self.base / "targets.tsv").read_text(),
                         "1.9.7+ds-1+local\tamd64\n1.9.7+ds-1+local\tarm64\n")
        descriptor.write_text("Source: libgit2\nVersion: 2.0.0+ds-1\n")
        with self.assertRaisesRegex(ValueError, "Version does not match"):
            METADATA.prepare_targets(self.base, ["amd64"])

    def test_backport_restores_automatic_dependencies(self):
        (self.base / "debian").mkdir()
        control = self.base / "debian/control"
        shutil.copyfile(ROOT / "tests/libgit2-1.9/fixtures/control", control)
        PREPARE.prepare_source(self.base)
        text = control.read_text()
        self.assertIn("debhelper-compat (= 13)", text)
        self.assertEqual(text.count("${misc:Depends}"), 5)
        self.assertEqual(text.count("${shlibs:Depends}"), 2)
        self.assertIn("libgit2-1.9 (= ${binary:Version})", text)
        with self.assertRaisesRegex(ValueError, "debhelper-compat"):
            PREPARE.prepare_source(self.base)

    def install_build_stubs(self):
        scripts = {
            "dpkg-source": 'mkdir -p "$3/debian"\ncp "$TEST_CONTROL" "$3/debian/control"',
            "dch": ":",
            "dpkg-buildpackage": r'''
python3 - <<'PY'
import os
from pathlib import Path
import subprocess
workspace = Path(os.environ['WORKSPACE'])
arch = os.environ['LIBGIT2_BUILD_ARCH']
multiarch = {'amd64': 'x86_64-linux-gnu', 'arm64': 'aarch64-linux-gnu'}[arch]
paths = {
    'libgit2-1.9': f'usr/lib/{multiarch}/libgit2.so.1.9',
    'libgit2-dev': 'usr/include/git2.h',
    'libgit2-experimental1.9': f'usr/lib/{multiarch}/libgit2-experimental.so.1.9',
    'libgit2-experimental-dev': 'usr/include/git2-experimental.h',
    'libgit2-fixtures': 'usr/share/doc/libgit2-fixtures/examples/example',
}
for name, path in paths.items():
    root = workspace / ('fixture-' + name)
    (root / 'DEBIAN').mkdir(parents=True)
    payload = root / path
    payload.parent.mkdir(parents=True)
    if name != os.environ.get('TEST_MISSING_PACKAGE'):
        payload.write_text('fixture library or header\n')
    package_arch = 'all' if name == 'libgit2-fixtures' else arch
    control = (f'Package: {name}\nVersion: 1.9.7+ds-1+local-1\n'
               f'Architecture: {package_arch}\nMaintainer: Test <test@localhost>\n'
               'Description: fixture\n')
    if not os.environ.get('TEST_MISSING_SIZE'):
        control += 'Installed-Size: 999999\n'
    (root / 'DEBIAN/control').write_text(control)
    subprocess.run(['dpkg-deb', '--build', '--root-owner-group', str(root),
                    str(workspace / f'{name}_1.9.7+ds-1+local-1_{package_arch}.deb')], check=True)
PY
''',
            "apt-get": r'''
if [[ " $* " == *" source "* ]]; then
    printf 'Source: libgit2\nVersion: 1.9.7+ds-1\n' > "$WORKSPACE/source/libgit2_1.9.7+ds-1.dsc"
fi
''',
            "apt-cache": "printf 'Package: libgit2\\nVersion: 1.9.7+ds-1\\n'",
        }
        for name, script in scripts.items():
            command = self.base / "bin" / name
            command.write_text("#!/bin/bash\nset -Eeuo pipefail\n" + script + "\n")
            command.chmod(0o755)
        shutil.copytree(ADAPTER, self.base / "adapters/libgit2-1.9")
        self.env.update(LIBGIT2_BUILD_ARCH="amd64", ARCHES="amd64",
                        TEST_CONTROL=str(ROOT / "tests/libgit2-1.9/fixtures/control"))

    def test_outputs_sizes_indexes_and_repeat_update(self):
        self.install_build_stubs()
        self.run_update()
        artifacts = self.artifacts()
        self.assertEqual(len(artifacts), 5)
        original = {path: path.read_bytes() for path in artifacts}
        for path in artifacts:
            metadata = fields(path)
            self.assertGreater(int(metadata["installed-size"]), 0)
            self.assertNotEqual(metadata["installed-size"], "999999")
            self.assertIn("Installed-Size: " + metadata["installed-size"] + "\n", self.index())
        self.run_update()
        self.assertEqual(original, {path: path.read_bytes() for path in self.artifacts()})
        self.env.update(LIBGIT2_BUILD_ARCH="arm64", ARCHES="arm64")
        self.run_update()
        self.assertEqual(len(self.artifacts()), 9)
        for path, contents in original.items():
            self.assertEqual(path.read_bytes(), contents)

    def test_no_19_release_leaves_repository_unchanged(self):
        self.install_build_stubs()
        (self.base / "bin/apt-cache").write_text(
            "#!/bin/bash\nprintf 'Package: libgit2\\nVersion: 2.0.0+ds-1\\n'\n")
        self.run_update()
        self.assertEqual(self.artifacts(), [])

    def test_wrong_toolchain_architecture_fails_early(self):
        self.install_build_stubs()
        self.env["ARCHES"] = "arm64"
        result = self.run_update(expected=1)
        self.assertIn("requested arm64 but toolchain targets amd64", result.stderr)
        self.assertEqual(self.artifacts(), [])

    def test_arm64_and_missing_upstream_size(self):
        self.install_build_stubs()
        self.env.update(LIBGIT2_BUILD_ARCH="arm64", ARCHES="arm64", TEST_MISSING_SIZE="1")
        self.run_update()
        self.assertEqual(len(self.artifacts()), 5)
        for path in self.artifacts():
            self.assertIn(fields(path)["architecture"], {"arm64", "all"})
            self.assertGreater(int(fields(path)["installed-size"]), 0)
            self.assertIn("Installed-Size: " + fields(path)["installed-size"] + "\n", self.index("arm64"))

    def test_missing_library_fails_without_storing_partial_outputs(self):
        self.install_build_stubs()
        self.env["TEST_MISSING_PACKAGE"] = "libgit2-experimental1.9"
        result = self.run_update(expected=1)
        self.assertIn("missing usr/lib/x86_64-linux-gnu/libgit2-experimental.so.1.9", result.stderr)
        self.assertEqual(self.artifacts(), [])
