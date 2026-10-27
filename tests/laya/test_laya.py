"""Offline packaging checks; fixture modules deliberately fail if imported."""

import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import stat
import subprocess
import zipfile

from tests.lib.publisher_test_support import ROOT, PublisherTestCase, fields


CURL = '''#!/usr/bin/env python3
import os
from pathlib import Path
import shutil
import sys
args = sys.argv[1:]
url = next(arg for arg in args if arg.startswith("https://"))
name = "laya.json" if url == "https://pypi.org/pypi/laya/json" else url.rsplit("/", 1)[1]
shutil.copyfile(Path(os.environ["TEST_DOWNLOADS"]) / name, args[args.index("-o") + 1])
'''


class LayaTests(PublisherTestCase):
    def setUp(self):
        super().setUp()
        self.adapter_dir = self.base / "adapters/laya"
        shutil.copytree(ROOT / "packages/laya", self.adapter_dir)
        (self.base / "bin/curl").write_text(CURL)
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        self.output = self.base / "output"
        self.output.mkdir()
        self.context = {
            **self.env,
            "ADAPTER_DIR": str(self.adapter_dir),
            "WORKSPACE": str(self.workspace),
            "PUBLISHER_STREAM": "laya",
            "BUILD_INPUTS_SHA256": "b" * 64,
        }
        self.fixture()

    def wheel(self, project, version, files, *, symlink=None, bad_record=False):
        dist_info = f"{project}-{version}.dist-info"
        files = dict(files)
        record = io.StringIO()
        writer = csv.writer(record, lineterminator="\n")
        for name, data in files.items():
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            writer.writerow((name, f"sha256={digest}", str(len(data))))
        writer.writerow((f"{dist_info}/RECORD", "", ""))
        files[f"{dist_info}/RECORD"] = b"broken\n" if bad_record else record.getvalue().encode()
        name = f"{project}-{version}-py3-none-any.whl"
        path = self.base / "downloads" / name
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for relative, data in files.items():
                entry = zipfile.ZipInfo(relative)
                entry.external_attr = (stat.S_IFREG | 0o644) << 16
                if relative == symlink:
                    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(entry, data)
        return {
            "version": version, "name": name,
            "url": f"https://files.pythonhosted.org/fixtures/{name}",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def fixture(self, *, changes=None, symlink=None, bad_record=False):
        metadata = (
            "Metadata-Version: 2.4\nName: laya\nVersion: 1.2.3\nRequires-Python: >=3.10\n"
            "Requires-Dist: torch>=2.0.0\nRequires-Dist: transformers>=4.48.0\n"
            "Requires-Dist: safetensors>=0.4.0\nRequires-Dist: huggingface_hub>=0.20.0\n"
            "Requires-Dist: numpy>=1.20.0\n"
            'Requires-Dist: fastapi>=0.110.0; extra == "serve"\n'
            'Requires-Dist: uvicorn>=0.27.0; extra == "serve"\n'
            'Requires-Dist: python-multipart>=0.0.9; extra == "serve"\n'
            'Requires-Dist: pydantic>=2.0.0; extra == "structured"\n'
        )
        files = {
            "laya/__init__.py": b'__version__ = "1.2.3"\nraise RuntimeError("Do not run fixture code")\n',
            "laya/cli.py": b'raise RuntimeError("Do not run fixture code")\n',
            "laya/serve.py": b'raise RuntimeError("Do not run fixture code")\n',
            "laya/router.py": b'raise RuntimeError("Do not run fixture code")\n',
            "laya-1.2.3.dist-info/METADATA": metadata.encode(),
            "laya-1.2.3.dist-info/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            "laya-1.2.3.dist-info/entry_points.txt": b"[console_scripts]\nlaya = laya.cli:main\nlaya-serve = laya.serve:main\n",
            "laya-1.2.3.dist-info/licenses/LICENSE": b"Apache license fixture\n",
        }
        for name, value in (changes or {}).items():
            if value is None:
                files.pop(name)
            else:
                files[name] = value
        self.laya_files = files
        asset = self.wheel("laya", "1.2.3", files, symlink=symlink, bad_record=bad_record)
        self.release = {
            "info": {"name": "laya", "version": "1.2.3"},
            "urls": [{"filename": asset["name"], "url": asset["url"],
                      "digests": {"sha256": asset["sha256"]}, "yanked": False,
                      "upload_time_iso_8601": "2026-01-01T00:00:00Z"}],
        }
        self.save_release()
        click_files = {
            "click/__init__.py": b'raise RuntimeError("Do not run fixture code")\n',
            "click-8.4.2.dist-info/METADATA": (
                b"Name: click\nVersion: 8.4.2\nRequires-Python: >=3.10\n"
                b"Requires-Dist: colorama; platform_system == 'Windows'\n"
            ),
            "click-8.4.2.dist-info/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            "click-8.4.2.dist-info/licenses/LICENSE.txt": b"BSD license fixture\n",
        }
        click = self.wheel("click", "8.4.2", click_files)
        (self.adapter_dir / "click.json").write_text(json.dumps(click))

    def save_release(self):
        (self.base / "downloads/laya.json").write_text(json.dumps(self.release))

    def query(self, success=True, context=None):
        result = subprocess.run([str(self.adapter_dir / "query")], env=context or self.context,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def build(self, success=True, arch="amd64", version="1.2.3-1"):
        result = subprocess.run([str(self.adapter_dir / "build"), version, arch, str(self.output)],
                                env=self.context, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def test_query_architectures_and_context(self):
        self.query()
        self.assertEqual((self.workspace / "targets.tsv").read_text(), "1.2.3\tamd64\n1.2.3\tarm64\n")
        self.query(context={**self.context, "ARCHES": "arm64"})
        self.assertEqual((self.workspace / "targets.tsv").read_text(), "1.2.3\tarm64\n")
        for name in ("ADAPTER_DIR", "WORKSPACE", "ARCHES"):
            result = self.query(False, context={**self.context, name: ""})
            self.assertIn(f"{name} must", result.stderr)
        self.query(False, context={**self.context, "ARCHES": "i386"})

    def test_query_rejects_ineligible_releases(self):
        for version in ("1.2.3rc1", "1.2", "v1.2.3"):
            self.release["info"]["version"] = version
            self.save_release()
            self.query(False)
        self.fixture()
        self.release["urls"][0]["yanked"] = True
        self.save_release()
        self.query(False)
        self.fixture()
        self.release["urls"] *= 2
        self.save_release()
        self.query(False)
        self.release["urls"] = []
        self.save_release()
        self.query(False)

    def test_query_rejects_bad_metadata_and_download_fields(self):
        for field, value in (("url", "http://files.pythonhosted.org/bad.whl"),
                             ("url", "https://files.pythonhosted.org/bad path"),
                             ("digests", {"sha256": "bad"}), ("digests", {})):
            with self.subTest(field=field, value=value):
                self.fixture()
                self.release["urls"][0][field] = value
                self.save_release()
                self.query(False)
        (self.base / "downloads/laya.json").write_text("{bad json")
        self.query(False)

    def test_build_rejects_download_and_version_mismatches(self):
        self.query()
        self.build(False, version="1.2.4-1")
        self.build(False, arch="i386")
        wheel = self.base / "downloads/laya-1.2.3-py3-none-any.whl"
        wheel.write_bytes(b"corrupt download")
        result = self.build(False)
        self.assertIn("FAILED", result.stdout)
        self.assertFalse(list(self.output.iterdir()))

    def test_build_requires_context_and_checks_private_click(self):
        self.query()
        for name in ("ADAPTER_DIR", "WORKSPACE", "PUBLISHER_STREAM",
                     "BUILD_INPUTS_SHA256", "MAINTAINER"):
            result = subprocess.run(
                [str(self.adapter_dir / "build"), "1.2.3-1", "amd64", str(self.output)],
                env={**self.context, name: ""}, capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(f"{name} must", result.stderr)
        (self.base / "downloads/click-8.4.2-py3-none-any.whl").write_bytes(b"corrupt Click")
        self.build(False)
        self.assertFalse(list(self.output.iterdir()))

    def test_record_detects_changed_bytes_even_when_download_digest_matches(self):
        path = self.base / "downloads/laya-1.2.3-py3-none-any.whl"
        with zipfile.ZipFile(path) as archive:
            members = {entry.filename: archive.read(entry) for entry in archive.infolist()}
        members["laya/cli.py"] += b"# Bytes not accounted for in RECORD\n"
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in members.items():
                archive.writestr(name, data)
        self.release["urls"][0]["digests"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.save_release()
        self.query()
        result = self.build(False)
        self.assertIn("RECORD hash or size mismatch: laya/cli.py", result.stderr)
        self.assertFalse(list(self.output.iterdir()))

    def test_maintainer_escaping_and_private_click_pin_changes_revision(self):
        self.env["MAINTAINER"] = r"Test \ & | Name <test@localhost>"
        self.run_update()
        for path in self.artifacts("laya"):
            self.assertEqual(fields(path)["maintainer"], self.env["MAINTAINER"])
        pin = self.adapter_dir / "click.json"
        pin.write_text(pin.read_text() + "\n")
        self.run_update()
        self.assertEqual(self.versions("laya"), {"1.2.3-1", "1.2.3-2"})

    def test_build_rejects_changed_layout_metadata_dependencies_and_records(self):
        metadata = self.laya_files["laya-1.2.3.dist-info/METADATA"]
        cases = [
            ({"laya/cli.py": None}, None, False, "Missing laya wheel files"),
            ({"laya/__init__.py": b'__version__ = "0.0.0"'}, None, False, "module version"),
            ({"laya-1.2.3.dist-info/METADATA": metadata.replace(b"Version: 1.2.3", b"Version: 9.9.9")}, None, False, "Version"),
            ({"laya-1.2.3.dist-info/METADATA": metadata + b"Requires-Dist: surprise>=1\n"}, None, False, "core dependencies changed"),
            ({"laya-1.2.3.dist-info/METADATA": metadata.replace(b"fastapi>=0.110.0", b"fastapi>=99")}, None, False, "HTTP dependencies changed"),
            ({"laya-1.2.3.dist-info/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: py3-none-any\n"}, None, False, "pure Python"),
            ({"../escape": b"bad"}, None, False, "wheel path"),
            ({"laya/bad.pth": b"import bad"}, None, False, "wheel payload"),
            ({"laya/bad.so": b"native"}, None, False, "wheel payload"),
            ({}, "laya/cli.py", False, "file type"),
            ({}, None, True, "RECORD row"),
        ]
        for changes, symlink, bad_record, message in cases:
            with self.subTest(message=message):
                self.fixture(changes=changes, symlink=symlink, bad_record=bad_record)
                self.query()
                result = self.build(False)
                self.assertIn(message, result.stderr)
                self.assertFalse(list(self.output.iterdir()))

    def test_packages_contents_dependencies_and_installed_size(self):
        self.query()
        self.build(arch="arm64")
        packages = sorted(self.output.glob("*.deb"))
        self.assertEqual({fields(path)["package"] for path in packages}, {"python3-laya", "laya-cli", "laya-http"})
        for path in packages:
            metadata = fields(path)
            self.assertEqual(metadata["architecture"], "all")
            self.assertEqual(metadata["x-publisher-stream"], "laya")
            self.assertEqual(metadata["x-build-inputs-sha256"], "b" * 64)
            root = self.base / metadata["package"]
            subprocess.run(["dpkg-deb", "--raw-extract", str(path), str(root)], check=True, capture_output=True)
            size = subprocess.check_output(["du", "--summarize", "--block-size=1024", "--exclude=DEBIAN", str(root)], text=True).split()[0]
            self.assertEqual(metadata["installed-size"], size)
            if metadata["package"] == "python3-laya":
                self.assertIn("python3-pydantic (>= 2.0)", metadata["depends"])
                self.assertEqual(metadata["recommends"], "python3-accelerate (>= 1.1)")
                self.assertTrue((root / "usr/lib/laya/vendor/click/__init__.py").is_file())
                self.assertFalse((root / "usr/lib/python3/dist-packages/click").exists())
                self.assertTrue((root / "usr/share/doc/python3-laya/click-LICENSE").is_file())
            else:
                self.assertIn("python3-laya (= 1.2.3-1)", metadata["depends"])
                command = "laya" if metadata["package"] == "laya-cli" else "laya-serve"
                launcher = root / "usr/bin" / command
                self.assertIn('sys.path.insert(0, "/usr/lib/laya/vendor")', launcher.read_text())
                self.assertEqual(launcher.stat().st_mode & 0o777, 0o755)
                if command == "laya-serve":
                    self.assertIn("python3-python-multipart", metadata["depends"])
            self.assertFalse((root / "etc/apt").exists())
            self.assertFalse((root / "usr/lib/systemd").exists())

    def test_publish_all_architectures_repeat_and_recipe_revision(self):
        self.run_update()
        original = {path.name: path.read_bytes() for path in self.artifacts("laya")}
        self.assertEqual(len(original), 3)
        for arch in ("amd64", "arm64"):
            index = self.index(arch)
            for path in self.artifacts("laya"):
                metadata = fields(path)
                paragraph = next(block for block in index.split("\n\n")
                                 if f"Package: {metadata['package']}\n" in block + "\n")
                self.assertIn(f"Installed-Size: {metadata['installed-size']}\n", paragraph + "\n")
                self.assertIn("Architecture: all", paragraph)
        self.run_update()
        self.assertEqual(original, {path.name: path.read_bytes() for path in self.artifacts("laya")})
        with (self.adapter_dir / "launcher.in").open("a") as stream:
            stream.write("\n# Packaging revision fixture\n")
        self.run_update()
        self.assertEqual(self.versions("laya"), {"1.2.3-1", "1.2.3-2"})
        for path in self.artifacts("laya"):
            if path.name in original:
                self.assertEqual(path.read_bytes(), original[path.name])
