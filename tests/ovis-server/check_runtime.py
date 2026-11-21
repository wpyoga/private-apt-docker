"""Run the real amd64 packages with private configuration and loopback HTTP."""

import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request


package, core_package, context = map(Path, sys.argv[1:])
root = context / 'root'
for archive in [package, core_package]:
    architecture = subprocess.check_output(['dpkg-deb', '--field', str(archive), 'Architecture'], text=True).strip()
    if architecture != 'amd64':
        raise SystemExit(f'{archive}: this runtime check requires amd64')
    subprocess.run(['dpkg-deb', '--extract', str(archive), str(root)], check=True)
for name in ['home', 'config', 'state', 'cache', 'data', 'run']:
    (context / name).mkdir(mode=0o700)
core = root / 'usr/bin/herdr-core'
binary = root / 'usr/lib/ovis-server/ovis-server'
with socket.socket() as listener:
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
env = {
    'HOME': str(context / 'home'), 'USER': os.environ.get('USER', ''),
    'PATH': f'{root / "usr/bin"}:/usr/bin:/bin', 'SHELL': '/bin/sh', 'LANG': 'C.UTF-8',
    'XDG_CONFIG_HOME': str(context / 'config'), 'XDG_STATE_HOME': str(context / 'state'),
    'XDG_DATA_HOME': str(context / 'data'), 'XDG_CACHE_HOME': str(context / 'cache'),
    'XDG_RUNTIME_DIR': str(context / 'run'), 'HC_SESSION': 't',
    'OVIS_RUNTIME': 'herdr-core', 'OVIS_HC_BIN': str(core),
    'OVIS_STATE_DIR': str(context / 'state/ovis-server'),
    'OVIS_ASSETS': str(root / 'usr/share/ovis-server'),
    'OVIS_TELEMETRY': '0', 'DO_NOT_TRACK': '1', 'HOST': '127.0.0.1', 'PORT': str(port),
}
env['OVIS_HC_ENV'] = json.dumps(env)
origin = f'http://127.0.0.1:{port}'
with (context / 'server.log').open('w') as log:
    process = subprocess.Popen([str(binary), 'serve'], env=env, cwd=env['HOME'],
                               stdout=log, stderr=log, start_new_session=True)
    try:
        for attempt in range(100):
            if process.poll() is not None:
                raise RuntimeError(f'Ovis exited with {process.returncode}; see {context / "server.log"}')
            try:
                with urllib.request.urlopen(origin + '/api/health', timeout=1) as response:
                    health = json.load(response)
                break
            except (OSError, ValueError):
                time.sleep(0.2)
        else:
            raise RuntimeError('Ovis did not answer /api/health within 20 seconds')
        print('Health:', json.dumps(health), flush=True)
        with urllib.request.urlopen(origin + '/', timeout=5) as response:
            html = response.read().decode()
        assert '<html' in html.lower(), 'The browser page is not HTML'
        with urllib.request.urlopen(origin + '/api/updates', timeout=5) as response:
            updates = json.load(response)
        assert updates['managed'] is False, updates
        assert 'Runtime: herdr-core' in (context / 'server.log').read_text()
        result = subprocess.run([str(core), 'server', 'status'], env=env, text=True,
                                capture_output=True, timeout=10)
        print('Core status:', result.stdout, result.stderr, flush=True)
        assert result.returncode == 0
        assert health.get('ok') is True, health
        assert health['herdr']['runtime'] == 'herdr-core', health
        assert health['herdr']['terminal_attach'] is True, health
        print('Browser HTML, health, Herdr core, and disabled in-app updates passed.', flush=True)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        result = subprocess.run([str(core), 'server', 'stop'], env=env, text=True,
                                capture_output=True, timeout=15)
        print('Core cleanup:', result.returncode, result.stdout, result.stderr, flush=True)
