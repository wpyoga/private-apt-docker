"""Build release tarballs with stored private dependencies in isolated workers."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from tests.lib.publisher_test_support import ROOT, PublisherTestCase, fields

ADAPTER = ROOT / 'packages/rebuild/diffofdiffs'
DESTINATION = ROOT / 'build/diffofdiffs'
PACKAGES = ['libgit2-1.9', 'libgit2-dev', 'libgit2-experimental1.9',
            'libgit2-experimental-dev', 'libgit2-fixtures']


def run(command, *, environment=None, log=None, timeout=900):
    if log is None:
        subprocess.run(command, env=environment, check=True, timeout=timeout)
    else:
        with log.open('w') as output:
            subprocess.run(command, env=environment, stdout=output, stderr=subprocess.STDOUT,
                           check=True, timeout=timeout)


def download_sources():
    cache = DESTINATION / 'downloads'
    cache.mkdir(parents=True, exist_ok=True)
    run(['curl', '-fLsS', '--retry', '3', '-H', 'Accept: application/vnd.github+json',
         'https://api.github.com/repos/ctrliq/diffofdiffs/releases/latest',
         '-o', str(cache / 'release.json')])
    metadata = json.loads((ADAPTER / 'source.json').read_text())
    archive = cache / f"v{metadata['version']}.tar.gz"
    if not archive.exists():
        run(['curl', '-fLsS', '--retry', '3',
             f"https://github.com/ctrliq/diffofdiffs/archive/refs/tags/v{metadata['version']}.tar.gz",
             '-o', str(archive)])
    specification = importlib.util.spec_from_file_location('diffofdiffs_source', ADAPTER / 'source.py')
    source = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(source)
    source.validate(archive, metadata)
    print('Verified release tarball SHA256: ' + hashlib.sha256(archive.read_bytes()).hexdigest())
    return cache, archive


def seed_repository(fixture):
    fixture.adapter('libgit2-1.9', package=' '.join(PACKAGES), stream='libgit2-1.9',
                    query=': > "$WORKSPACE/targets.tsv"\n')
    pool = Path(fixture.env['REPO_DIR']) / 'pool/main/libgit2-1.9'
    pool.mkdir(parents=True)
    for architecture in ['amd64', 'arm64']:
        directory = ROOT / f'build/libgit2-1.9/{architecture}/output'
        for name in PACKAGES:
            package_arch = 'all' if name == 'libgit2-fixtures' else architecture
            candidates = list(directory.glob(f'{name}_*_{package_arch}.deb'))
            if len(candidates) != 1:
                raise ValueError(f'{directory}: expected one verified {name} package')
            package = candidates[0]
            metadata = fields(package)
            if metadata['x-publisher-stream'] != 'libgit2-1.9' or metadata['architecture'] != package_arch:
                raise ValueError(f'{package}: unexpected stored dependency identity')
            target = pool / package.name
            if not target.exists():
                shutil.copyfile(package, target)
    consumer_pool = Path(fixture.env['REPO_DIR']) / 'pool/main/diffofdiffs'
    for package in DESTINATION.glob('*/output/diffofdiffs_*.deb'):
        metadata = fields(package)
        if metadata.get('x-publisher-stream') != 'diffofdiffs':
            raise ValueError(f'{package}: unexpected cached consumer identity')
        consumer_pool.mkdir(exist_ok=True)
        shutil.copyfile(package, consumer_pool / package.name)


def build_architecture(fixture, architecture):
    state = fixture.base / f'worker-{architecture}'
    (state / 'queue').mkdir(parents=True)
    (state / 'tmp').mkdir()
    image_name = f'private-apt-rebuild-{architecture}:local'
    image = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', image_name],
                                    text=True).strip()
    environment = {**fixture.env, 'ARCHES': architecture, 'BUILD_ARCH': architecture,
                   'TMPDIR': str(state / 'tmp'), 'BUILD_QUEUE_DIR': str(state / 'queue'),
                   'BUILD_IMAGE': image}
    log_directory = DESTINATION / 'logs'
    with (log_directory / f'worker-{architecture}.log').open('w') as output:
        worker = subprocess.Popen(['bash', str(ROOT / 'lib/build-worker.sh')], env=environment,
                                  stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 30
            while not (state / 'queue/worker.ready').exists():
                if worker.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError(f'{architecture}: build worker did not start')
                time.sleep(0.1)
            run(['bash', str(fixture.publisher / 'update.sh')], environment=environment,
                log=log_directory / f'publisher-{architecture}.log')
            packages = [path for path in fixture.artifacts('diffofdiffs')
                        if fields(path)['architecture'] == architecture]
            if not packages:
                raise ValueError(f'{architecture}: no diffofdiffs package was produced')
            package = packages[0]
            for candidate in packages[1:]:
                if subprocess.run(['dpkg', '--compare-versions', fields(candidate)['version'],
                                   'gt', fields(package)['version']]).returncode == 0:
                    package = candidate
            metadata = fields(package)
            assert metadata['version'].rpartition('-')[0] == '1.1.0'
            assert 'libgit2-1.9 (>= 1.9.1)' in metadata['depends']
            assert 'libgit2-dev:' in metadata['x-private-build-dependencies']
            assert int(metadata['installed-size']) > 0
            assert package.stat().st_uid == os.getuid()
            assert 'Installed-Size: ' + metadata['installed-size'] + '\n' in fixture.index(architecture)
            export = DESTINATION / architecture / 'output'
            export.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(package, export / package.name)
            before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in fixture.artifacts()}
            run(['bash', str(fixture.publisher / 'update.sh')], environment=environment,
                log=log_directory / f'repeat-{architecture}.log', timeout=120)
            assert before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in fixture.artifacts()}
            print(f'Built and indexed: {export / package.name}')
            return export / package.name
        finally:
            worker.terminate()
            worker.wait(timeout=30)


def installation_test(archive, package):
    context = DESTINATION / 'install-context'
    if context.exists():
        shutil.rmtree(context)
    (context / 'packages').mkdir(parents=True)
    for name in ['libgit2-1.9', 'libgit2-dev']:
        dependency = next((ROOT / 'build/libgit2-1.9/amd64/output').glob(f'{name}_*_amd64.deb'))
        shutil.copyfile(dependency, context / 'packages' / dependency.name)
    shutil.copyfile(package, context / 'packages' / package.name)
    shutil.copyfile(archive, context / 'source.tar.gz')
    shutil.copyfile(ROOT / 'tests/diffofdiffs/install.Dockerfile', context / 'Dockerfile')
    shutil.copyfile(ROOT / 'tests/diffofdiffs/smoke.py', context / 'smoke.py')
    shutil.copyfile(ROOT / 'tests/diffofdiffs/check-upstream.py', context / 'check-upstream.py')
    run(['docker', 'build', '--build-arg', f'USER_ID={os.getuid()}', '--build-arg', f'GROUP_ID={os.getgid()}',
         '-t', 'private-apt-diffofdiffs-install-test:local', str(context)],
        log=DESTINATION / 'logs/install-and-upstream-tests.log', timeout=900)


def main():
    cache, archive = download_sources()
    fixture = PublisherTestCase()
    fixture.setUp()
    fixture.temporary._finalizer.detach()
    print(f'Isolated repository and failure evidence: {fixture.base}')
    shutil.copytree(ADAPTER, fixture.base / 'adapters/diffofdiffs')
    for source in cache.iterdir():
        if source.is_file():
            shutil.copyfile(source, fixture.base / 'downloads' / source.name)
    seed_repository(fixture)
    outputs = {}
    for architecture in ['amd64', 'arm64']:
        outputs[architecture] = build_architecture(fixture, architecture)
    installation_test(archive, outputs['amd64'])
    print('Both architecture builds and native installation/upstream checks passed.')


if __name__ == '__main__':
    main()
