"""Build fixed release archives for the Herdr desktop and core tests."""

import hashlib
import io
import json
import shutil
import struct
import subprocess
import tarfile

from tests.lib.publisher_test_support import ROOT, PublisherTestCase, fields


class HerdrArchiveTests(PublisherTestCase):
    component = None

    def fixture(self, *, missing_arm64=False, missing_path=None, wrong_machine=False,
                unsafe_link=False):
        name = f'herdr-{self.component}'
        adapter = self.base / f'adapters/{name}'
        if not adapter.exists():
            shutil.copytree(ROOT / f'packages/repack/{name}', adapter)
        targets = {}
        for arch, machine in [('x86_64', 62), ('aarch64', 183)]:
            if arch == 'aarch64' and missing_arm64:
                continue
            path = self.base / f'downloads/{name}-linux-{arch}.tar.gz'
            prefix = 'herdr-app/' if self.component == 'app' else ''
            header = struct.pack('<16sHHIQQQIHHHHHH', b'\x7fELF\x02\x01\x01' + b'\0' * 9,
                                 2, 0 if wrong_machine else machine, 1, 0, 0, 0, 0,
                                 64, 0, 0, 0, 0, 0)
            content = {name: header, 'LICENSE': b'license\n', 'THIRD-PARTY-NOTICES': b'notices\n'}
            if self.component == 'app':
                content['herdr-app.svg'] = b'<svg/>\n'
            with tarfile.open(path, 'w:gz') as archive:
                for member_name, data in content.items():
                    if member_name == missing_path:
                        continue
                    member = tarfile.TarInfo(prefix + member_name)
                    member.size = len(data)
                    member.mode = 0o755 if member_name == name else 0o644
                    archive.addfile(member, io.BytesIO(data))
                if unsafe_link:
                    member = tarfile.TarInfo(prefix + 'unsafe')
                    member.type = tarfile.SYMTYPE
                    member.linkname = '/etc/passwd'
                    archive.addfile(member)
            targets[f'linux-{arch}'] = {
                'url': f'https://releases.herdr.dev/{self.component}/0.1.21/{path.name}',
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        self.manifest = self.base / 'downloads/latest.json'
        self.manifest.write_text(json.dumps({'version': '0.1.21', 'core_min': '0.1.11',
                                             'targets': targets}))
        return adapter

    def change_manifest(self, change):
        manifest = json.loads(self.manifest.read_text())
        change(manifest)
        self.manifest.write_text(json.dumps(manifest))

    def test_contents_size_and_revision_reuse(self):
        adapter = self.fixture()
        self.run_update()
        self.assertEqual(len(self.artifacts()), 2)
        for path in self.artifacts():
            metadata = fields(path)
            self.assertEqual(metadata['package'], f'herdr-{self.component}')
            size = metadata['installed-size']
            self.assertGreater(int(size), 0)
            self.assertIn(f'Installed-Size: {size}\n', self.index(metadata['architecture']))
            unpacked = self.base / f"unpacked-{metadata['architecture']}"
            subprocess.run(['dpkg-deb', '--extract', str(path), str(unpacked)],
                           check=True, capture_output=True)
            self.assertTrue((unpacked / f'usr/bin/herdr-{self.component}').is_file())
            self.assertTrue((unpacked / f'usr/share/doc/herdr-{self.component}/copyright').is_file())
            if self.component == 'core':
                self.assertEqual((unpacked / 'usr/bin/hc').readlink().as_posix(), 'herdr-core')
            else:
                self.assertIn('herdr-core (>= 0.1.11)', metadata['depends'])
                depends = subprocess.check_output(
                    ['dpkg-deb', '--field', str(path), 'Depends'], text=True)
                self.assertIn('libxkbcommon-x11-0', depends)
                self.assertTrue((unpacked / 'usr/share/applications/herdr-app.desktop').is_file())
                # No icon beside the executable: upstream cannot treat /usr/bin as its update folder.
                self.assertFalse((unpacked / 'usr/bin/herdr-app.svg').exists())
        before = {p.name: p.read_bytes() for p in self.artifacts()}
        self.run_update()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.artifacts()})
        (adapter / 'comment').write_text('Recipe changed\n')
        self.run_update()
        self.assertEqual({fields(p)['version'] for p in self.artifacts()}, {'0.1.21-1', '0.1.21-2'})

    def test_missing_architecture(self):
        self.fixture(missing_arm64=True)
        self.run_update()
        self.assertEqual(len(self.artifacts()), 1)

    def test_missing_license(self):
        self.fixture(missing_path='LICENSE')
        self.assertIn('missing upstream paths', self.run_update(expected=1).stderr)
        self.assertEqual(self.artifacts(), [])

    def test_external_link(self):
        self.fixture(unsafe_link=True)
        self.assertIn('unexpected file or type', self.run_update(expected=1).stderr)
        self.assertEqual(self.artifacts(), [])

    def test_wrong_architecture(self):
        self.fixture(wrong_machine=True)
        self.assertIn('invalid amd64 ELF', self.run_update(expected=1).stderr)

    def test_invalid_digest(self):
        self.fixture()
        self.change_manifest(lambda m: m['targets']['linux-x86_64'].update(sha256='bad'))
        self.assertIn('Invalid URL or SHA256', self.run_update(expected=1).stderr)

    def test_changed_url(self):
        self.fixture()
        self.change_manifest(lambda m: m['targets']['linux-x86_64'].update(url='https://example.test/x'))
        self.assertIn('Invalid URL or SHA256', self.run_update(expected=1).stderr)

    def test_invalid_version(self):
        self.fixture()
        self.change_manifest(lambda m: m.update(version='nightly'))
        self.assertIn('Invalid release version', self.run_update(expected=1).stderr)

    def test_invalid_targets(self):
        self.fixture()
        self.change_manifest(lambda m: m.update(targets=[]))
        self.assertIn('Invalid targets object', self.run_update(expected=1).stderr)

    def test_corrupt_archive(self):
        self.fixture()
        path = self.base / f'downloads/herdr-{self.component}-linux-x86_64.tar.gz'
        path.write_bytes(b'corrupt')
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])
