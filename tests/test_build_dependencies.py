"""Private dependency ordering, selection, fingerprints, and worker boundaries."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess

from tests.lib.publisher_test_support import ROOT, PublisherTestCase, fields

SPEC = importlib.util.spec_from_file_location('build_dependencies', ROOT / 'lib/build-dependencies.py')
DEPENDENCIES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEPENDENCIES)


class DependencyTests(PublisherTestCase):
    def test_unconstrained_dependency_accepts_versions_before_zero(self):
        adapter = self.adapter()
        self.declare(adapter, 'provider provider-cli\n')
        dependency = DEPENDENCIES.read_dependencies(adapter)[0]
        self.assertTrue(DEPENDENCIES.version_matches('0~beta-1', dependency))

    def declare(self, adapter, text):
        (adapter / 'build-dependencies').write_text(text)

    def fake_worker(self):
        # Exercise the publisher's dispatch without needing Docker in offline tests.
        # The real context/worker boundary has separate tests below.
        (self.publisher / 'lib/isolated-build.sh').write_text('''#!/bin/bash
set -Eeuo pipefail
python3 -c 'import json,os; from pathlib import Path; p=Path(os.environ["WORKSPACE"]); m=json.loads((p/"build-dependencies.json").read_text()); assert m[os.environ["ARCHES"].split()[0]]["packages"]'
exec "$ADAPTER_DIR/build" "$@"
''')

    def test_dependency_order_and_same_cycle_packages(self):
        consumer = self.adapter('aaa-consumer')
        self.adapter('zzz-provider', package='library-dev library-runtime')
        self.declare(consumer, 'zzz-provider library-dev >= 1.2\n')
        self.fake_worker()
        self.run_update()
        events = (self.base / 'events').read_text().splitlines()
        self.assertEqual(events[:3], ['zzz-provider/query', 'zzz-provider/build', 'zzz-provider/build'])
        self.assertEqual(self.versions('aaa-consumer'), {'1.2.3-1'})
        self.run_update()
        self.assertEqual(len(self.artifacts('aaa-consumer')), 2)

    def test_cycles_unknown_providers_and_invalid_declarations_leave_independent_stream(self):
        first = self.adapter('first')
        second = self.adapter('second')
        self.adapter('unrelated')
        for declaration in ('second second-cli\n', 'absent library-dev\n',
                            'second second-cli != 1\n', 'second second-cli >= bad\n',
                            'second second-cli\nsecond second-cli\n'):
            with self.subTest(declaration=declaration):
                self.declare(first, declaration)
                self.declare(second, 'first first-cli\n')
                result = self.run_update(expected=1)
                self.assertEqual(self.versions('unrelated'), {'1.2.3-1'})
                self.assertEqual(self.artifacts('first'), [])
                self.assertEqual(self.artifacts('second'), [])
                self.assertNotIn('first/query', (self.base / 'events').read_text())

    def test_unsatisfied_version_skips_only_consumer(self):
        consumer = self.adapter('consumer')
        self.adapter('provider')
        self.adapter('unrelated')
        self.declare(consumer, 'provider provider-cli >= 9\n')
        result = self.run_update(expected=1)
        self.assertIn('no complete amd64 build of provider', result.stderr)
        self.assertEqual(self.artifacts('consumer'), [])
        self.assertEqual(len(self.artifacts('unrelated')), 2)

    def test_dependency_update_rebuilds_current_consumer_and_then_settles(self):
        consumer = self.adapter('consumer')
        provider = self.adapter('provider')
        self.declare(consumer, 'provider provider-cli\n')
        self.fake_worker()
        self.run_update()
        original = {path: path.read_bytes() for path in self.artifacts()}
        (provider / 'upstream-version').write_text('2.0\n')
        self.run_update()
        self.assertEqual(self.versions('consumer'), {'1.2.3-1', '1.2.3-2'})
        self.assertEqual({path: path.read_bytes() for path in original}, original)
        self.run_update()
        self.assertEqual(self.versions('consumer'), {'1.2.3-1', '1.2.3-2'})

    def test_failed_provider_can_use_previous_complete_artifacts(self):
        consumer = self.adapter('consumer')
        provider = self.adapter('provider', package='library-dev library-runtime')
        self.declare(consumer, 'provider library-dev\n')
        self.fake_worker()
        self.run_update()
        (provider / 'query').write_text('#!/bin/bash\nexit 7\n')
        (consumer / 'upstream-version').write_text('2.0\n')
        self.run_update(expected=1)
        self.assertIn('2.0-1', self.versions('consumer'))

    def test_one_missing_architecture_does_not_block_available_target(self):
        consumer = self.adapter('consumer')
        self.adapter('provider', query='printf "1.2.3\\tamd64\\n" > "$WORKSPACE/targets.tsv"\n')
        self.declare(consumer, 'provider provider-cli\n')
        self.fake_worker()
        self.run_update(expected=1)
        self.assertEqual([fields(path)['architecture'] for path in self.artifacts('consumer')], ['amd64'])

    def test_complete_set_selection_uses_debian_order_and_checks_stream_identity(self):
        self.adapter('provider', package='library-dev library-runtime', version='1.10')
        self.run_update()
        # A higher incomplete output set and a same-name package from another
        # stream cannot displace this provider's complete build.
        self.legacy('library-dev', '99-1', 'amd64')
        consumer = self.adapter('consumer')
        self.declare(consumer, 'provider library-dev\n')
        self.fake_worker()
        self.run_update()
        self.assertEqual(self.versions('consumer'), {'1.2.3-1'})

    def test_context_contains_verified_packages_and_no_signing_environment(self):
        self.adapter('provider')
        self.run_update()
        consumer = self.adapter('consumer')
        self.declare(consumer, 'provider provider-cli\n')
        self.env.update(ADAPTER_DIR=str(consumer), PUBLISHER_STREAM='consumer',
                        WORKSPACE=str(self.base / 'workspace'), BUILD_INPUTS_SHA256='a' * 64,
                        BINARY_PACKAGES='consumer-cli', SECRET_TOKEN='must-not-leak')
        workspace = Path(self.env['WORKSPACE'])
        workspace.mkdir()
        (workspace / 'targets.tsv').write_text('1.2.3\tamd64\n')
        subprocess.run(['python3', str(ROOT / 'lib/build-dependencies.py'), 'prepare'],
                       env=self.env, capture_output=True, check=True)
        context = self.base / 'context'
        context.mkdir()
        subprocess.run(['python3', str(ROOT / 'lib/build-context.py'), str(context), 'amd64'],
                       env=self.env, capture_output=True, check=True)
        environment = (context / 'environment').read_text()
        self.assertNotIn('GNUPGHOME', environment)
        self.assertNotIn('GPG_KEY', environment)
        self.assertNotIn('SECRET_TOKEN', environment)
        self.assertIn('provider-cli:amd64=1.2.3-1', (context / 'install').read_text())
        self.assertIn('Package: provider-cli', (context / 'repository/Packages').read_text())
        self.assertTrue((context / 'framework/adapter/build').is_file())
        manifest = json.loads((workspace / 'build-dependencies.json').read_text())
        manifest['amd64']['packages'][0]['sha256'] = '0' * 64
        (workspace / 'build-dependencies.json').write_text(json.dumps(manifest))
        other = self.base / 'other-context'
        other.mkdir()
        result = subprocess.run(['python3', str(ROOT / 'lib/build-context.py'), str(other), 'amd64'],
                                env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('dependency changed', result.stderr)

    def test_transitive_providers_build_first_and_propagate_rebuilds(self):
        consumer = self.adapter('aaa-consumer')
        middle = self.adapter('bbb-middle')
        library = self.adapter('zzz-library')
        self.declare(consumer, 'bbb-middle bbb-middle-cli\n')
        self.declare(middle, 'zzz-library zzz-library-cli\n')
        self.fake_worker()
        self.run_update()
        queries = [line for line in (self.base / 'events').read_text().splitlines()
                   if line.endswith('/query')]
        self.assertEqual(queries, ['zzz-library/query', 'bbb-middle/query', 'aaa-consumer/query'])
        (library / 'upstream-version').write_text('2.0\n')
        self.run_update()
        self.assertEqual(self.versions('aaa-consumer'), {'1.2.3-1', '1.2.3-2'})
        self.assertEqual(self.versions('bbb-middle'), {'1.2.3-1', '1.2.3-2'})

    def test_separate_architecture_cycles_converge_on_shared_revision(self):
        consumer = self.adapter('consumer')
        self.adapter('provider')
        self.declare(consumer, 'provider provider-cli\n')
        self.fake_worker()
        self.env['ARCHES'] = 'amd64'
        self.run_update()
        self.env['ARCHES'] = 'arm64'
        self.run_update()
        self.env['ARCHES'] = 'amd64'
        self.run_update()
        self.env['ARCHES'] = 'arm64'
        self.run_update()
        count = len(self.artifacts('consumer'))
        self.run_update()
        self.assertEqual(len(self.artifacts('consumer')), count)
        latest = [fields(path) for path in self.artifacts('consumer')
                  if fields(path)['version'] == '1.2.3-2']
        self.assertEqual({package['architecture'] for package in latest}, {'amd64', 'arm64'})
        self.assertEqual(len({package['x-build-inputs-sha256'] for package in latest}), 1)

    def test_no_worker_fails_consumer_without_running_build_directly(self):
        consumer = self.adapter('consumer')
        self.adapter('provider')
        self.declare(consumer, 'provider provider-cli\n')
        result = self.run_update(expected=1)
        self.assertIn('rebuild.sh', result.stderr)
        self.assertEqual(self.artifacts('consumer'), [])
        self.assertNotIn('consumer/build', (self.base / 'events').read_text())
