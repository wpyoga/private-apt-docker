"""Check unchanged Ovis imports and their repository metadata."""

import hashlib
import json
import shutil
import subprocess

from tests.lib.publisher_test_support import ROOT, PublisherTestCase, fields


EXECUTABLES = (
    'opt/Ovis/ovis', 'opt/Ovis/chrome-sandbox', 'opt/Ovis/resources/ovis/bin/bun',
    'opt/Ovis/resources/ovis/bin/herdr-core',
    'opt/Ovis/resources/ovis/server/bin/ovis-pty-sidecar',
)
FILES = EXECUTABLES + (
    'opt/Ovis/resources/ovis/LICENSE',
    'opt/Ovis/resources/ovis/THIRD_PARTY_NOTICES.md',
    'opt/Ovis/resources/ovis/licenses/bun/LICENSE.md',
    'opt/Ovis/resources/ovis/licenses/herdr-core/LICENSE',
    'opt/Ovis/resources/ovis/licenses/herdr-core/THIRD-PARTY-NOTICES',

    'opt/Ovis/resources/app.asar', 'opt/Ovis/resources/apparmor-profile',
    'opt/Ovis/resources/ovis/server/dist/index.html',
    'opt/Ovis/resources/ovis/server/dist/THIRD_PARTY_NOTICES.md',
    'opt/Ovis/LICENSE.electron.txt', 'opt/Ovis/LICENSES.chromium.html',
    'usr/share/applications/ovis.desktop',
)


class OvisTests(PublisherTestCase):
    def fixture(self, *, installed_size=None, missing_path=None, wrong_machine=False,
                missing_arm64=False, package_name='ovis-desktop', version='0.5.9'):
        self.env['REPOSITORY_MODE'] = 'redistribute'
        adapter = self.base / 'adapters/ovis'
        if not adapter.exists():
            shutil.copytree(ROOT / 'packages/redistribute/ovis', adapter)
        assets = []
        for arch, asset_arch, machine in [('amd64', 'x64', 62), ('arm64', 'arm64', 183)]:
            if arch == 'arm64' and missing_arm64:
                continue
            stage = self.base / f'stage-{arch}'
            shutil.rmtree(stage, ignore_errors=True)
            (stage / 'DEBIAN').mkdir(parents=True)
            control = (f'Package: {package_name}\nVersion: {version}\nArchitecture: {arch}\n'
                       'Maintainer: Upstream <test@example.com>\nDepends: libnss3\n'
                       'Description: Ovis fixture\n')
            if installed_size is not None:
                control += f'Installed-Size: {installed_size}\n'
            (stage / 'DEBIAN/control').write_text(control)
            (stage / 'DEBIAN/postinst').write_text('#!/bin/sh\nexit 99\n')
            (stage / 'DEBIAN/postinst').chmod(0o755)
            for name in FILES:
                if name == missing_path:
                    continue
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                if name in EXECUTABLES:
                    header = bytearray(20)
                    header[:6] = b'\x7fELF\x02\x01'
                    header[18:20] = (0 if wrong_machine else machine).to_bytes(2, 'little')
                    path.write_bytes(header + b'x' * 2048)
                    path.chmod(0o755)
                else:
                    path.write_text('fixture\n')
            path = self.base / f'downloads/Ovis-linux-{asset_arch}.deb'
            subprocess.run(['dpkg-deb', '--build', '--root-owner-group', str(stage), str(path)],
                           check=True, capture_output=True)
            assets.append({'name': path.name,
                           'browser_download_url': f'https://example.test/{path.name}',
                           'digest': 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()})
        self.release = self.base / 'downloads/release.json'
        self.release.write_text(json.dumps({'tag_name': 'v0.5.9', 'draft': False,
                                           'prerelease': False, 'assets': assets}))
        return adapter

    def test_original_bytes_and_size_in_index(self):
        self.fixture()
        self.run_update()
        self.assertEqual(len(self.artifacts()), 2)
        for path in self.artifacts():
            metadata = fields(path)
            asset_arch = {'amd64': 'x64', 'arm64': 'arm64'}[metadata['architecture']]
            original = self.base / f'downloads/Ovis-linux-{asset_arch}.deb'
            self.assertEqual(path.read_bytes(), original.read_bytes())
            self.assertEqual(metadata['version'], '0.5.9')
            self.assertNotIn('installed-size', metadata)
            self.assertEqual(metadata['depends'], 'libnss3')
            self.assertIn('Installed-Size: 11\n', self.index(metadata['architecture']))
            self.assertIn('X-Publisher-Stream: ovis\n', self.index(metadata['architecture']))
        before = {p.name: p.read_bytes() for p in self.artifacts()}
        self.run_update()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.artifacts()})

    def test_stale_size_and_recipe_change(self):
        adapter = self.fixture(installed_size=999999)
        self.run_update()
        self.assertNotIn('Installed-Size: 999999', self.index())
        before = {p.name: p.read_bytes() for p in self.artifacts()}
        (adapter / 'comment').write_text('New recipe\n')
        self.run_update()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.artifacts()})

    def test_missing_architecture(self):
        self.fixture(missing_arm64=True)
        self.run_update()
        self.assertEqual(len(self.artifacts()), 1)

    def test_missing_server(self):
        self.fixture(missing_path='opt/Ovis/resources/ovis/bin/herdr-core')
        self.assertIn('missing upstream paths', self.run_update(expected=1).stderr)
        self.assertEqual(self.artifacts(), [])

    def test_wrong_machine(self):
        self.fixture(wrong_machine=True)
        self.assertIn('invalid amd64 executable', self.run_update(expected=1).stderr)

    def test_wrong_package_identity(self):
        self.fixture(package_name='other')
        self.assertIn('unexpected Package', self.run_update(expected=1).stderr)

    def test_wrong_package_version(self):
        self.fixture(version='0.5.8')
        self.assertIn('unexpected Version', self.run_update(expected=1).stderr)

    def test_invalid_digest_and_duplicate_assets(self):
        self.fixture()
        release = json.loads(self.release.read_text())
        release['assets'][0]['digest'] = None
        self.release.write_text(json.dumps(release))
        self.assertIn('Missing or invalid SHA256', self.run_update(expected=1).stderr)
        release['assets'].append(release['assets'][0])
        self.release.write_text(json.dumps(release))
        self.assertIn('Duplicate release asset', self.run_update(expected=1).stderr)

    def test_corrupt_download(self):
        self.fixture()
        (self.base / 'downloads/Ovis-linux-x64.deb').write_bytes(b'corrupt')
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])
