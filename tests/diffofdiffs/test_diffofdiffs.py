"""Offline release, source-integrity, architecture and Debian packaging checks."""

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile

from tests.lib.publisher_test_support import ROOT, PublisherTestCase, fields

ADAPTER = ROOT / 'packages/rebuild/diffofdiffs'
SPEC = importlib.util.spec_from_file_location('diffofdiffs_source', ADAPTER / 'source.py')
SOURCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SOURCE)
LICENSES = ['LICENSE', 'NOTICE', 'THIRD_PARTY.md', 'LICENSES/GPL-2.0.txt',
            'LICENSES/Primer-MIT.txt', 'vendor/urcu/LICENSE', 'vendor/urcu/README.md']


class DiffofdiffsTests(PublisherTestCase):
    def setUp(self):
        super().setUp()
        self.adapter_dir = self.base / 'adapters/diffofdiffs'
        shutil.copytree(ADAPTER, self.adapter_dir)
        self.tree = self.base / 'source-tree'
        self.tree.mkdir()
        for name in ['Makefile', 'VERSION', 'README.md', 'GUIDE.md', *LICENSES]:
            path = self.tree / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('1.1.0\n' if name == 'VERSION' else f'fixture {name}\n')
        repository = self.base / 'git-tree'
        subprocess.run(['git', 'init', '--bare', '--quiet', str(repository)], check=True)
        command = ['git', '-c', 'core.autocrlf=false', f'--git-dir={repository}',
                   f'--work-tree={self.tree}']
        subprocess.run([*command, 'add', '--all', '--force'], check=True)
        tree_hash = subprocess.check_output([*command, 'write-tree'], text=True).strip()
        self.metadata = {'version': '1.1.0', 'commit': 'a' * 40, 'tree': tree_hash}
        (self.adapter_dir / 'source.json').write_text(json.dumps(self.metadata))
        self.archive = self.base / 'downloads/v1.1.0.tar.gz'
        with tarfile.open(self.archive, 'w:gz') as archive:
            archive.add(self.tree, arcname='diffofdiffs-1.1.0')
        self.release = {'tag_name': 'v1.1.0', 'draft': False, 'prerelease': False,
                        'assets': [], 'published_at': '2026-10-08T07:58:29Z'}
        self.workspace = self.base / 'workspace'
        self.workspace.mkdir()
        self.output = self.base / 'output'
        self.output.mkdir()
        self.env.update(ADAPTER_DIR=str(self.adapter_dir), WORKSPACE=str(self.workspace),
                        PUBLISHER_STREAM='diffofdiffs', BINARY_PACKAGES='diffofdiffs',
                        BUILD_INPUTS_SHA256='a' * 64, LIBGIT2_BUILD_ARCH='amd64')

    def query(self):
        (self.base / 'downloads/release.json').write_text(json.dumps(self.release))
        return subprocess.run([str(self.adapter_dir / 'query')], env=self.env,
                              capture_output=True, text=True)

    def build(self, architecture='amd64', version='1.1.0-1'):
        self.env['LIBGIT2_BUILD_ARCH'] = architecture
        self.env['TEST_ARCHITECTURE'] = architecture
        return subprocess.run([str(self.adapter_dir / 'build'), version, architecture, str(self.output)],
                              env=self.env, capture_output=True, text=True)

    def install_build_stubs(self):
        library_source = self.base / 'library.c'
        library_source.write_text('int fixture_git(void) { return 1; }\n')
        subprocess.run(['gcc', '-shared', '-fPIC', '-Wl,-soname,libgit2.so.1.9',
                        str(library_source), '-o', str(self.base / 'libgit2.so')],
                       check=True, capture_output=True)
        source = self.base / 'main.c'
        source.write_text('int fixture_git(void); int main(void) { return fixture_git() - 1; }\n')
        executable = self.base / 'fixture-executable'
        subprocess.run(['gcc', str(source), '-L' + str(self.base), '-lgit2', '-o', str(executable)],
                       check=True, capture_output=True)
        self.env['TEST_EXECUTABLE'] = str(executable)
        make = self.base / 'bin/make'
        make.write_text('''#!/usr/bin/env python3
import os
from pathlib import Path
import shutil
import struct
import sys
args = sys.argv[1:]
if 'install' in args:
    source = Path(args[args.index('-C') + 1])
    destination = Path(next(arg.split('=', 1)[1] for arg in args if arg.startswith('DESTDIR=')))
    executable = destination / 'usr/bin/diffofdiffs'
    executable.parent.mkdir(parents=True)
    data = bytearray(Path(os.environ['TEST_EXECUTABLE']).read_bytes())
    arch = os.environ.get('TEST_ARCHITECTURE', os.environ.get('LIBGIT2_BUILD_ARCH'))
    machine = 183 if arch == 'arm64' else 62
    if os.environ.get('TEST_WRONG_ELF'):
        machine = 62 if machine == 183 else 183
    struct.pack_into('<H', data, 18, machine)
    executable.write_bytes(data)
    executable.chmod(0o755)
    for name in ['LICENSE', 'NOTICE', 'THIRD_PARTY.md', 'LICENSES/GPL-2.0.txt', 'LICENSES/Primer-MIT.txt', 'vendor/urcu/LICENSE', 'vendor/urcu/README.md']:
        if name == os.environ.get('TEST_MISSING_DOC'):
            continue
        target = destination / 'usr/share/doc/diffofdiffs' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
''')
        make.chmod(0o755)
        for name in ['strip', 'aarch64-linux-gnu-strip']:
            path = self.base / 'bin' / name
            path.write_text('#!/bin/bash\nset -Eeuo pipefail\nexit 0\n')
            path.chmod(0o755)
        for name, target in [('gcc', 'x86_64-linux-gnu'), ('aarch64-linux-gnu-gcc', 'aarch64-linux-gnu')]:
            path = self.base / 'bin' / name
            path.write_text('#!/bin/bash\nset -Eeuo pipefail\n'
                            f'printf "%s\\n" "${{TEST_COMPILER_TARGET:-{target}}}"\n')
            path.chmod(0o755)
        shlibdeps = self.base / 'bin/dpkg-shlibdeps'
        shlibdeps.write_text("#!/bin/bash\nset -Eeuo pipefail\nprintf '%s\\n' 'shlibs:Depends=libc6 (>= 2.34), libgit2-1.9 (>= 1.9.0)'\n")
        shlibdeps.chmod(0o755)

    def test_query_verifies_source_for_both_architectures(self):
        result = self.query()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.workspace / 'targets.tsv').read_text(), '1.1.0\tamd64\n1.1.0\tarm64\n')
        self.assertEqual((self.workspace / 'source.sha256').read_text().strip(),
                         hashlib.sha256(self.archive.read_bytes()).hexdigest())
        self.assertEqual((self.workspace / 'release-date').read_text(), '2026-10-08T07:58:29Z\n')

    def test_other_release_and_prerelease_require_review(self):
        for key, value in [('tag_name', 'v1.2.0'), ('prerelease', True), ('draft', True)]:
            with self.subTest(key=key):
                original = dict(self.release)
                self.release[key] = value
                self.assertNotEqual(self.query().returncode, 0)
                self.assertFalse((self.workspace / 'targets.tsv').exists())
                self.release = original

    def test_tree_hash_is_independently_verified_by_git(self):
        SOURCE.validate(self.archive, self.metadata)
        self.metadata['tree'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'source tree checksum'):
            SOURCE.validate(self.archive, self.metadata)

    def test_unsafe_duplicate_and_link_members_are_rejected(self):
        for name, kind in [('diffofdiffs-1.1.0/../escape', tarfile.REGTYPE),
                           ('other-root/VERSION', tarfile.REGTYPE),
                           ('diffofdiffs-1.1.0/linked', tarfile.SYMTYPE),
                           ('diffofdiffs-1.1.0/VERSION', tarfile.REGTYPE)]:
            with self.subTest(name=name, kind=kind):
                path = self.base / 'invalid.tar.gz'
                with tarfile.open(path, 'w:gz') as archive:
                    archive.add(self.tree, arcname='diffofdiffs-1.1.0')
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    member.linkname = '/etc/passwd' if kind == tarfile.SYMTYPE else ''
                    archive.addfile(member, io.BytesIO(b''))
                with self.assertRaises(ValueError):
                    SOURCE.validate(path, self.metadata)

    def test_wrong_version_and_executable_bit_change_fail_source_validation(self):
        for name, contents, mode in [('VERSION', b'1.2.0\n', 0o644), ('README.md', b'fixture README.md\n', 0o755)]:
            path = self.base / 'changed.tar.gz'
            with tarfile.open(self.archive) as original, tarfile.open(path, 'w:gz') as changed:
                for member in original:
                    data = original.extractfile(member).read() if member.isfile() else None
                    if member.name == 'diffofdiffs-1.1.0/' + name:
                        data, member.mode, member.size = contents, mode, len(contents)
                    changed.addfile(member, io.BytesIO(data) if data is not None else None)
            with self.assertRaises(ValueError):
                SOURCE.validate(path, self.metadata)

    def test_native_package_metadata_payload_and_index_size(self):
        self.install_build_stubs()
        self.assertEqual(self.query().returncode, 0)
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        package = self.output / 'diffofdiffs_1.1.0-1_amd64.deb'
        metadata = fields(package)
        self.assertIn('libgit2-1.9 (>= 1.9.1)', metadata['depends'])
        self.assertNotIn('python', metadata['depends'])
        self.assertNotIn('git,', metadata['depends'])
        self.assertGreater(int(metadata['installed-size']), 0)
        index = subprocess.check_output(['dpkg-scanpackages', '--multiversion', str(self.output)],
                                        text=True, stderr=subprocess.DEVNULL)
        self.assertIn('Installed-Size: ' + metadata['installed-size'] + '\n', index)
        unpacked = self.base / 'unpacked'
        subprocess.run(['dpkg-deb', '-x', str(package), str(unpacked)], check=True)
        for name in ['README.md', 'GUIDE.md', 'copyright', *LICENSES]:
            self.assertTrue((unpacked / 'usr/share/doc/diffofdiffs' / name).is_file(), name)
        self.assertTrue((unpacked / 'usr/bin/diffofdiffs').is_file())

    def test_arm64_is_packaged_without_target_execution(self):
        self.install_build_stubs()
        self.assertEqual(self.query().returncode, 0)
        result = self.build('arm64')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(fields(next(self.output.glob('*.deb')))['architecture'], 'arm64')

    def test_changed_download_fails_before_build(self):
        self.assertEqual(self.query().returncode, 0)
        (self.workspace / 'source.tar.gz').write_bytes(b'changed source')
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_missing_notices_and_wrong_elf_are_rejected(self):
        self.install_build_stubs()
        self.assertEqual(self.query().returncode, 0)
        self.env['TEST_MISSING_DOC'] = 'NOTICE'
        result = self.build()
        self.assertIn('missing documentation NOTICE', result.stderr)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_wrong_elf_is_rejected(self):
        self.install_build_stubs()
        self.assertEqual(self.query().returncode, 0)
        self.env['TEST_WRONG_ELF'] = '1'
        self.assertIn('unexpected ELF', self.build().stderr)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_wrong_version_or_toolchain_fails_early(self):
        result = self.build(version='1.2.0-1')
        self.assertIn('does not match source', result.stderr)
        self.install_build_stubs()
        self.env['TEST_COMPILER_TARGET'] = 'aarch64-linux-gnu'
        result = subprocess.run([str(self.adapter_dir / 'build'), '1.1.0-1', 'amd64', str(self.output)],
                                env=self.env, capture_output=True, text=True)
        self.assertIn('gcc targets aarch64-linux-gnu', result.stderr)

    def test_publisher_dependency_order_repeat_and_both_architectures(self):
        self.install_build_stubs()
        self.adapter('libgit2-1.9', package='libgit2-dev libgit2-1.9', stream='libgit2-1.9', version='1.9.7')
        (self.base / 'downloads/release.json').write_text(json.dumps(self.release))
        (self.publisher / 'lib/isolated-build.sh').write_text('''#!/bin/bash
set -Eeuo pipefail
export LIBGIT2_BUILD_ARCH="$2"
export TEST_ARCHITECTURE="$2"
exec "$ADAPTER_DIR/build" "$@"
''')
        self.run_update()
        self.assertEqual(len(self.artifacts('diffofdiffs')), 2)
        original = {path: path.read_bytes() for path in self.artifacts()}
        self.run_update()
        self.assertEqual({path: path.read_bytes() for path in self.artifacts()}, original)
