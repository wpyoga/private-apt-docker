"""Shared packaging contracts and declared recipe inputs."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AdapterHelperTests(unittest.TestCase):
    def test_template_replacement_escapes_human_values(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'in').write_text('@VALUE@\n')
            value = r'A & B | C\D'
            subprocess.run(['bash', '-c',
                'source "$1/lib/adapter/package.sh"; render_template "$2/in" "$2/out" VALUE "$3"',
                'bash', str(ROOT), str(base), value], check=True, capture_output=True)
            self.assertEqual((base / 'out').read_text(), value + '\n')

    def test_declared_helpers_change_checksum_and_invalid_paths_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            adapter = base / 'adapter'
            adapter.mkdir()
            (base / 'lib').mkdir()
            (base / 'Dockerfile').write_text('fixture')
            helper = base / 'lib/helper.sh'
            helper.write_text('one')
            declaration = adapter / 'helper-inputs'
            declaration.write_text('helper.sh\n')
            environment = {**os.environ, 'FRAMEWORK_DIR': str(base),
                           'ADAPTER_DIR': str(adapter), 'MAINTAINER': 'Fixture'}
            def checksum():
                return subprocess.run(['python3', str(ROOT / 'lib/checksum.py')],
                    env=environment, capture_output=True, text=True)
            first = checksum().stdout
            (base / 'lib/unrelated').write_text('unrelated')
            self.assertEqual(first, checksum().stdout)
            helper.write_text('two')
            self.assertNotEqual(first, checksum().stdout)
            before_permissions = checksum().stdout
            helper.chmod(0o755)
            self.assertNotEqual(before_permissions, checksum().stdout)
            link = base / 'lib/link'
            link.symlink_to(helper)
            declaration.write_text('link\n')
            self.assertNotEqual(checksum().returncode, 0)
            for invalid in ('../Dockerfile', '/tmp/nope', 'missing', 'helper.sh\nhelper.sh'):
                declaration.write_text(invalid + '\n')
                self.assertNotEqual(checksum().returncode, 0)

    def test_github_asset_requires_unique_valid_metadata(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            release = Path(directory) / 'release.json'
            asset = {'name': 'bundle', 'digest': 'sha256:' + 'a' * 64,
                     'browser_download_url': 'https://example.com/bundle'}
            def select(assets):
                release.write_text(json.dumps({'assets': assets}))
                return subprocess.run(['bash', '-c',
                    'source "$1/lib/adapter/github.sh"; select_github_asset "$2" bundle',
                    'bash', str(ROOT), str(release)], capture_output=True, text=True)
            self.assertEqual(select([]).stdout, '')
            self.assertEqual(select([asset]).returncode, 0)
            self.assertNotEqual(select([asset, asset]).returncode, 0)
            self.assertNotEqual(select([{**asset, 'digest': 'bad'}]).returncode, 0)
            self.assertNotEqual(select([{**asset, 'browser_download_url': 'http://example.com'}]).returncode, 0)

    def test_download_cache_policies_preserve_verified_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / 'source'
            destination = base / 'destination'
            source.write_bytes(b'expected')
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            def download(policy):
                return subprocess.run(['bash', '-c',
                    'source "$1/lib/adapter/package.sh"; verify_download "$2" "$3" "$4" "$5"',
                    'bash', str(ROOT), source.as_uri(), str(destination), digest, policy],
                    capture_output=True)
            self.assertEqual(download('reuse').returncode, 0)
            destination.write_bytes(b'wrong')
            self.assertNotEqual(download('reuse').returncode, 0)
            self.assertEqual(download('repair').returncode, 0)
            source.write_bytes(b'changed')
            self.assertNotEqual(download('refresh').returncode, 0)
            self.assertEqual(destination.read_bytes(), b'expected')
