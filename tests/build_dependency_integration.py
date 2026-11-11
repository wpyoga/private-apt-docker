"""Optional real-Docker test; never uses production storage or signing keys."""

import os
from pathlib import Path
import shutil
import subprocess
import time

from tests.lib.publisher_test_support import ROOT, PublisherTestCase, fields


def main():
    fixture = PublisherTestCase()
    fixture.setUp()
    base = fixture.base
    # Failed fixture data must outlive the Python process for diagnosis.
    fixture.temporary._finalizer.detach()
    state = base / 'worker'
    (state / 'queue').mkdir(parents=True)
    (state / 'tmp').mkdir()
    image = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}',
                                     os.environ['BUILD_IMAGE']], text=True).strip()
    environment = {**fixture.env, 'ARCHES': 'amd64', 'BUILD_ARCH': 'amd64',
                   'TMPDIR': str(state / 'tmp'), 'BUILD_QUEUE_DIR': str(state / 'queue'),
                   'BUILD_IMAGE': image}
    fixture.env = environment
    provider = fixture.adapter('zzz-library', package='libpublisher-test1 libpublisher-test-dev', version='1.0')
    consumer = fixture.adapter('aaa-consumer', package='private-consumer', version='1.0')
    (consumer / 'build-dependencies').write_text('zzz-library libpublisher-test-dev >= 1\n')
    for adapter, name in ((provider, 'provider'), (consumer, 'consumer')):
        shutil.copyfile(ROOT / f'tests/fixtures/build-dependencies/{name}-build', adapter / 'build')
        (adapter / 'build').chmod(0o755)
    worker_log = (base / 'worker.log').open('w')
    worker = subprocess.Popen(['bash', str(ROOT / 'lib/build-worker.sh')],
                              env=environment, stdout=worker_log, stderr=subprocess.STDOUT,
                              start_new_session=True)
    try:
        deadline = time.monotonic() + 30
        while not (state / 'queue/worker.ready').exists():
            if worker.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(f'Worker did not start; inspect {base / "worker.log"}')
            time.sleep(0.1)
        result = subprocess.run(['bash', str(fixture.publisher / 'update.sh')],
                                env=environment, capture_output=True, text=True, timeout=600)
        (base / 'coordinator.log').write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f'Coordinator failed; inspect {base}')
        artifacts = fixture.artifacts('aaa-consumer')
        assert len(artifacts) == 1
        metadata = fields(artifacts[0])
        assert 'libpublisher-test-dev:amd64 (= 1.0-1)' in metadata['x-private-build-dependencies']
        assert 'libpublisher-test1:amd64 (= 1.0-1)' in metadata['x-private-build-dependencies']
        assert len(metadata['x-build-environment-sha256']) == 64
        assert artifacts[0].stat().st_uid == os.getuid()
        assert 'X-Private-Build-Dependencies:' in fixture.index()
        assert not list((state / 'queue').glob('job-*'))
        before = {path: path.read_bytes() for path in fixture.artifacts()}
        result = subprocess.run(['bash', str(fixture.publisher / 'update.sh')],
                                env=environment, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
        assert {path: path.read_bytes() for path in fixture.artifacts()} == before
        original_build = (consumer / 'build').read_text()
        (consumer / 'upstream-version').write_text('2.0\n')
        (consumer / 'build').write_text('#!/bin/bash\nexit 7\n')
        result = subprocess.run(['bash', str(fixture.publisher / 'update.sh')],
                                env=environment, capture_output=True, text=True, timeout=600)
        (base / 'failed-consumer.log').write_text(result.stdout + result.stderr)
        assert result.returncode == 1
        assert fixture.versions('aaa-consumer') == {'1.0-1'}
        failed_jobs = list((state / 'queue').glob('job-*'))
        assert len(failed_jobs) == 1
        assert (failed_jobs[0] / 'result').read_text().strip() != '0'
        assert (failed_jobs[0] / 'build.log').is_file()
        remaining = subprocess.check_output([
            'docker', 'ps', '-aq', '--filter', f'name=apt-build-{failed_jobs[0].name}-'], text=True)
        assert not remaining.strip(), remaining
        (consumer / 'build').write_text(original_build)
        result = subprocess.run(['bash', str(fixture.publisher / 'update.sh')],
                                env=environment, capture_output=True, text=True, timeout=600)
        (base / 'retried-consumer.log').write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
        assert fixture.versions('aaa-consumer') == {'1.0-1', '2.0-1'}
        print(f'Integration passed; fixture packages and logs retained: {base}')
    finally:
        worker.terminate()
        worker.wait(timeout=10)
        worker_log.close()


if __name__ == '__main__':
    main()
