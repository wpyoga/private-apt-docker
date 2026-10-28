"""Offline imports of USBImager GTK packages and arm64 X11 archives."""

import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
import zipfile

from tests.lib.publisher_test_support import ROOT, PublisherTestCase, fields


class USBImagerTests(PublisherTestCase):
    def fixture(self, *, missing_arm64=False, installed_size=None, mutation=None):
        adapter = self.base / 'adapters/usbimager'
        shutil.copytree(ROOT / 'packages/usbimager', adapter, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__'))
        lines = []
        for arch, machine in (('amd64', 62), ('arm64', 183)):
            if missing_arm64 and arch == 'arm64':
                continue
            root = self.base / f'upstream-{arch}'
            if root.exists():
                shutil.rmtree(root)
            usr = root / 'usr'
            payloads = {
                'bin/usbimager': Path('/bin/true').read_bytes(),
                'share/applications/usbimager.desktop': (
                    b'[Desktop Entry]\nVersion=1.0.10\nType=Application\n'
                    b'Name=USBImager\nExec=/usr/bin/usbimager\nIcon=usbimager\n'),
                'share/man/man8/usbimager.8.gz': b'fixture manual',
                **{f'share/icons/hicolor/{size}x{size}/apps/usbimager.png': b'icon'
                   for size in (16, 32, 64, 128)},
            }
            binary = bytearray(payloads['bin/usbimager'])
            struct.pack_into('<H', binary, 18, machine)
            payloads['bin/usbimager'] = binary
            for name, contents in payloads.items():
                path = usr / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(contents)
            (usr / 'bin/usbimager').chmod(0o755)
            if mutation:
                mutation(usr, arch)
            if arch == 'amd64':
                name = 'usbimager_1.0.10-amd64.deb'
                (root / 'DEBIAN').mkdir()
                (root / 'DEBIAN/control').write_text(
                    'Package: usbimager\nVersion: 1.0.10\nArchitecture: amd64\n'
                    'Maintainer: bzt\nDepends: udisks2\nDescription: USBImager\n Full interface\n' +
                    (f'Installed-Size: {installed_size}\n' if installed_size is not None else ''))
                (root / 'DEBIAN/copyright').write_text('Upstream copyright fixture\n')
                subprocess.run(['dpkg-deb', '--build', '--root-owner-group', str(root),
                                str(self.base / 'downloads' / name)], check=True, capture_output=True)
            else:
                name = 'usbimager_1.0.10_uf-aarch64-linux-x11.zip'
                with zipfile.ZipFile(self.base / 'downloads' / name, 'w') as archive:
                    for path in usr.rglob('*'):
                        if path.is_file():
                            archive.write(path, path.relative_to(usr))
            digest = hashlib.sha256((self.base / 'downloads' / name).read_bytes()).hexdigest()
            lines.append(f'{digest}  {name}\n')
        (self.base / 'downloads/sha256checksums.txt').write_text(''.join(lines))

    def test_both_variants_metadata_payload_index_and_repeat_update(self):
        self.fixture()
        self.env['MAINTAINER'] = r'Alice / Ops & Team | Back\Slash <alice@example.com>'
        self.run_update()
        self.assertEqual(len(self.artifacts()), 2)
        for package in self.artifacts():
            metadata = fields(package)
            arch = metadata['architecture']
            self.assertEqual(metadata['package'], 'usbimager-gtk' if arch == 'amd64' else 'usbimager-x11')
            self.assertEqual(metadata['version'], '1.0.10-1')
            self.assertEqual(metadata['maintainer'], self.env['MAINTAINER'])
            self.assertEqual(metadata['provides'], 'usbimager')
            self.assertEqual(metadata['x-publisher-stream'], 'usbimager')
            self.assertRegex(metadata['x-build-inputs-sha256'], r'^[a-f0-9]{64}$')
            self.assertGreater(int(metadata['installed-size']), 0)
            self.assertIn(f"Installed-Size: {metadata['installed-size']}\n", self.index(arch))
            self.assertIn('libgtk-3-0t64' if arch == 'amd64' else 'libx11-6', metadata['depends'])
            data = subprocess.check_output(['dpkg-deb', '--fsys-tarfile', str(package)])
            with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                self.assertEqual(archive.getmember('./usr/bin/usbimager').mode, 0o755)
                self.assertEqual(archive.getmember('./usr/bin/usbimager').uid, 0)
                self.assertIsNotNone(archive.getmember(f"./usr/share/doc/{metadata['package']}/copyright"))
                if arch == 'arm64':
                    self.assertIsNotNone(archive.getmember('./usr/share/doc/usbimager-x11/font-license'))
        original = {p: p.read_bytes() for p in self.artifacts()}
        self.run_update()
        self.assertEqual({p: p.read_bytes() for p in self.artifacts()}, original)

    def test_missing_architecture_is_filled_later(self):
        self.fixture(missing_arm64=True)
        self.run_update()
        self.assertEqual(len(self.artifacts()), 1)
        self.fixture()
        self.run_update()
        self.assertEqual(self.versions('usbimager'), {'1.0.10-1'})
        self.assertEqual(len(self.artifacts()), 2)

    def test_stale_installed_size_is_recalculated(self):
        def large_file(usr, arch):
            with (usr / 'bin/usbimager').open('ab') as output:
                output.write(b'x' * (2 * 1024 * 1024))
        self.fixture(installed_size=1, mutation=large_file)
        self.env['ARCHES'] = 'amd64'
        self.run_update()
        metadata = fields(self.artifacts()[0])
        self.assertGreater(int(metadata['installed-size']), 2048)
        self.assertIn(f"Installed-Size: {metadata['installed-size']}\n", self.index())

    def test_bad_digest_is_rejected(self):
        self.fixture()
        path = self.base / 'downloads/usbimager_1.0.10-amd64.deb'
        path.write_bytes(path.read_bytes() + b'corruption')
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_required_layout_architecture_and_dependencies_are_checked(self):
        def missing(usr, arch):
            (usr / 'share/applications/usbimager.desktop').unlink()
        def wrong_machine(usr, arch):
            path = usr / 'bin/usbimager'
            data = bytearray(path.read_bytes())
            struct.pack_into('<H', data, 18, 3)
            path.write_bytes(data)
        def unknown_library(usr, arch):
            path = usr / 'bin/usbimager'
            path.write_bytes(path.read_bytes().replace(b'libc.so.6', b'evil.so.6'))
        for mutation in (missing, wrong_machine, unknown_library):
            with self.subTest(mutation=mutation.__name__):
                self.fixture(mutation=mutation)
                self.run_update(expected=1)
                self.assertEqual(self.artifacts(), [])

    def test_import_rejects_wrong_package_metadata(self):
        self.fixture()
        root = self.base / 'upstream-amd64'
        control = root / 'DEBIAN/control'
        control.write_text(control.read_text().replace('Package: usbimager', 'Package: wrong'))
        destination = self.base / 'downloads/usbimager_1.0.10-amd64.deb'
        subprocess.run(['dpkg-deb', '--build', str(root), str(destination)], check=True, capture_output=True)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        manifest = self.base / 'downloads/sha256checksums.txt'
        lines = manifest.read_text().splitlines()
        lines[0] = f'{digest}  {destination.name}'
        manifest.write_text('\n'.join(lines) + '\n')
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_query_orders_versions_numerically_and_selects_requested_architecture(self):
        self.fixture()
        manifest = self.base / 'downloads/sha256checksums.txt'
        manifest.write_text(manifest.read_text() + 'a' * 64 + '  usbimager_1.0.9-amd64.deb\n')
        self.env['ARCHES'] = 'arm64'
        workspace = self.base / 'query'
        workspace.mkdir()
        subprocess.run([str(self.base / 'adapters/usbimager/query')],
                       env={**self.env, 'WORKSPACE': str(workspace),
                            'ADAPTER_DIR': str(self.base / 'adapters/usbimager')}, check=True)
        self.assertEqual((workspace / 'targets.tsv').read_text(), '1.0.10\tarm64\n')
        self.assertEqual(set(json.loads((workspace / 'assets.json').read_text())), {'arm64'})

    def test_new_release_does_not_fall_back_to_older_architecture(self):
        self.fixture()
        manifest = self.base / 'downloads/sha256checksums.txt'
        manifest.write_text(manifest.read_text() + 'a' * 64 + '  usbimager_1.0.11-amd64.deb\n')
        self.env['ARCHES'] = 'arm64'
        self.run_update()
        self.assertEqual(self.artifacts(), [])

    def test_malformed_and_duplicate_checksums_fail(self):
        self.fixture()
        manifest = self.base / 'downloads/sha256checksums.txt'
        original = manifest.read_text()
        for text in ('bad checksum\n', original + original, ''):
            with self.subTest(text=text[:30]):
                manifest.write_text(text)
                self.run_update(expected=1)
                self.assertEqual(self.artifacts(), [])

    def test_zip_rejects_links_traversal_and_extra_files(self):
        self.env['ARCHES'] = 'arm64'
        for kind in ('link', 'traversal', 'extra'):
            with self.subTest(kind=kind):
                self.fixture()
                path = self.base / 'downloads/usbimager_1.0.10_uf-aarch64-linux-x11.zip'
                with zipfile.ZipFile(path, 'a') as archive:
                    if kind == 'link':
                        entry = zipfile.ZipInfo('link')
                        entry.create_system = 3
                        entry.external_attr = 0o120777 << 16
                        archive.writestr(entry, '/etc/passwd')
                    else:
                        archive.writestr('../escape' if kind == 'traversal' else 'extra', b'x')
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                manifest = self.base / 'downloads/sha256checksums.txt'
                lines = manifest.read_text().splitlines()
                lines[-1] = f'{digest}  {path.name}'
                manifest.write_text('\n'.join(lines) + '\n')
                self.run_update(expected=1)
                self.assertEqual(self.artifacts(), [])
