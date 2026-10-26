"""Offline Zed releases, ELF validation, package integration, and update tests."""

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
import unittest

from publisher_test_support import ROOT, PublisherTestCase, fields


LIBRARIES = (
    "libXdmcp.so.6", "libXau.so.6", "libxcb.so.1", "libxcb-xkb.so.1",
    "libxkbcommon-x11.so.0", "libstdc++.so.6", "libbsd.so.0",
    "libX11-xcb.so.1", "libxkbcommon.so.0",
)
DESKTOP = (
    "[Desktop Entry]\nType=Application\nName=Zed\nTryExec=zed\n"
    "Exec=zed %U\nIcon=zed\nMimeType=text/plain;x-scheme-handler/zed;\n"
    "Actions=NewWorkspace;\n\n[Desktop Action NewWorkspace]\n"
    "Exec=zed --new %U\nName=Open a new workspace\n"
)


@unittest.skipUnless(shutil.which("patchelf") and shutil.which("readelf"),
                     "Zed tests require patchelf and binutils")
class ZedTests(PublisherTestCase):
    def fixture(self, *, missing_arm64=False, mutation=None, corrupt_digest=False):
        shutil.copytree(ROOT / "packages/zed", self.base / "adapters/zed", dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"))
        assets = []
        for arch, target, machine in (("amd64", "x86_64", 62), ("arm64", "aarch64", 183)):
            if missing_arm64 and arch == "arm64":
                continue
            source = self.base / f"upstream-{arch}"
            if source.exists():
                shutil.rmtree(source)
            bundle = source / "zed.app"
            for directory in ("bin", "libexec", "lib", "share/applications",
                              "share/icons/hicolor/512x512/apps",
                              "share/icons/hicolor/1024x1024/apps"):
                (bundle / directory).mkdir(parents=True, exist_ok=True)
            binary = bundle / "bin/zed"
            shutil.copyfile("/bin/true", binary)
            # Use real ELF dynamic tables. ARM headers are inspected, never run.
            data = bytearray(binary.read_bytes())
            struct.pack_into("<H", data, 18, machine)
            binary.write_bytes(data)
            subprocess.run(["patchelf", "--set-rpath", "$ORIGIN/../lib", str(binary)],
                           check=True, capture_output=True)
            for soname in ("libstdc++.so.6", "libxcb.so.1", "libxkbcommon.so.0",
                           "libxkbcommon-x11.so.0", "libX11-xcb.so.1"):
                subprocess.run(["patchelf", "--add-needed", soname, str(binary)],
                               check=True, capture_output=True)
            shutil.copyfile(binary, bundle / "libexec/zed-editor")
            for name in LIBRARIES:
                shutil.copyfile(binary, bundle / "lib" / name)
            # libbsd belongs only to the discarded bundle's libXdmcp chain.
            subprocess.run(["patchelf", "--add-needed", "libbsd.so.0",
                            str(bundle / "lib/libXdmcp.so.6")], check=True, capture_output=True)
            (bundle / "licenses.md").write_text("Upstream license fixture\n")
            (bundle / "share/applications/dev.zed.Zed.desktop").write_text(DESKTOP)
            for size in (512, 1024):
                (bundle / f"share/icons/hicolor/{size}x{size}/apps/zed.png").write_bytes(b"icon")
            if mutation:
                mutation(bundle, arch)
            name = f"zed-linux-{target}.tar.gz"
            archive = self.base / "downloads" / name
            with tarfile.open(archive, "w:gz") as output:
                output.add(bundle, arcname="zed.app")
            digest = "0" * 64 if corrupt_digest else hashlib.sha256(archive.read_bytes()).hexdigest()
            assets.append({"name": name, "digest": "sha256:" + digest,
                           "browser_download_url": "https://fixtures.invalid/" + name})
        release = {"tag_name": "v1.2.3", "draft": False, "prerelease": False,
                   "published_at": "2026-10-23T13:45:48Z", "assets": assets}
        (self.base / "downloads/release.json").write_text(json.dumps(release))

    def query(self, success=True):
        workspace = self.base / "query"
        workspace.mkdir(exist_ok=True)
        environment = {**self.env, "WORKSPACE": str(workspace),
                       "ADAPTER_DIR": str(self.base / "adapters/zed")}
        result = subprocess.run([str(self.base / "adapters/zed/query")], env=environment,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return workspace

    def test_query_architectures_and_release_date(self):
        self.fixture()
        self.env["ARCHES"] = "arm64"
        workspace = self.query()
        self.assertEqual((workspace / "targets.tsv").read_text(), "1.2.3\tarm64\n")
        self.assertEqual((workspace / "release-date").read_text(), "2026-10-23T13:45:48Z\n")
        self.assertEqual(set(json.loads((workspace / "assets.json").read_text())), {"arm64"})

    def test_query_rejects_invalid_release_metadata(self):
        self.fixture()
        path = self.base / "downloads/release.json"
        original = json.loads(path.read_text())
        cases = [
            {**original, "tag_name": "v1.2.3-preview"},
            {**original, "tag_name": "v1.2"},
            {**original, "prerelease": True}, {**original, "draft": True},
            {**original, "assets": None},
            {**original, "assets": original["assets"] * 2},
        ]
        for release in cases:
            with self.subTest(release=release):
                path.write_text(json.dumps(release))
                self.query(success=False)
        path.write_text("{invalid")
        self.query(success=False)

    def test_query_rejects_missing_digests_and_invalid_urls(self):
        self.fixture()
        path = self.base / "downloads/release.json"
        original = path.read_text()
        for field, value in (("digest", None), ("digest", "sha256:bad"),
                             ("digest", "sha256:" + "a" * 64 + "\n"),
                             ("browser_download_url", "http://invalid/archive"),
                             ("browser_download_url", "https://invalid/bad url")):
            with self.subTest(field=field, value=value):
                release = json.loads(original)
                release["assets"][0][field] = value
                path.write_text(json.dumps(release))
                self.query(success=False)

    def test_package_layout_dependencies_metadata_and_size(self):
        self.fixture()
        self.run_update()
        for artifact in self.artifacts("zed"):
            metadata = fields(artifact)
            self.assertEqual(metadata["package"], "zed")
            self.assertEqual(metadata["version"], "1.2.3-1")
            self.assertEqual(metadata["maintainer"], self.env["MAINTAINER"])
            self.assertRegex(metadata["x-build-inputs-sha256"], r"^[0-9a-f]{64}$")
            for dependency in ("libstdc++6", "libxcb1", "libxkbcommon-x11-0",
                               "libvulkan1", "libwayland-client0", "ca-certificates"):
                self.assertIn(dependency, metadata["depends"])
            self.assertNotIn("libbsd0", metadata["depends"])
            self.assertNotIn("libxdmcp6", metadata["depends"])
            contents = subprocess.check_output(["dpkg-deb", "--fsys-tarfile", str(artifact)])
            with tarfile.open(fileobj=io.BytesIO(contents)) as archive:
                names = archive.getnames()
                self.assertFalse(any(".so" in name for name in names))
                self.assertIn("./usr/share/doc/zed/licenses.md", names)
                self.assertIn("./usr/share/doc/zed/copyright", names)
                self.assertEqual(archive.extractfile(
                    "./usr/share/applications/dev.zed.Zed.desktop").read().decode(), DESKTOP)
                for name in ("./usr/bin/zed", "./usr/lib/zed/bin/zed",
                             "./usr/lib/zed/libexec/zed-editor"):
                    member = archive.getmember(name)
                    self.assertEqual(member.mode, 0o755)
                    self.assertEqual((member.uid, member.gid), (0, 0))
            extracted = self.base / f"extract-{metadata['architecture']}"
            subprocess.run(["dpkg-deb", "--extract", artifact, extracted], check=True)
            for name in ("bin/zed", "libexec/zed-editor"):
                rpath = subprocess.check_output(
                    ["patchelf", "--print-rpath", str(extracted / "usr/lib/zed" / name)], text=True)
                self.assertEqual(rpath.strip(), "")
            actual_size = int(subprocess.check_output(
                ["du", "--summarize", "--block-size=1024", str(extracted)], text=True).split()[0])
            self.assertEqual(int(metadata["installed-size"]), actual_size)
            self.assertIn(f"Installed-Size: {actual_size}\n", self.index(metadata["architecture"]))

    def test_wrapper_passes_arguments_environment_and_exit_status(self):
        self.fixture()
        self.env["ARCHES"] = "amd64"
        self.run_update()
        extracted = self.base / "wrapper-package"
        subprocess.run(["dpkg-deb", "--extract", self.artifacts()[0], extracted], check=True)
        fake_cli = self.base / "fake-cli"
        fake_cli.write_text("#!/usr/bin/python3\nimport json,os,sys\n"
                            "print(json.dumps([os.environ['ZED_UPDATE_EXPLANATION'],sys.argv[1:]]))\n"
                            "sys.exit(37)\n")
        fake_cli.chmod(0o755)
        wrapper = extracted / "usr/bin/zed"
        # Relocate only the exec target; exercise the installed wrapper itself.
        wrapper.write_text(wrapper.read_text().replace("/usr/lib/zed/bin/zed", str(fake_cli)))
        arguments = ["a file.txt", "--new", "", "$(literal)"]
        result = subprocess.run([str(wrapper), *arguments], text=True, capture_output=True,
                                env={**os.environ, "ZED_UPDATE_EXPLANATION": "old value"})
        self.assertEqual(result.returncode, 37, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["Update Zed using APT.", arguments])

    def test_missing_architecture_and_repeat_updates(self):
        self.fixture(missing_arm64=True)
        self.run_update()
        original = self.artifacts()[0]
        original_bytes = original.read_bytes()
        self.run_update()
        self.assertEqual(len(self.artifacts()), 1)
        self.fixture()
        self.run_update()
        self.assertEqual(len(self.artifacts()), 2)
        self.assertEqual(original.read_bytes(), original_bytes)
        self.assertEqual(self.versions("zed"), {"1.2.3-1"})
        launcher = self.base / "adapters/zed/launcher.in"
        launcher.write_text(launcher.read_text() + "\n# Packaging change\n")
        self.run_update()
        self.assertEqual(self.versions("zed"), {"1.2.3-1", "1.2.3-2"})
        self.assertEqual(original.read_bytes(), original_bytes)

    def test_bad_digest_stores_nothing(self):
        self.fixture(corrupt_digest=True)
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_unknown_library_is_rejected_even_in_discarded_bundle(self):
        def mutation(bundle, arch):
            subprocess.run(["patchelf", "--add-needed", "libfuture.so.1",
                            str(bundle / "lib/libXdmcp.so.6")], check=True, capture_output=True)
        self.fixture(mutation=mutation)
        result = self.run_update(expected=1)
        self.assertIn("Unknown library libfuture.so.1", result.stderr)
        self.assertEqual(self.artifacts(), [])

    def test_wrong_elf_architecture_fails(self):
        def mutation(bundle, arch):
            path = bundle / "libexec/zed-editor"
            data = bytearray(path.read_bytes())
            struct.pack_into("<H", data, 18, 0)
            path.write_bytes(data)
        self.fixture(mutation=mutation)
        result = self.run_update(expected=1)
        self.assertIn("Wrong ELF architecture", result.stderr)
        self.assertEqual(self.artifacts(), [])

    def test_new_symbol_baseline_fails(self):
        def mutation(bundle, arch):
            path = bundle / "libexec/zed-editor"
            path.write_bytes(path.read_bytes().replace(b"GLIBC_2.34", b"GLIBC_9.99"))
        self.fixture(mutation=mutation)
        result = self.run_update(expected=1)
        self.assertIn("Unsupported Debian 13 symbol version GLIBC_9.99", result.stderr)
        self.assertEqual(self.artifacts(), [])

    def test_required_files_and_desktop_contract(self):
        def missing(bundle, arch):
            (bundle / "licenses.md").unlink()
        self.fixture(mutation=missing)
        result = self.run_update(expected=1)
        self.assertIn("Missing bundle file: licenses.md", result.stderr)
        def desktop(bundle, arch):
            (bundle / "share/applications/dev.zed.Zed.desktop").write_text("Exec=other\n")
        self.fixture(mutation=desktop)
        result = self.run_update(expected=1)
        self.assertIn("Unexpected desktop entry", result.stderr)

    def test_links_are_rejected_before_extraction(self):
        protected = self.base / "protected"
        protected.write_text("unchanged")
        def mutation(bundle, arch):
            (bundle / "licenses.md").unlink()
            (bundle / "licenses.md").symlink_to(protected)
        self.fixture(mutation=mutation)
        result = self.run_update(expected=1)
        self.assertIn("Unsupported archive entry type", result.stderr)
        self.assertEqual(protected.read_text(), "unchanged")
        self.assertEqual(self.artifacts(), [])

    def test_unexpected_root_and_path_traversal_are_rejected(self):
        for name in ("other.app/file", "zed.app/../../escaped"):
            with self.subTest(name=name):
                archive = self.base / "unsafe.tar.gz"
                with tarfile.open(archive, "w:gz") as output:
                    member = tarfile.TarInfo(name)
                    member.size = 1
                    output.addfile(member, io.BytesIO(b"x"))
                result = subprocess.run(["python3", str(ROOT / "packages/zed/inspect-bundle.py"),
                                         "archive", str(archive)], text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
