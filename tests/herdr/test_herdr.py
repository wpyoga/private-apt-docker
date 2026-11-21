"""Check static binaries, release selection, and Debian output."""

import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

from tests.lib.publisher_test_support import ROOT, PublisherTestCase, fields


class HerdrTests(PublisherTestCase):
    def fixture(self, *, missing_arm64=False, wrong_machine=False):
        adapter = self.base / 'adapters/herdr'
        shutil.copytree(ROOT / 'packages/repack/herdr', adapter)
        assets = []
        for arch, machine in [('x86_64', 62), ('aarch64', 183)]:
            if arch == 'aarch64' and missing_arm64:
                continue
            header = struct.pack('<16sHHIQQQIHHHHHH', b'\x7fELF\x02\x01\x01' + b'\0' * 9,
                                 2, 0 if wrong_machine else machine, 1, 0, 0, 0, 0,
                                 64, 0, 0, 0, 0, 0)
            path = self.base / f'downloads/herdr-linux-{arch}'
            path.write_bytes(header)
            assets.append({'name': path.name,
                           'browser_download_url': f'https://example.test/{path.name}',
                           'digest': 'sha256:' + hashlib.sha256(header).hexdigest()})
        self.release = self.base / 'downloads/release.json'
        self.release.write_text(json.dumps({'tag_name': 'v0.9.5', 'draft': False,
                                           'prerelease': False, 'assets': assets}))
        return adapter

    def change_release(self, change):
        release = json.loads(self.release.read_text())
        change(release)
        self.release.write_text(json.dumps(release))

    def test_packages_both_architectures_size_and_repeat_update(self):
        adapter = self.fixture()
        self.run_update()
        self.assertEqual(len(self.artifacts()), 2)
        before = {p.name: p.read_bytes() for p in self.artifacts()}
        for package in self.artifacts():
            metadata = fields(package)
            self.assertEqual(metadata['version'], '0.9.5-1')
            self.assertGreater(int(metadata['installed-size']), 0)
            self.assertIn(f"Installed-Size: {metadata['installed-size']}\n",
                          self.index(metadata['architecture']))
            listing = subprocess.check_output(['dpkg-deb', '--contents', str(package)], text=True)
            self.assertIn('./usr/bin/herdr', listing)
            self.assertIn('./usr/share/doc/herdr/copyright', listing)
        self.run_update()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.artifacts()})
        (adapter / 'comment').write_text('Recipe change\n')
        self.run_update()
        self.assertEqual({fields(p)['version'] for p in self.artifacts()}, {'0.9.5-1', '0.9.5-2'})

    def test_missing_arm64(self):
        self.fixture(missing_arm64=True)
        self.run_update()
        self.assertEqual([fields(p)['architecture'] for p in self.artifacts()], ['amd64'])

    def test_invalid_machine(self):
        self.fixture(wrong_machine=True)
        self.assertIn('invalid amd64 ELF', self.run_update(expected=1).stderr)
        self.assertEqual(self.artifacts(), [])

    def test_corrupt_binary(self):
        self.fixture()
        (self.base / 'downloads/herdr-linux-x86_64').write_bytes(b'corrupt')
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_invalid_digest(self):
        self.fixture()
        self.change_release(lambda r: r['assets'][0].update(digest=None))
        self.assertIn('Missing or invalid SHA256', self.run_update(expected=1).stderr)

    def test_duplicate_asset(self):
        self.fixture()
        self.change_release(lambda r: r['assets'].append(r['assets'][0]))
        self.assertIn('Duplicate release asset', self.run_update(expected=1).stderr)

    def test_prerelease(self):
        self.fixture()
        self.change_release(lambda r: r.update(prerelease=True))
        self.assertIn('Expected a stable release', self.run_update(expected=1).stderr)

    def test_unexpected_version(self):
        self.fixture()
        self.change_release(lambda r: r.update(tag_name='nightly'))
        self.assertIn('Unexpected stable release tag', self.run_update(expected=1).stderr)

    def test_dynamic_binary_is_rejected(self):
        self.fixture()
        path = self.base / 'downloads/herdr-linux-x86_64'
        path.write_bytes(Path(shutil.which('true')).read_bytes())
        digest = 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
        self.change_release(lambda r: r['assets'][0].update(digest=digest))
        self.assertIn('expected a static Linux binary', self.run_update(expected=1).stderr)
        self.assertEqual(self.artifacts(), [])
