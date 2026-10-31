"""Offline source-version selection and repository routing regressions."""
import importlib.util
from pathlib import Path
import subprocess

from tests.lib.publisher_test_support import ROOT, PublisherTestCase

SPEC = importlib.util.spec_from_file_location(
    "terminal_source", ROOT / "packages/rebuild/xfce4-terminal/source-metadata.py")
METADATA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(METADATA)


class SourceTests(PublisherTestCase):
    def test_source_version_preserved_for_both_architectures(self):
        (self.base / "source").mkdir()
        (self.base / "source/xfce4-terminal_1.1.4-1.dsc").write_text(
            "Source: xfce4-terminal\nVersion: 1.1.4-1\n")
        METADATA.prepare_targets(self.base, ["amd64", "arm64"])
        self.assertEqual((self.base / "targets.tsv").read_text(),
                         "1.1.4-1+local\tamd64\n1.1.4-1+local\tarm64\n")
        subprocess.run(["dpkg", "--compare-versions", "1.1.4-1+local-1", "gt", "1.1.4-1"], check=True)

    def test_missing_descriptor_fails(self):
        (self.base / "source").mkdir()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            METADATA.prepare_targets(self.base, ["amd64"])

    def test_missing_version_fails(self):
        (self.base / "source").mkdir()
        (self.base / "source/xfce4-terminal_test.dsc").write_text(
            "Source: xfce4-terminal\n")
        with self.assertRaisesRegex(ValueError, "source Version"):
            METADATA.prepare_targets(self.base, ["amd64"])

    def test_build_recalculates_size_and_index_metadata(self):
        from tests.lib.publisher_test_support import fields
        workspace = self.base / "workspace"
        workspace.mkdir()
        (workspace / "source-version").write_text("1.1.4-1\n")
        (workspace / "source-descriptor").write_text("unused.dsc\n")
        output = self.base / "output"
        output.mkdir()
        for name, body in {
            "dpkg-source": 'mkdir -p "$3"',
            "dch": ':',
            "dpkg-buildpackage": '''
mkdir -p "$WORKSPACE/upstream/DEBIAN" "$WORKSPACE/upstream/usr/bin"
printf 'Package: xfce4-terminal\nVersion: 1.1.4-1+local-1\nArchitecture: amd64\nMaintainer: Test <test@localhost>\nDescription: fixture terminal\nInstalled-Size: 999999\n' > "$WORKSPACE/upstream/DEBIAN/control"
printf '#!/bin/sh\nexit 0\n' > "$WORKSPACE/upstream/usr/bin/xfce4-terminal"
chmod 755 "$WORKSPACE/upstream/usr/bin/xfce4-terminal"
mkdir -p "$WORKSPACE/upstream/usr/share/applications"
printf '[Desktop Entry]\nType=Application\nName=Terminal\nExec=xfce4-terminal\n' > "$WORKSPACE/upstream/usr/share/applications/xfce4-terminal.desktop"
dpkg-deb --build --root-owner-group "$WORKSPACE/upstream" "$WORKSPACE/xfce4-terminal_1.1.4-1+local-1_amd64.deb"
''',
        }.items():
            stub = self.base / "bin" / name
            stub.write_text('#!/bin/bash\nset -Eeuo pipefail\n' + body + '\n')
            stub.chmod(0o755)
        environment = {**self.env, "FRAMEWORK_DIR": str(ROOT),
                       "ADAPTER_DIR": str(ROOT / "packages/rebuild/xfce4-terminal"),
                       "WORKSPACE": str(workspace), "XFCE_BUILD_ARCH": "amd64",
                       "PUBLISHER_STREAM": "xfce4-terminal",
                       "BUILD_INPUTS_SHA256": "a" * 64}
        subprocess.run([str(ROOT / "packages/rebuild/xfce4-terminal/build"),
                        "1.1.4-1+local-1", "amd64", str(output)],
                       env=environment, check=True, capture_output=True, text=True)
        package = next(output.glob('*.deb'))
        metadata = fields(package)
        self.assertGreater(int(metadata['installed-size']), 0)
        self.assertNotEqual(metadata['installed-size'], '999999')
        self.assertEqual(metadata['x-publisher-stream'], 'xfce4-terminal')
        index = subprocess.check_output(['dpkg-scanpackages', '--multiversion', str(output)],
                                        text=True, stderr=subprocess.DEVNULL)
        self.assertIn('Installed-Size: ' + metadata['installed-size'] + '\n', index)
