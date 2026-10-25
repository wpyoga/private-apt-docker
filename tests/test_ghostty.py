"""Offline Ghostty import tests using real Debian fixture packages."""
import hashlib
import io
import json
import shutil
import subprocess
import tarfile

from publisher_test_support import ROOT, PublisherTestCase, fields


class GhosttyTests(PublisherTestCase):
    def fixture(self, *, missing_arm64=False, corrupt=False, package='ghostty',
                version='1.3.1-0~ppa2', missing_path=False):
        shutil.copytree(ROOT / 'packages/ghostty', self.base / 'adapters/ghostty',
                        dirs_exist_ok=True)
        assets = []
        for arch in ('amd64', 'arm64'):
            if missing_arm64 and arch == 'arm64':
                continue
            root = self.base / f'upstream-{arch}'
            (root / 'DEBIAN').mkdir(parents=True, exist_ok=True)
            (root / 'DEBIAN/control').write_text(
                f'Package: {package}\nVersion: {version}\nArchitecture: {arch}\n'
                'Maintainer: Upstream <upstream@example.com>\n'
                'Depends: libgtk-4-1, libadwaita-1-0\n'
                'Description: Ghostty fixture\n Continued description\n'
                'X-Publisher-Stream: old-stream\n')
            postinst = root / 'DEBIAN/postinst'
            postinst.write_text('#!/bin/sh\nexit 42\n')
            postinst.chmod(0o755)
            for path in ('usr/bin/ghostty',
                         'usr/share/applications/com.mitchellh.ghostty.desktop',
                         'usr/share/terminfo/x/xterm-ghostty'):
                dest = root / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text('fixture\n')
                if path == 'usr/bin/ghostty':
                    dest.chmod(0o755)
            if missing_path:
                (root / 'usr/bin/ghostty').unlink()
            name = f'ghostty_1.3.1-0.ppa2_{arch}_trixie.deb'
            deb = self.base / 'downloads' / name
            subprocess.run(['dpkg-deb', '--build', str(root), str(deb)],
                           check=True, capture_output=True)
            assets.append({'name': name,
                           'digest': 'sha256:' + ('0' * 64 if corrupt else
                                                 hashlib.sha256(deb.read_bytes()).hexdigest()),
                           'browser_download_url': f'https://fixtures.invalid/{name}'})
        release = {'tag_name': '1.3.1-0-ppa2', 'draft': False, 'prerelease': False,
                   'published_at': '2026-04-01T03:36:27Z', 'assets': assets}
        (self.base / 'downloads/release.json').write_text(json.dumps(release))

    def test_import_preserves_integration_and_rewrites_metadata(self):
        self.fixture()
        self.run_update()
        self.assertEqual(len(self.artifacts('ghostty')), 2)
        for artifact in self.artifacts('ghostty'):
            metadata = fields(artifact)
            self.assertEqual(metadata['version'], '1.3.1+0.ppa2-1')
            self.assertEqual(metadata['maintainer'], self.env['MAINTAINER'])
            self.assertEqual(metadata['depends'], 'libgtk-4-1, libadwaita-1-0')
            self.assertEqual(metadata['x-publisher-stream'], 'ghostty')
            self.assertRegex(metadata['x-build-inputs-sha256'], r'^[a-f0-9]{64}$')
            payload = subprocess.check_output(['dpkg-deb', '--fsys-tarfile', str(artifact)])
            with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
                self.assertEqual(archive.getmember('./usr/bin/ghostty').mode, 0o755)
                self.assertIsNotNone(archive.getmember('./usr/share/terminfo/x/xterm-ghostty'))
            control = self.base / ('control-' + metadata['architecture'])
            subprocess.run(['dpkg-deb', '--control', str(artifact), str(control)], check=True)
            self.assertEqual((control / 'postinst').read_text(), '#!/bin/sh\nexit 42\n')
        self.run_update()
        self.assertEqual(len(self.artifacts()), 2)

    def test_missing_architecture_is_published_later(self):
        self.fixture(missing_arm64=True)
        result = self.run_update()
        self.assertIn('No current upstream package for arm64', result.stderr)
        self.assertEqual(len(self.artifacts()), 1)
        self.fixture()
        self.run_update()
        self.assertEqual(len(self.artifacts()), 2)

    def test_bad_digest_and_unexpected_metadata_or_layout_store_nothing(self):
        for options in ({'corrupt': True}, {'package': 'wrong'},
                        {'version': '9.9.9'}, {'missing_path': True}):
            with self.subTest(options=options):
                self.fixture(**options)
                self.run_update(expected=1)
                self.assertEqual(self.artifacts(), [])

    def test_query_rejects_unstable_releases_and_invalid_digests(self):
        self.fixture()
        path = self.base / 'downloads/release.json'
        original = path.read_text()
        for change in ('tag', 'prerelease', 'digest', 'url'):
            with self.subTest(change=change):
                release = json.loads(original)
                if change == 'tag':
                    release['tag_name'] = 'tip'
                elif change == 'prerelease':
                    release['prerelease'] = True
                elif change == 'digest':
                    release['assets'][0]['digest'] = 'sha256:bad'
                else:
                    release['assets'][0]['browser_download_url'] = 'http://invalid/file.deb'
                path.write_text(json.dumps(release))
                self.run_update(expected=1)
                self.assertEqual(self.artifacts(), [])
