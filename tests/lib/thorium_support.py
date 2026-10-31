"""Thorium fixture packages and regression scenarios shared by its streams."""

import hashlib
import gzip
import json
from pathlib import Path
import shutil
import subprocess

from tests.lib.publisher_test_support import ROOT, fields

PREFIX = "opt/chromium.org/thorium"

CURL = '''#!/usr/bin/env python3
import os
from pathlib import Path
import shutil
import sys
args = sys.argv[1:]
url = next(arg for arg in args if arg.startswith("https://"))
if "api.github.com" in url:
    source = "gz83" if "/gz83/" in url else "alex"
    name = source + "-" + url.rsplit("page=", 1)[1] + ".json"
else:
    name = url.rsplit("/", 1)[1]
shutil.copyfile(Path(os.environ["TEST_DOWNLOADS"]) / name, args[args.index("-o") + 1])
'''


class ThoriumCases:
    stream = None

    def fixture(self, *, installed_size=None, missing=None, corrupt=False, wrong_arch=False):
        self.adapter_dir = self.base / "adapters" / self.stream
        shutil.copytree(ROOT / "packages" / "repack" / self.stream, self.adapter_dir)
        settings = dict(line.split("=", 1) for line in (self.adapter_dir / "settings").read_text().splitlines())
        self.gz83 = settings["ALLOW_BETA"] == "true"
        self.version = "156.0.8078.28" if self.gz83 else "138.0.7204.303"
        self.source = "gz83" if self.gz83 else "alex"
        curl = self.base / "bin/curl"
        curl.write_text(CURL)
        curl.chmod(0o755)
        assets = []
        targets = [("amd64", tier) for tier in ("SSE3", "SSE4", "AVX", "AVX2")]
        if self.gz83:
            targets.append(("arm64", "arm64"))
        for arch, tier in targets:
            package = self.base / f"upstream-{arch}-{tier}"
            (package / "DEBIAN").mkdir(parents=True)
            declared_arch = "arm64" if wrong_arch else arch
            control = ("Package: thorium-browser\n" + f"Version: {self.version}-1\n"
                       f"Architecture: {declared_arch}\nMaintainer: Upstream <upstream@example.com>\n"
                       "Depends: libc6 (>= 2.25),\n libnss3\nDescription: Thorium fixture\n Continued description\n"
                       "Conflicts: thorium-browser-unstable\nReplaces: thorium-browser-unstable\n")
            if installed_size is not None:
                control += f"Installed-Size: {installed_size}\n"
            (package / "DEBIAN/control").write_text(control)
            for script in ("postinst", "prerm", "postrm"):
                path = package / "DEBIAN" / script
                path.write_text("#!/bin/bash\nexit 99\n")
                path.chmod(0o755)
            required = {
                "thorium", "thorium-browser", "thorium_shell", "chrome-sandbox", "chrome_crashpad_handler",
                "chromedriver", "resources.pak", "icudtl.dat", "locales/en-US.pak", "thorium_shell.png",
                "WidevineCdm/LICENSE",
            }
            required.update(f"product_logo_{size}.png" for size in (16, 24, 32, 48, 64, 128, 256))
            required.add("apparmor.d/thorium-browser" if self.gz83 else "cron/thorium-browser")
            if self.gz83:
                required.add("pak")
            for name in required:
                path = package / PREFIX / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture\n")
            for name in ("thorium", "thorium_shell", "chrome-sandbox", "chrome_crashpad_handler", "chromedriver"):
                header = bytearray(64)
                header[:6] = b"\x7fELF\x02\x01"
                header[18:20] = (183 if arch == "arm64" else 62).to_bytes(2, "little")
                path = package / PREFIX / name
                path.write_bytes(header)
                path.chmod(0o4755 if name == "chrome-sandbox" else 0o755)
            if self.gz83:
                (package / PREFIX / "apparmor.d/thorium-browser").write_text(
                    "abi <abi/4.0>,\nprofile thorium-browser /opt/chromium.org/thorium/thorium "
                    "flags=(unconfined) {\n userns,\n include if exists <local/thorium-browser>\n}\n")
            outside = {
                "usr/bin/thorium-shell": "fixture\n",
                "usr/share/applications/thorium-browser.desktop":
                    "[Desktop Entry]\nName=Thorium Browser\nIcon=thorium-browser\nExec=/usr/bin/thorium-browser %U\n"
                    "[Desktop Action shell]\nExec=/usr/bin/thorium-shell %U\n",
                "usr/share/applications/thorium-shell.desktop":
                    "[Desktop Entry]\nName=Thorium Shell\nIcon=/opt/chromium.org/thorium/thorium_shell.png\n"
                    "Exec=/usr/bin/thorium-shell %U\n",
                "usr/share/applications/org.chromium.Thorium.desktop": "fixture\n",
                "usr/share/appdata/thorium-browser.appdata.xml":
                    "<component><id>thorium-browser.desktop</id><name>Thorium</name></component>\n",
                "usr/share/doc/thorium-browser/changelog.gz": "fixture\n",
                "usr/share/gnome-control-center/default-apps/thorium-browser.xml": "fixture\n",
                "usr/share/man/man1/thorium-browser.1.gz": "fixture\n",
            }
            for name, text in outside.items():
                path = package / name
                path.parent.mkdir(parents=True, exist_ok=True)
                if name.endswith(".gz"):
                    path.write_bytes(gzip.compress(text.encode(), mtime=0))
                else:
                    path.write_text(text)
            (package / "usr/bin/thorium-browser").symlink_to(f"/{PREFIX}/thorium-browser")
            if self.gz83:
                (package / "usr/bin/pak").symlink_to(f"/{PREFIX}/pak")
            else:
                (package / "usr/bin/pak").write_text("fixture\n")
                (package / "etc/cron.daily").mkdir(parents=True)
                (package / "etc/cron.daily/thorium-browser").symlink_to(f"/{PREFIX}/cron/thorium-browser")
            if missing:
                (package / missing).unlink()
            name = f"thorium-browser_{self.version}_{tier}.deb"
            archive = self.base / "downloads" / name
            subprocess.run([
                "dpkg-deb", "--threads-max=1", "-Zxz", "-z1",
                "--build", "--root-owner-group", str(package), str(archive),
            ], check=True, capture_output=True)
            # Fail the last amd64 tier to exercise all-output storage validation.
            digest = "0" * 64 if corrupt and tier == "AVX2" else hashlib.sha256(archive.read_bytes()).hexdigest()
            assets.append({"name": name, "digest": "sha256:" + digest,
                           "browser_download_url": f"https://fixtures.invalid/{name}"})
        self.release = {"tag_name": "M" + self.version, "name": "M156 Beta" if self.gz83 else "Stable",
                        "draft": False, "prerelease": False, "published_at": "2026-10-11T14:32:00Z",
                        "assets": assets}
        self.save_releases([self.release])

    def save_releases(self, releases, page=1):
        (self.base / f"downloads/{self.source}-{page}.json").write_text(json.dumps(releases))

    def unpack(self, artifact):
        target = self.base / ("unpacked-" + artifact.name)
        subprocess.run(["dpkg-deb", "--raw-extract", str(artifact), str(target)], check=True, capture_output=True)
        return target

    def test_packages_publish_size_and_preserve_private_payload(self):
        self.fixture()
        self.run_update()
        expected_count = 6 if self.gz83 else 5
        self.assertEqual(len(self.artifacts()), expected_count)
        for artifact in self.artifacts():
            metadata = fields(artifact)
            package = metadata["package"]
            self.assertIn(package, {self.stream, *(f"{self.stream}-{tier}" for tier in ("sse3", "sse4", "avx", "avx2"))})
            self.assertEqual(metadata["x-publisher-stream"], self.stream)
            self.assertEqual(metadata["maintainer"], self.env["MAINTAINER"])
            self.assertEqual(metadata["version"], self.version + "-1")
            stanza = next(text for text in self.index(metadata["architecture"]).split("\n\n")
                          if f"Package: {package}\n" in text + "\n")
            self.assertIn(f"Installed-Size: {metadata['installed-size']}\n", stanza + "\n")
            tree = self.unpack(artifact)
            measured = subprocess.check_output([
                "du", "--summarize", "--block-size=1024", "--exclude=DEBIAN", str(tree)], text=True).split()[0]
            self.assertEqual(metadata["installed-size"], measured)
            self.assertFalse((tree / "etc/cron.daily/thorium-browser").exists())
            if package == self.stream and metadata["architecture"] == "amd64":
                self.assertEqual(metadata["depends"], self.stream + "-avx (= " + self.version + "-1)")
                self.assertFalse((tree / "opt").exists())
                continue
            self.assertFalse((tree / "usr/bin/thorium-browser").exists())
            self.assertTrue((tree / f"opt/{package}/WidevineCdm/LICENSE").is_file())
            self.assertEqual((tree / f"opt/{package}/chrome-sandbox").stat().st_mode & 0o7777, 0o4755)
            self.assertNotIn("exit 99", (tree / "DEBIAN/postinst").read_text())
            self.assertNotIn("Conflicts:", (tree / "DEBIAN/control").read_text())
            desktop = (tree / f"usr/share/applications/{package}.desktop").read_text()
            self.assertIn(f"Exec=/usr/bin/{package} %U", desktop)
            self.assertIn(f"Exec=/usr/bin/{package}-shell %U", desktop)
            shell_desktop = (tree / f"usr/share/applications/{package}-shell.desktop").read_text()
            self.assertIn(f"Icon={package}-shell", shell_desktop)
            for script in ("postinst", "prerm", "postrm"):
                text = (tree / f"DEBIAN/{script}").read_text()
                self.assertNotIn("/opt/chromium.org", text)
                self.assertNotIn("thorium-browser.gpg", text)
            if self.gz83:
                profile = (tree / f"etc/apparmor.d/{package}").read_text()
                self.assertIn(f"profile {package} /opt/{package}/thorium", profile)
                self.assertIn(f"<local/{package}>", profile)
        self.run_update()
        self.assertEqual(len(self.artifacts()), expected_count)

    def test_stale_installed_size_is_replaced(self):
        self.fixture(installed_size=999999)
        self.run_update()
        self.assertTrue(all(fields(a)["installed-size"] != "999999" for a in self.artifacts()))

    def test_layout_failure_is_atomic(self):
        self.fixture(missing=PREFIX + "/resources.pak")
        result = self.run_update(expected=1)
        self.assertIn("Missing upstream path", result.stderr)
        self.assertEqual(self.artifacts(), [])

    def test_bad_digest_stores_nothing(self):
        self.fixture(corrupt=True)
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_wrong_architecture_is_rejected(self):
        self.fixture(wrong_arch=True)
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_truncated_xz_payload_names_archive_and_reader_failure(self):
        self.fixture()
        original = self.base / "downloads" / f"thorium-browser_{self.version}_SSE3.deb"
        truncated = self.base / "truncated.deb"
        truncated.write_bytes(original.read_bytes()[:-32])
        result = subprocess.run([
            "python3", str(self.adapter_dir / "stage.py"), "validate", str(truncated),
        ], env={
            **self.env,
            "ADAPTER_DIR": str(self.adapter_dir),
            "UPSTREAM_REPOSITORY": "gz83/thorium" if self.gz83 else "Alex313031/thorium",
            "ARCHITECTURE": "amd64",
            "PACKAGE_NAME": self.stream + "-sse3",
        }, text=True, capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(truncated), result.stderr)
        self.assertIn("payload reader exit status", result.stderr)

    def test_payload_reader_preserves_tar_and_ignores_inherited_xz_options(self):
        self.fixture()
        archive = self.base / "downloads" / f"thorium-browser_{self.version}_SSE3.deb"
        expected = subprocess.check_output(["dpkg-deb", "--fsys-tarfile", str(archive)])
        result = subprocess.run([
            "bash", str(self.adapter_dir / "payload-tar"), str(archive),
        ], env={**self.env, "XZ_DEFAULTS": "--memlimit-decompress=1",
                "XZ_OPT": "--not-a-real-option"}, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stdout, expected)

    def test_payload_reader_rejects_missing_xz_member(self):
        self.fixture()
        archive = self.base / "downloads" / f"thorium-browser_{self.version}_SSE3.deb"
        subprocess.run(["ar", "d", str(archive), "data.tar.xz"], check=True, capture_output=True)
        result = subprocess.run([
            "bash", str(self.adapter_dir / "payload-tar"), str(archive),
        ], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn(str(archive), result.stderr)
        self.assertIn("expected debian-binary, control.tar.xz, data.tar.xz", result.stderr)

    def test_announcements_and_pagination(self):
        self.fixture()
        announcement = {**self.release, "tag_name": "M999.0.0.0", "name": "Beta announcement", "assets": []}
        self.save_releases([announcement] * 100)
        self.save_releases([self.release], page=2)
        self.run_update()
        self.assertTrue(self.artifacts())
        self.assertEqual(self.versions(self.stream), {self.version + "-1"})

    def test_missing_asset_does_not_build(self):
        self.fixture()
        self.release["assets"] = []
        self.save_releases([self.release])
        self.run_update()
        self.assertEqual(self.artifacts(), [])

    def test_beta_policy_and_duplicate_asset_validation(self):
        self.fixture()
        if not self.gz83:
            self.release["name"] = "Beta release"
            self.save_releases([self.release])
            self.run_update()
            self.assertEqual(self.artifacts(), [])
            self.release["name"] = "Stable"
        self.release["assets"].append(self.release["assets"][0])
        self.save_releases([self.release])
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_malformed_matching_asset_fails_query(self):
        self.fixture()
        self.release["assets"][0]["digest"] = None
        self.save_releases([self.release])
        result = self.run_update(expected=1)
        self.assertIn("invalid SHA256", result.stderr)
        self.assertEqual(self.artifacts(), [])

    def test_missing_architecture_keeps_published_version(self):
        self.fixture()
        self.run_update()
        stored = {str(path): path.read_bytes() for path in self.artifacts()}
        self.release["assets"] = []
        self.save_releases([self.release])
        self.run_update()
        self.assertEqual({str(path): path.read_bytes() for path in self.artifacts()}, stored)

    def test_incomplete_newer_release_uses_complete_older_set(self):
        self.fixture()
        self.env["ARCHES"] = "amd64"
        newer = {**self.release, "tag_name": "M999.0.0.0", "name": "Stable", "assets": [
            {**asset, "name": asset["name"].replace(self.version, "999.0.0.0")}
            for asset in self.release["assets"][:3]
        ]}
        self.save_releases([newer, self.release])
        self.run_update()
        self.assertEqual(len(self.artifacts()), 5)
        self.assertEqual(self.versions(self.stream), {self.version + "-1"})

    def test_missing_one_cpu_tier_does_not_publish_partial_set(self):
        self.fixture()
        self.env["ARCHES"] = "amd64"
        self.release["assets"] = [asset for asset in self.release["assets"]
                                  if not asset["name"].endswith("_AVX2.deb")]
        self.save_releases([self.release])
        result = self.run_update()
        self.assertIn("Incomplete", result.stderr)
        self.assertEqual(self.artifacts(), [])

    def test_missing_output_resumes_shared_revision_without_overwriting(self):
        self.fixture()
        self.run_update()
        artifacts = self.artifacts()
        removed = next(path for path in artifacts if fields(path)["package"].endswith("-avx2"))
        preserved = {str(path): path.read_bytes() for path in artifacts if path != removed}
        removed.unlink()
        self.run_update()
        self.assertTrue(removed.exists())
        self.assertEqual(self.versions(self.stream), {self.version + "-1"})
        self.assertEqual({path: Path(path).read_bytes() for path in preserved}, preserved)
