"""Check the release manifest, Linux binaries, and fixed web archive layout."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile


def sha256(path):
    checksum = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def checked_file(workspace, entry, name):
    if not isinstance(entry, dict) or entry.get('file') != name:
        raise ValueError(f'ovis-server.json: expected file {name}')
    digest = entry.get('sha256')
    size = entry.get('size')
    if (not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)
            or type(size) is not int or size <= 0):
        raise ValueError(f'ovis-server.json: invalid SHA256 or size for {name}')
    path = workspace / name
    if path.stat().st_size != size or sha256(path) != digest:
        raise ValueError(f'{name}: bytes do not match ovis-server.json')
    return path


def check_elf(path, architecture):
    with path.open('rb') as source:
        header = source.read(20)
    machine = {'amd64': 62, 'arm64': 183}[architecture]
    if (len(header) != 20 or header[:6] != b'\x7fELF\x02\x01'
            or int.from_bytes(header[18:20], 'little') != machine):
        raise ValueError(f'{path.name}: invalid {architecture} ELF binary')
    dynamic = subprocess.check_output(['readelf', '--dynamic', str(path)], text=True)
    needed = set(re.findall(r'\(NEEDED\).*\[(.*?)\]', dynamic))
    allowed = {'libc.so.6', 'libm.so.6', 'libdl.so.2', 'libpthread.so.0',
               'librt.so.1'}
    allowed.add({'amd64': 'ld-linux-x86-64.so.2', 'arm64': 'ld-linux-aarch64.so.1'}[architecture])
    if needed - allowed:
        raise ValueError(f'{path.name}: unknown shared libraries: {sorted(needed - allowed)}')
    versions = subprocess.check_output(['readelf', '--version-info', str(path)], text=True)
    limits = {'GLIBC': (2, 41)}
    for family, version in re.findall(r'Name: (GLIBC)_([0-9.]+)', versions):
        if tuple(map(int, version.split('.'))) > limits[family]:
            raise ValueError(f'{path.name}: {family}_{version} exceeds Debian 13')


def stage_web(archive_path, destination):
    found = set()
    required = {'index.html', 'build.json', 'sw.js', 'manifest.webmanifest', 'THIRD_PARTY_NOTICES.md'}
    with tarfile.open(archive_path, 'r:gz') as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError(f'{archive_path.name}: unsafe path: {member.name}')
            name = str(path)
            if name in found or not (member.isfile() or member.isdir()):
                raise ValueError(f'{archive_path.name}: duplicate path or unexpected type: {member.name}')
            found.add(name)
            target = destination / path
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open('wb') as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o644)
    for name in required:
        path = destination / name
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f'{archive_path.name}: missing web file: {name}')
    build = json.loads((destination / 'build.json').read_text())
    if (not isinstance(build, dict) or not isinstance(build.get('revision'), str)
            or not re.fullmatch('[0-9a-f]{40,64}', build['revision']) or build.get('dirty') is not False):
        raise ValueError(f'{archive_path.name}: invalid build.json revision or dirty field')


def stage(workspace, version, architecture, destination):
    workspace = Path(workspace)
    destination = Path(destination)
    manifest_path = workspace / 'ovis-server.json'
    manifest = json.loads(manifest_path.read_text())
    if (not isinstance(manifest, dict) or type(manifest.get('schema')) is not int
            or manifest['schema'] != 1 or manifest.get('version') != version):
        raise ValueError(f'ovis-server.json: expected schema 1 and version {version}')
    for field in ['assets', 'pty', 'dist']:
        if not isinstance(manifest.get(field), dict):
            raise ValueError(f'ovis-server.json: invalid {field} object')
    platform = {'amd64': 'linux-x64', 'arm64': 'linux-arm64'}[architecture]
    server = checked_file(workspace, manifest.get('assets', {}).get(platform), f'ovis-server-{platform}')
    pty = checked_file(workspace, manifest.get('pty', {}).get(platform), f'ovis-pty-sidecar-{platform}')
    dist = checked_file(workspace, manifest.get('dist'), 'ovis-dist.tar.gz')
    check_elf(server, architecture)
    check_elf(pty, architecture)

    library = destination / 'usr/lib/ovis-server'
    (library / 'bin').mkdir(parents=True)
    shutil.copyfile(server, library / 'ovis-server')
    (library / 'ovis-server').chmod(0o755)
    shutil.copyfile(pty, library / 'bin/ovis-pty-sidecar')
    (library / 'bin/ovis-pty-sidecar').chmod(0o755)
    record = {'version': version, 'sha256': sha256(pty)}
    (library / 'bin/ovis-pty-sidecar.json').write_text(json.dumps(record) + '\n')
    stage_web(dist, destination / 'usr/share/ovis-server/dist')
    documentation = destination / 'usr/share/doc/ovis-server'
    documentation.mkdir(parents=True)
    shutil.copyfile(manifest_path, documentation / 'upstream-manifest.json')


if __name__ == '__main__':
    stage(*sys.argv[1:])
