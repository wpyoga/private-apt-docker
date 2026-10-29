"""Real curl transfers with connection resets, without contacting upstream."""

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import threading
import unittest

from tests.lib.publisher_test_support import ROOT


class DownloadTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "build").mkdir(exist_ok=True)

    def check_download(self, failures, *, corrupt=False):
        payload = b"verified download fixture\n"
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                if len(requests) <= failures:
                    self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                                               struct.pack("ii", 1, 0))
                    self.connection.close()
                    self.close_connection = True
                    return
                body = b"incorrect payload" if corrupt else payload
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                with tempfile.TemporaryDirectory(dir=ROOT / "build") as directory:
                    destination = Path(directory) / "archive"
                    url = f"http://127.0.0.1:{server.server_port}/archive"
                    digest = hashlib.sha256(payload).hexdigest()
                    result = subprocess.run(
                        ["bash", "-c",
                         'source "$1/lib/adapter/package.sh"; '
                         'verify_download "$2" "$3" "$4" reuse --retry-all-errors',
                         "bash", str(ROOT), url, str(destination), digest],
                        capture_output=True, text=True, timeout=20,
                    )
                    if failures < 4 and not corrupt:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(destination.read_bytes(), payload)
                        self.assertFalse(destination.with_suffix(".part").exists())
                    else:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertFalse(destination.exists())
                    self.assertEqual(len(requests), min(failures + 1, 4))
            finally:
                server.shutdown()
                worker.join(timeout=5)

    def test_retry_after_connection_reset(self):
        self.check_download(1)

    def test_retry_exhaustion_does_not_publish_partial_download(self):
        self.check_download(4)

    def test_recovered_transfer_still_requires_matching_checksum(self):
        self.check_download(1, corrupt=True)


CURL_STUB = '''#!/usr/bin/env python3
import os
from pathlib import Path
import sys

args = sys.argv[1:]
url = next(arg for arg in args if arg.startswith("https://"))
base = Path(os.environ["TEST_DOWNLOAD_DIRECTORY"])
with (base / "requests").open("a") as stream:
    stream.write(url + "\\n")
if "download.gimp.org" in url:
    headers = "".join(
        f"Link: <https://mirror{number}.example/archive>; rel=duplicate; pri={number}\\r\\n"
        for number in (1, 1, 2, 3, 4)
    )
    Path(args[args.index("--dump-header") + 1]).write_text(headers)
    raise SystemExit(56)
if os.environ["TEST_MIRROR_MODE"] == "unavailable":
    raise SystemExit(56)
body = b"expected"
if os.environ["TEST_MIRROR_MODE"] == "corrupt" and "mirror1." in url:
    body = b"incorrect"
Path(args[args.index("-o") + 1]).write_bytes(body)
'''


class MirrorTests(unittest.TestCase):
    def check_mirrors(self, mode):
        (ROOT / "build").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as directory:
            base = Path(directory)
            (base / "bin").mkdir()
            curl = base / "bin/curl"
            curl.write_text(CURL_STUB)
            curl.chmod(0o755)
            destination = base / "archive"
            environment = {
                **os.environ, "FRAMEWORK_DIR": str(ROOT), "WORKSPACE": str(base),
                "PATH": f"{base / 'bin'}:{os.environ['PATH']}",
                "TEST_DOWNLOAD_DIRECTORY": str(base), "TEST_MIRROR_MODE": mode,
            }
            result = subprocess.run(
                ["bash", str(ROOT / "packages/gimp-3.2/download-asset"),
                 "https://download.gimp.org/archive", str(destination),
                 hashlib.sha256(b"expected").hexdigest()],
                env=environment, capture_output=True, text=True, timeout=10,
            )
            requests = (base / "requests").read_text().splitlines()
            self.assertEqual(requests[0], "https://download.gimp.org/archive")
            count = {"available": 1, "corrupt": 2, "unavailable": 3}[mode]
            self.assertEqual(requests[1:],
                             [f"https://mirror{number}.example/archive"
                              for number in range(1, count + 1)])
            self.assertTrue((base / "archive.headers.failed").exists())
            if mode == "unavailable":
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(destination.exists())
            else:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(destination.read_bytes(), b"expected")

    def test_failed_primary_uses_advertised_mirror(self):
        self.check_mirrors("available")

    def test_corrupt_mirror_is_rejected_before_trying_next(self):
        self.check_mirrors("corrupt")

    def test_all_failed_mirrors_do_not_publish_archive(self):
        self.check_mirrors("unavailable")
