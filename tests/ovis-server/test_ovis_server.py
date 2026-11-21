"""Check the Ovis server release files and Debian packages offline."""

import hashlib
import io
import json
import shutil
import struct
import subprocess
import tarfile

from tests.lib.publisher_test_support import ROOT, PublisherTestCase, fields


class OvisServerTests(PublisherTestCase):
    def fixture(self, *, missing_arm64=False, missing_web=None, unsafe_path=None,
                wrong_machine=False, manifest_version='0.5.9', schema=1):
        adapter = self.base / 'adapters/ovis-server'
        shutil.copytree(ROOT / 'packages/repack/ovis-server', adapter)
        downloads = self.base / 'downloads'
        web = {
            'index.html': b'<!doctype html><title>Ovis fixture</title>\n',
            'build.json': json.dumps({'revision': 'a' * 40, 'dirty': False}).encode(),
            'sw.js': b'// service worker fixture\n',
            'manifest.webmanifest': b'{"name":"Ovis"}\n',
            'THIRD_PARTY_NOTICES.md': b'Fixture notice\n',
        }
        with tarfile.open(downloads / 'ovis-dist.tar.gz', 'w:gz') as archive:
            for name, data in web.items():
                if name == missing_web:
                    continue
                member = tarfile.TarInfo('./' + name)
                member.size = len(data)
                member.mode = 0o644
                archive.addfile(member, io.BytesIO(data))
            if unsafe_path:
                member = tarfile.TarInfo(unsafe_path)
                member.type = tarfile.SYMTYPE
                member.linkname = '/etc/passwd'
                archive.addfile(member)
        assets = []

        def asset(name):
            path = downloads / name
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            assets.append({'name': name, 'size': len(data), 'digest': 'sha256:' + digest,
                           'browser_download_url': f'https://example.test/{name}'})
            return {'file': name, 'size': len(data), 'sha256': digest}

        manifest = {'schema': schema, 'version': manifest_version, 'assets': {}, 'pty': {},
                    'dist': asset('ovis-dist.tar.gz')}
        for arch, machine in [('x64', 62), ('arm64', 183)]:
            if arch == 'arm64' and missing_arm64:
                continue
            header = struct.pack('<16sHHIQQQIHHHHHH', b'\x7fELF\x02\x01\x01' + b'\0' * 9,
                                 2, 0 if wrong_machine else machine, 1, 0, 0, 0, 0,
                                 64, 0, 0, 0, 0, 0)
            for key, prefix in [('assets', 'ovis-server'), ('pty', 'ovis-pty-sidecar')]:
                name = f'{prefix}-linux-{arch}'
                (downloads / name).write_bytes(header)
                manifest[key][f'linux-{arch}'] = asset(name)
        (downloads / 'ovis-server.json').write_text(json.dumps(manifest))
        asset('ovis-server.json')
        self.release = downloads / 'release.json'
        self.release.write_text(json.dumps({'tag_name': 'v0.5.9', 'draft': False,
                                           'prerelease': False, 'assets': assets}))
        return adapter

    def change_release(self, change):
        release = json.loads(self.release.read_text())
        change(release)
        self.release.write_text(json.dumps(release))

    def change_manifest(self, change):
        path = self.base / 'downloads/ovis-server.json'
        manifest = json.loads(path.read_text())
        change(manifest)
        path.write_text(json.dumps(manifest))
        digest = 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
        self.change_release(lambda r: next(a for a in r['assets'] if a['name'] == path.name).update(digest=digest))

    def test_both_packages_contents_dependencies_size_and_repeat_update(self):
        self.fixture()
        self.run_update()
        self.assertEqual(len(self.artifacts()), 2)
        for package in self.artifacts():
            metadata = fields(package)
            self.assertEqual(metadata['package'], 'ovis-server')
            self.assertEqual(metadata['version'], '0.5.9-1')
            self.assertEqual(metadata['depends'], 'herdr-core, libc6 (>= 2.17)')
            tree = self.base / metadata['architecture']
            subprocess.run(['dpkg-deb', '--raw-extract', str(package), str(tree)],
                           check=True, capture_output=True)
            for path in ['usr/bin/ovis-server', 'usr/lib/ovis-server/ovis-server',
                         'usr/lib/ovis-server/bin/ovis-pty-sidecar',
                         'usr/share/ovis-server/dist/index.html',
                         'usr/lib/systemd/user/ovis-server.service',
                         'usr/share/doc/ovis-server/copyright',
                         'usr/share/doc/ovis-server/bun-copyright',
                         'usr/share/doc/ovis-server/THIRD-PARTY-NOTICES']:
                self.assertTrue((tree / path).is_file(), path)
            record = json.loads((tree / 'usr/lib/ovis-server/bin/ovis-pty-sidecar.json').read_text())
            sidecar = tree / 'usr/lib/ovis-server/bin/ovis-pty-sidecar'
            self.assertEqual(record, {'version': '0.5.9', 'sha256': hashlib.sha256(sidecar.read_bytes()).hexdigest()})
            actual_size = subprocess.check_output(
                ['du', '--summarize', '--block-size=1024', '--exclude=DEBIAN', str(tree)], text=True).split()[0]
            self.assertEqual(metadata['installed-size'], actual_size)
            self.assertIn(f'Installed-Size: {actual_size}\n', self.index(metadata['architecture']))
            self.assertEqual(sorted(p.name for p in (tree / 'DEBIAN').iterdir()), ['control'])
        before = {p.name: p.read_bytes() for p in self.artifacts()}
        self.run_update()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.artifacts()})

    def test_recipe_change_builds_new_revision(self):
        adapter = self.fixture()
        self.run_update()
        (adapter / 'comment').write_text('Recipe changed\n')
        self.run_update()
        self.assertEqual({fields(p)['version'] for p in self.artifacts()}, {'0.5.9-1', '0.5.9-2'})

    def test_missing_architecture(self):
        self.fixture(missing_arm64=True)
        self.run_update()
        self.assertEqual([fields(p)['architecture'] for p in self.artifacts()], ['amd64'])

    def test_missing_terminal_helper_fails(self):
        self.fixture()
        self.change_release(lambda r: r.update(assets=[a for a in r['assets'] if a['name'] != 'ovis-pty-sidecar-linux-x64']))
        self.assertIn('Missing release asset', self.run_update(expected=1).stderr)
        self.assertEqual(self.artifacts(), [])

    def test_missing_common_web_archive_fails(self):
        self.fixture()
        self.change_release(lambda r: r.update(assets=[a for a in r['assets'] if a['name'] != 'ovis-dist.tar.gz']))
        self.assertIn('Missing release asset', self.run_update(expected=1).stderr)

    def test_bad_digest(self):
        self.fixture()
        self.change_release(lambda r: r['assets'][0].update(digest=None))
        self.assertIn('Missing or invalid SHA256', self.run_update(expected=1).stderr)

    def test_duplicate_server(self):
        self.fixture()
        self.change_release(lambda r: r['assets'].append(next(a for a in r['assets'] if a['name'] == 'ovis-server-linux-x64')))
        self.assertIn('Duplicate release asset', self.run_update(expected=1).stderr)

    def test_prerelease(self):
        self.fixture()
        self.change_release(lambda r: r.update(prerelease=True))
        self.assertIn('Expected a stable release', self.run_update(expected=1).stderr)

    def test_manifest_version(self):
        self.fixture(manifest_version='0.5.8')
        self.assertIn('expected schema 1 and version 0.5.9', self.run_update(expected=1).stderr)

    def test_manifest_schema(self):
        self.fixture(schema=2)
        self.assertIn('expected schema 1', self.run_update(expected=1).stderr)

    def test_manifest_digest_disagreement(self):
        self.fixture()
        self.change_manifest(lambda m: m['assets']['linux-x64'].update(sha256='0' * 64))
        self.assertIn('bytes do not match ovis-server.json', self.run_update(expected=1).stderr)

    def test_wrong_architecture(self):
        self.fixture(wrong_machine=True)
        self.assertIn('invalid amd64 ELF', self.run_update(expected=1).stderr)
        self.assertEqual(self.artifacts(), [])

    def test_missing_web_file(self):
        self.fixture(missing_web='index.html')
        self.assertIn('missing web file: index.html', self.run_update(expected=1).stderr)

    def test_web_archive_external_link(self):
        self.fixture(unsafe_path='link')
        self.assertIn('unexpected type', self.run_update(expected=1).stderr)

    def test_web_archive_parent_path(self):
        self.fixture(unsafe_path='../outside')
        self.assertIn('unsafe path', self.run_update(expected=1).stderr)

    def test_corrupt_server_download(self):
        self.fixture()
        (self.base / 'downloads/ovis-server-linux-x64').write_bytes(b'corrupt')
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])
