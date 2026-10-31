"""Offline source-version selection and repository routing regressions."""
import importlib.util
from pathlib import Path
import subprocess
import shutil

from tests.lib.publisher_test_support import ROOT, PublisherTestCase

SPEC = importlib.util.spec_from_file_location(
    "screensaver_source", ROOT / "packages/rebuild/xfce4-screensaver/source-metadata.py")
METADATA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(METADATA)


class SourceTests(PublisherTestCase):
    def test_source_version_preserved_for_both_architectures(self):
        (self.base / "source").mkdir()
        (self.base / "source/xfce4-screensaver_4.18.4-1.dsc").write_text(
            "Source: xfce4-screensaver\nVersion: 4.18.4-1\n")
        METADATA.prepare_targets(self.base, ["amd64", "arm64"])
        self.assertEqual((self.base / "targets.tsv").read_text(),
                         "4.18.4-1+local\tamd64\n4.18.4-1+local\tarm64\n")
        subprocess.run(["dpkg", "--compare-versions", "4.18.4-1+local-1", "gt", "4.18.4-1"], check=True)

    def test_missing_descriptor_fails(self):
        (self.base / "source").mkdir()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            METADATA.prepare_targets(self.base, ["amd64"])

    def test_missing_version_fails(self):
        (self.base / "source").mkdir()
        (self.base / "source/xfce4-screensaver_test.dsc").write_text(
            "Source: xfce4-screensaver\n")
        with self.assertRaisesRegex(ValueError, "source Version"):
            METADATA.prepare_targets(self.base, ["amd64"])

    def run_build(self, architecture="amd64", rules=None, missing_path="", patch_series=None):
        workspace = self.base / "workspace"
        workspace.mkdir()
        (workspace / "source-version").write_text("4.18.4-1\n")
        (workspace / "source-descriptor").write_text("unused.dsc\n")
        output = self.base / "output"
        output.mkdir()
        rules_path = self.base / "rules"
        if rules is None:
            rules = (ROOT / "tests/xfce4-screensaver/fixtures/rules").read_text()
        rules_path.write_text(rules)
        for name, body in {
            "dpkg-source": '''
mkdir -p "$3/debian"
cp "$TEST_RULES" "$3/debian/rules"
printf 'Build-Depends: debhelper-compat (= 13),\n               xfce4-dev-tools\n' > "$3/debian/control"
''',
            "quilt": 'printf "%s\\n" "$*" >> "$WORKSPACE/quilt-commands"',
            "dch": ':',
            "dh_auto_configure": 'printf "%s\\n" "$@" > "$WORKSPACE/configure-arguments"',
            "dpkg-buildpackage": '''
if [[ "$XFCE_BUILD_ARCH" == arm64 ]]; then
    grep -Fq 'xfce4-dev-tools:native' debian/control
    [[ "$CC" == aarch64-linux-gnu-gcc ]]
fi
make -f debian/rules override_dh_auto_configure
mkdir -p "$WORKSPACE/upstream/DEBIAN" "$WORKSPACE/upstream/usr/bin"
printf 'Package: xfce4-screensaver\nVersion: 4.18.4-1+local-1\nArchitecture: %s\nMaintainer: Test <test@localhost>\nDescription: fixture screensaver\nInstalled-Size: 999999\n' "$XFCE_BUILD_ARCH" > "$WORKSPACE/upstream/DEBIAN/control"
printf '#!/bin/sh\nexit 0\n' > "$WORKSPACE/upstream/usr/bin/xfce4-screensaver"
chmod 755 "$WORKSPACE/upstream/usr/bin/xfce4-screensaver"
mkdir -p "$WORKSPACE/upstream/usr/share/applications"
printf '[Desktop Entry]\nType=Application\nName=Screensaver\nExec=xfce4-screensaver\n' > "$WORKSPACE/upstream/usr/share/applications/xfce4-screensaver-preferences.desktop"
for FILE in usr/bin/xfce4-screensaver-command usr/bin/xfce4-screensaver-preferences usr/libexec/xfce4-screensaver-dialog usr/share/dbus-1/services/org.xfce.ScreenSaver.service etc/pam.d/xfce4-screensaver etc/xdg/autostart/xfce4-screensaver.desktop; do
    mkdir -p "$WORKSPACE/upstream/$(dirname "$FILE")"
    printf 'fixture\n' > "$WORKSPACE/upstream/$FILE"
done
if [[ -n "${TEST_MISSING_PATH:-}" ]]; then
    rm "$WORKSPACE/upstream/$TEST_MISSING_PATH"
fi
dpkg-deb --build --root-owner-group "$WORKSPACE/upstream" "$WORKSPACE/xfce4-screensaver_4.18.4-1+local-1_${XFCE_BUILD_ARCH}.deb"
''',
        }.items():
            stub = self.base / "bin" / name
            stub.write_text('#!/bin/bash\nset -Eeuo pipefail\n' + body + '\n')
            stub.chmod(0o755)
        adapter = self.base / "screensaver-adapter"
        shutil.copytree(ROOT / "packages/rebuild/xfce4-screensaver", adapter)
        if patch_series is not None:
            (adapter / "patches/series").write_text(patch_series)
            (adapter / "patches/local.patch").write_text("fixture patch\n")
        environment = {**self.env, "FRAMEWORK_DIR": str(ROOT),
                       "ADAPTER_DIR": str(adapter),
                       "WORKSPACE": str(workspace), "XFCE_BUILD_ARCH": architecture,
                       "TEST_RULES": str(rules_path), "TEST_MISSING_PATH": missing_path,
                       "PUBLISHER_STREAM": "xfce4-screensaver",
                       "BUILD_INPUTS_SHA256": "a" * 64}
        result = subprocess.run([str(ROOT / "packages/rebuild/xfce4-screensaver/build"),
                                 "4.18.4-1+local-1", architecture, str(output)],
                                env=environment, capture_output=True, text=True)
        return result, workspace, output

    def test_build_recalculates_size_and_index_metadata(self):
        from tests.lib.publisher_test_support import fields
        result, workspace, output = self.run_build()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((workspace / "configure-arguments").read_text().splitlines(),
                         ["--", "--enable-maintainer-mode"])
        package = next(output.glob('*.deb'))
        metadata = fields(package)
        self.assertGreater(int(metadata['installed-size']), 0)
        self.assertNotEqual(metadata['installed-size'], '999999')
        self.assertEqual(metadata['x-publisher-stream'], 'xfce4-screensaver')
        index = subprocess.check_output(['dpkg-scanpackages', '--multiversion', str(output)],
                                        text=True, stderr=subprocess.DEVNULL)
        self.assertIn('Installed-Size: ' + metadata['installed-size'] + '\n', index)

    def test_arm64_build_uses_maintainer_mode(self):
        result, workspace, output = self.run_build(architecture="arm64")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((workspace / "configure-arguments").read_text().splitlines(),
                         ["--", "--enable-maintainer-mode"])
        self.assertEqual(len(list(output.glob("*_arm64.deb"))), 1)

    def test_changed_configure_command_fails_before_building(self):
        rules = (ROOT / "tests/xfce4-screensaver/fixtures/rules").read_text()
        result, workspace, output = self.run_build(
            rules=rules + "\noverride_dh_auto_configure:\n\tdh_auto_configure -- --unexpected\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("xfce4-screensaver 4.18.4-1: unexpected dh_auto_configure command in debian/rules",
                      result.stderr)
        self.assertFalse((workspace / "configure-arguments").exists())
        self.assertEqual(list(output.iterdir()), [])

    def test_missing_pam_configuration_fails(self):
        result, workspace, output = self.run_build(missing_path="etc/pam.d/xfce4-screensaver")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing etc/pam.d/xfce4-screensaver", result.stderr)
        self.assertEqual(list(output.iterdir()), [])

    def test_patch_series_is_applied_without_fuzz(self):
        result, workspace, output = self.run_build(patch_series="# Local patches\n\nlocal.patch\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        commands = (workspace / "quilt-commands").read_text().splitlines()
        self.assertTrue(commands[0].endswith("/patches/local.patch"))
        self.assertEqual(commands[1], "push --fuzz=0")

    def test_missing_patch_fails(self):
        result, workspace, output = self.run_build(patch_series="missing.patch\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid local patch: missing.patch", result.stderr)
        self.assertEqual(list(output.iterdir()), [])

    def test_query_downloads_source_and_selects_requested_architecture(self):
        apt = self.base / "bin/apt-get"
        apt.write_text('''#!/bin/bash
set -Eeuo pipefail
printf '%s\\n' "$*" >> "$WORKSPACE/apt-commands"
if [[ " $* " == *" source --download-only xfce4-screensaver "* ]]; then
    printf 'Source: xfce4-screensaver\\nVersion: 4.18.4-1\\n' > xfce4-screensaver_4.18.4-1.dsc
fi
''')
        apt.chmod(0o755)
        workspace = self.base / "query-workspace"
        environment = {**self.env, "ADAPTER_DIR": str(ROOT / "packages/rebuild/xfce4-screensaver"),
                       "WORKSPACE": str(workspace), "ARCHES": "arm64"}
        result = subprocess.run([str(ROOT / "packages/rebuild/xfce4-screensaver/query")],
                                env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((workspace / "targets.tsv").read_text(), "4.18.4-1+local\tarm64\n")
        commands = (workspace / "apt-commands").read_text().splitlines()
        self.assertEqual(len(commands), 2)
        self.assertTrue(commands[0].endswith(" update"))
        self.assertTrue(commands[1].endswith(" source --download-only xfce4-screensaver"))
