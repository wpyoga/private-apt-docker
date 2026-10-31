"""Offline GIMP AppImage tests with real SquashFS and Debian package tools."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
import unittest

from tests.lib.publisher_test_support import ROOT, PublisherTestCase, fields


TOOLS = all(shutil.which(name) for name in ("patchelf", "mksquashfs", "unsquashfs"))


@unittest.skipUnless(TOOLS, "GIMP tests require patchelf and squashfs-tools")
class GimpTests(PublisherTestCase):
    def fixture(self, *, missing_arm64=False, mutation=None):
        adapter = self.base / "adapters/gimp-3.2"
        shutil.copytree(ROOT / "packages/repack/gimp-3.2", adapter, dirs_exist_ok=True)
        assets = []
        for arch, target, multiarch, machine in (
            ("amd64", "x86_64", "x86_64-linux-gnu", 62),
            ("arm64", "aarch64", "aarch64-linux-gnu", 183),
        ):
            if arch == "arm64" and missing_arm64:
                continue
            source = self.base / f"upstream-{arch}"
            if source.exists():
                shutil.rmtree(source)
            usr = source / "usr"
            lib = usr / "lib" / multiarch
            directories = [
                usr / "bin", usr / "libexec", usr / "etc/gimp/3.0",
                usr / "share/gimp/3.0", usr / "share/applications",
                usr / "share/metainfo", usr / "share/icons/hicolor/48x48/apps",
                usr / "share/locale/en/LC_MESSAGES", lib / "pkgconfig",
                lib / "girepository-1.0", lib / "gimp/3.0/environ",
                lib / "babl-0.1", lib / "gegl-0.4",
                usr / "include/gimp-3.0", usr / "include/babl-0.1", usr / "include/gegl-0.4",
            ]
            for directory in directories:
                directory.mkdir(parents=True, exist_ok=True)
            for name in ("gimp-3.2", "gimp-console-3.2", "gimp-script-fu-interpreter-3.0", "gimptool-3.2"):
                path = usr / "bin" / name
                data = bytearray(Path("/bin/true").read_bytes())
                struct.pack_into("<H", data, 18, machine)
                path.write_bytes(data)
                path.chmod(0o755)
            shutil.copyfile(usr / "bin/gimp-3.2", usr / "libexec/gimp-debug-tool-3.2")
            (usr / "libexec/gimp-debug-tool-3.2").chmod(0o755)

            # The arm64 fixtures have ARM ELF headers but are never executed.
            obj = self.base / "fixture.o"
            subprocess.run(["as", "-o", obj], input=".text\n.global fixture\nfixture: ret\n",
                           text=True, check=True, capture_output=True)
            for name in ("gimp-3.0", "babl-0.1", "gegl-0.4"):
                soname = f"lib{name}.so.0"
                binary = lib / (soname + ".1")
                subprocess.run(["ld", "-shared", "-soname", soname, "-o", binary, obj],
                               check=True, capture_output=True)
                data = bytearray(binary.read_bytes())
                struct.pack_into("<H", data, 18, machine)
                binary.write_bytes(data)
                (lib / soname).symlink_to(binary.name)
                (lib / f"lib{name}.so").symlink_to(soname)
            for family in ("babl-0.1", "gegl-0.4"):
                shutil.copyfile(lib / "libbabl-0.1.so.0.1", lib / family / "fixture.so")
            shutil.copyfile(lib / "libbabl-0.1.so.0.1", lib / "libgegl-npd-0.4.so")
            for name in ("Gimp-3.0", "GimpUi-3.0", "Babl-0.1", "Gegl-0.4"):
                (lib / "girepository-1.0" / f"{name}.typelib").write_text("fixture typelib\n")
            for name, version in (("gimp-3.0", "3.2.6"), ("babl-0.1", "0.1.128"),
                                  ("gegl-0.4", "0.4.72"), ("gimpui-3.0", "3.2.6"),
                                  ("gimpthumb-3.0", "3.2.6")):
                (lib / "pkgconfig" / f"{name}.pc").write_text(
                    f"prefix=${{pcfiledir}}/../../..\nincludedir=${{prefix}}/include\n"
                    f"libdir=${{prefix}}/lib/{multiarch}\nName: {name}\nDescription: fixture\n"
                    f"Version: {version}\nLibs: -L${{libdir}} -l{name}\n"
                    f"Cflags: -I${{includedir}}/{name}\n")
            for name in ("gimp-3.0", "babl-0.1", "gegl-0.4"):
                (usr / "include" / name / "fixture.h").write_text("/* fixture header */\n")
            (usr / "etc/gimp/3.0/gimprc").write_text(
                "# configuration fixture\n(check-updates yes)\n")
            (lib / "gimp/3.0/environ/native-runtime.env").write_text("LIBHEIF_PLUGIN_PATH=/bad\n")
            (usr / "share/gimp/3.0/resource").write_bytes(b"x" * 16384)
            (usr / "share/applications/org.gimp.GIMP.Stable.desktop").write_text(
                "[Desktop Entry]\nType=Application\nName=GIMP\n"
                "Exec=org.gimp.GIMP.Stable %U\nIcon=org.gimp.GIMP.Stable\n")
            (usr / "share/metainfo/org.gimp.GIMP.Stable.appdata.xml").write_text("<component/>\n")
            (usr / "share/icons/hicolor/48x48/apps/gimp.png").write_bytes(b"fixture icon")
            (usr / "share/locale/en/LC_MESSAGES/gimp30.mo").write_bytes(b"fixture translation")
            # External bundle libraries must not leak into our private runtime.
            (lib / "libssl.so.3").write_bytes(b"discard this external library")

            extension = lib / "gimp/3.0/extensions/org.gimp.extension.goat-exercises"
            extension.mkdir(parents=True)
            for example in ("goat-exercise-gjs.js", "goat-exercise-lua.lua", "goat-exercise-py3.py"):
                (extension / example).write_text("# example fixture\n")
            (extension / "org.gimp.extension.goat-exercises.metainfo.xml").write_text(
                '<component><custom><value key="GIMP::plug-in-path">'
                'goat-exercise-py3.py:goat-exercise-gjs.js:goat-exercise-lua.lua'
                '</value></custom></component>\n')
            mng = lib / "gimp/3.0/plug-ins/file-mng/file-mng"
            mng.parent.mkdir(parents=True)
            shutil.copyfile(usr / "bin/gimp-3.2", mng)
            subprocess.run(["patchelf", "--add-needed", "libmng.so.1", mng],
                           check=True, capture_output=True)
            subprocess.run(["patchelf", "--add-needed", "libpng16.so.16",
                            lib / "libbabl-0.1.so.0.1"], check=True, capture_output=True)
            (usr / "share/gimp/3.0/gimp-release").write_text(
                "[package]\nrevision=7\ncheck-update=true\n")

            for path, soname in ((lib / "libgimp-3.0.so.0.1", "libpng16.so.16"),
                                 (usr / "bin/gimp-3.2", "libheif.so.1")):
                subprocess.run(["patchelf", "--add-needed", soname, path],
                               check=True, capture_output=True)

            if mutation:
                mutation(source, lib, arch)

            squashfs = self.base / f"{arch}.squashfs"
            squashfs.unlink(missing_ok=True)
            subprocess.run(["mksquashfs", source, squashfs, "-noappend", "-no-progress",
                            "-processors", "1"], check=True, capture_output=True)
            runtime = bytearray(Path("/bin/true").read_bytes())
            runtime[8:11] = b"AI\x02"
            struct.pack_into("<H", runtime, 18, machine)
            end = (struct.unpack_from("<Q", runtime, 40)[0]
                   + struct.unpack_from("<H", runtime, 58)[0]
                   * struct.unpack_from("<H", runtime, 60)[0])
            runtime = runtime[:end]
            name = f"GIMP-3.2.6-{target}.AppImage"
            archive = self.base / "downloads" / name
            archive.write_bytes(runtime + squashfs.read_bytes())
            assets.append({"filename": name, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                           "min-support": "Debian 13"})
        release = {"version": "3.2.6", "date": "2026-09-10", "appimage": assets}
        (self.base / "downloads/gimp_versions.json").write_text(json.dumps({"STABLE": [
            {"version": "3.4.0", "date": "2026-10-25"},
            {"version": "3.2.4", "date": "2026-04-17"}, release,
        ]}))
        docs = self.base / "docs/gimp-api-docs-3.2.6/reference/libgimp-3.0"
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "index.html").write_text("<html>API fixture</html>\n")
        archive = self.base / "downloads/gimp-api-docs-3.2.6.tar.xz"
        with tarfile.open(archive, "w:xz") as stream:
            stream.add(docs.parents[1], arcname="gimp-api-docs-3.2.6")
        (self.base / "downloads/SHA256SUMS").write_text(
            hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + archive.name + "\n")

    def query(self, success=True):
        workspace = self.base / "query"
        workspace.mkdir(exist_ok=True)
        result = subprocess.run([self.base / "adapters/gimp-3.2/query"],
                                env={**self.env, "ADAPTER_DIR": str(self.base / "adapters/gimp-3.2"),
                                     "BINARY_PACKAGES": (self.base / "adapters/gimp-3.2/config").read_text().split('BINARY_PACKAGES="')[1].split('"')[0],
                                     "WORKSPACE": str(workspace)}, text=True, capture_output=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return workspace, result

    def test_query_follows_32_and_requested_architecture(self):
        self.fixture()
        self.env["ARCHES"] = "arm64"
        workspace, _ = self.query()
        self.assertEqual((workspace / "targets.tsv").read_text(), "3.2.6\tarm64\n")
        self.assertEqual((workspace / "release-date").read_text(), "2026-09-10T00:00:00Z\n")
        self.assertEqual(set(json.loads((workspace / "assets.json").read_text())), {"arm64"})

    def test_query_rejects_bad_metadata_digest_baseline_and_duplicates(self):
        self.fixture()
        path = self.base / "downloads/gimp_versions.json"
        original = path.read_text()
        for change in ("json", "shape", "digest", "baseline", "duplicate", "rebuild", "date"):
            with self.subTest(change=change):
                data = json.loads(original)
                release = data["STABLE"][-1]
                if change == "shape": data["STABLE"] = {}
                if change == "digest": release["appimage"][0]["sha256"] = "bad"
                if change == "baseline": release["appimage"][0]["min-support"] = "Debian 14"
                if change == "duplicate": release["appimage"].append(release["appimage"][0])
                if change == "rebuild": release["appimage"][0]["revision"] = 1
                if change == "date": release["date"] = "2026-99-99"
                path.write_text("{bad" if change == "json" else json.dumps(data))
                self.query(success=False)

    def test_query_empty_stream_and_latest_missing_assets(self):
        self.fixture()
        path = self.base / "downloads/gimp_versions.json"
        path.write_text(json.dumps({"STABLE": [{"version": "3.4.0", "date": "2026-10-25"}]}))
        workspace, _ = self.query()
        self.assertEqual((workspace / "targets.tsv").read_text(), "")
        path.write_text(json.dumps({"STABLE": [
            {"version": "3.2.8", "date": "2026-10-25", "appimage": []},
            {"version": "3.2.6", "date": "2026-09-10", "appimage": []}]}))
        workspace, _ = self.query()
        self.assertEqual((workspace / "targets.tsv").read_text(), "")

    def test_packages_layout_metadata_dependencies_and_revision_reuse(self):
        self.fixture()
        self.env["MAINTAINER"] = r"Release / Ops & Team | Name <test@example.invalid>"
        self.run_update()
        self.assertEqual(len(self.artifacts()), 15)
        for artifact in self.artifacts():
            metadata = fields(artifact)
            name = metadata["package"]
            arch = metadata["architecture"]
            self.assertEqual(metadata["version"], "3.2.6-1")
            self.assertEqual(metadata["maintainer"], self.env["MAINTAINER"])
            self.assertEqual(metadata["x-publisher-stream"], "gimp-3.2")
            self.assertRegex(metadata["x-build-inputs-sha256"], r"^[a-f0-9]{64}$")
            size = int(metadata["installed-size"])
            self.assertGreater(size, 0)
            self.assertIn(f"Installed-Size: {size}\n", self.index("amd64" if arch == "all" else arch))
            if arch == "all":
                self.assertIn(f"Filename: pool/main/gimp-3.2/{artifact.name}", self.index("arm64"))
            root = self.base / f"unpacked-{name}-{arch}"
            subprocess.run(["dpkg-deb", "--raw-extract", artifact, root], check=True, capture_output=True)
            multiarch = "x86_64-linux-gnu" if arch == "amd64" else "aarch64-linux-gnu"
            lib = root / "usr/lib" / multiarch
            if name == "gimp":
                launcher = (root / "usr/bin/gimp-3.2").read_text()
                self.assertIn(f"/usr/lib/{multiarch}/gimp/bundled", launcher)
                self.assertEqual(os.readlink(root / "usr/bin/gimp"), "gimp-3.2")
                interpreter = subprocess.check_output(["patchelf", "--print-interpreter",
                                                        root / "usr/bin/gimp-3.2.bin"], text=True).strip()
                self.assertEqual(interpreter, "/lib64/ld-linux-x86-64.so.2" if arch == "amd64"
                                 else "/lib/ld-linux-aarch64.so.1")
                for dependency in ("libheif1 (>= 1.19.8)", "libheif-plugin-j2kdec (>= 1.19.8)"):
                    self.assertIn(dependency, metadata["depends"])

                extension = lib / "gimp/3.0/extensions/org.gimp.extension.goat-exercises"
                self.assertFalse((extension / "goat-exercise-gjs.js").exists())
                self.assertFalse((extension / "goat-exercise-lua.lua").exists())
                self.assertTrue((extension / "goat-exercise-py3.py").is_file())
                self.assertNotIn("goat-exercise-gjs.js", (extension / "org.gimp.extension.goat-exercises.metainfo.xml").read_text())
                self.assertNotIn("goat-exercise-lua.lua", (extension / "org.gimp.extension.goat-exercises.metainfo.xml").read_text())
                self.assertTrue((lib / "gimp/3.0/plug-ins/file-mng/file-mng").is_file())
                self.assertIn("libmng1", metadata["depends"])
                self.assertIn("libc6", metadata["depends"])
                self.assertNotIn("gjs", metadata["depends"].split(", "))
                self.assertIn("gvfs-backends", metadata["suggests"])

                self.assertIn("gimp-data-extras", metadata["suggests"])
                self.assertNotIn("LIBHEIF_PLUGIN_PATH", (lib / "gimp/3.0/environ/native-runtime.env").read_text())
            if name == "gimp-bundled-runtime":
                self.assertFalse((lib / "gimp/bundled/libssl.so.3").exists())
                self.assertTrue((lib / "gimp/bundled/babl-0.1").is_dir())
                self.assertTrue((lib / "gimp/bundled/gegl-0.4").is_dir())
                self.assertFalse((lib / "libbabl-0.1.so.0").exists())
            if name == "gimp-data":
                self.assertEqual((root / "DEBIAN/conffiles").read_text(), "/etc/gimp/3.0/gimprc\n")
                self.assertIn("Icon=gimp\n", (root / "usr/share/applications/org.gimp.GIMP.Stable.desktop").read_text())
                configuration = (root / "etc/gimp/3.0/gimprc").read_text()
                self.assertIn("(check-updates no)", configuration)
                self.assertNotIn("(check-updates yes)", configuration)
                self.assertNotIn("show-welcome-dialog", configuration)
                release = (root / "usr/share/gimp/3.0/gimp-release").read_text()
                self.assertIn("check-update = false", release)
                self.assertIn("revision = 7", release)
                self.assertGreaterEqual(size, 16)
            if name == "libgimp-3.0-0":
                self.assertEqual((root / "DEBIAN/triggers").read_text(), "activate-noawait ldconfig\n")
            if name == "libgimp-3.0-dev":
                self.assertTrue((root / "usr/include/gimp-3.0/bundled/gegl-0.4/fixture.h").is_file())
                self.assertIn("libgimp-3.0-bin (= 3.2.6-1)", metadata["depends"])
                self.assertFalse((root / "usr/include/gegl-0.4").exists())
                self.assertFalse((lib / "gimp/bundled/libgegl-npd-0.4.so").exists())
                private_pc = (lib / "pkgconfig/gimp-gegl-0.4.pc").read_text()
                self.assertIn(f"libdir=/usr/lib/{multiarch}/gimp/bundled", private_pc)
            if name == "libgimp-3.0-bin":
                self.assertEqual(os.readlink(root / "usr/bin/gimptool"), "gimptool-3.2")
                self.assertTrue((root / "usr/share/man/man1/gimptool-3.2.1.gz").is_file())
                self.assertIn("libgimp-3.0-0 (= 3.2.6-1)", metadata["depends"])
            if name == "libgimp-3.0-doc":
                self.assertEqual(arch, "all")
                self.assertFalse((root / "usr/lib").exists())
                self.assertTrue((root / "usr/share/doc/libgimp-3.0-doc/reference/libgimp-3.0/index.html").is_file())
            self.assertTrue((root / "usr/share/doc" / name / "copyright").is_file())
        self.run_update()
        self.assertEqual(len(self.artifacts()), 15)

    def test_missing_architecture_can_be_published_later(self):
        self.fixture(missing_arm64=True)
        self.run_update()
        self.assertEqual(len(self.artifacts()), 8)
        self.fixture()
        self.run_update()
        self.assertEqual(len(self.artifacts()), 15)

    def test_digest_failure_stores_nothing(self):
        self.fixture()
        with (self.base / "downloads/GIMP-3.2.6-x86_64.AppImage").open("ab") as stream:
            stream.write(b"changed")
        self.env["ARCHES"] = "amd64"
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_documentation_digest_and_archive_layout_are_checked(self):
        self.env["ARCHES"] = "amd64"
        self.fixture(missing_arm64=True)
        archive = self.base / "downloads/gimp-api-docs-3.2.6.tar.xz"
        with archive.open("ab") as stream:
            stream.write(b"changed")
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

        self.fixture(missing_arm64=True)
        with tarfile.open(archive, "w:xz") as stream:
            entry = tarfile.TarInfo("../escaped")
            stream.addfile(entry)
        (self.base / "downloads/SHA256SUMS").write_text(
            hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + archive.name + "\n")
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_layout_version_architecture_links_and_new_dependency_fail(self):
        self.env["ARCHES"] = "amd64"
        def mutate(source, lib, arch):
            if change == "layout": (source / "usr/bin/gimp-3.2").unlink()
            if change == "version": (lib / "pkgconfig/gimp-3.0.pc").write_text("Version: 3.4.0\n")
            if change == "architecture":
                path = source / "usr/bin/gimp-3.2"
                data = bytearray(path.read_bytes())
                struct.pack_into("<H", data, 18, 183)
                path.write_bytes(data)
            if change == "link":
                (lib / "gimp/3.0/environ/escape").symlink_to("/etc/passwd")
            if change == "special": os.mkfifo(lib / "gimp/3.0/pipe")
            if change == "dependency":
                subprocess.run(["patchelf", "--add-needed", "libfuture.so.99", source / "usr/bin/gimp-3.2"],
                               check=True, capture_output=True)
        for change in ("layout", "version", "architecture", "link", "special", "dependency"):
            with self.subTest(change=change):
                self.fixture(missing_arm64=True, mutation=mutate)
                self.run_update(expected=1)
                self.assertEqual(self.artifacts(), [])

    def test_dependency_ownership_includes_loaded_modules_and_explicit_requirements(self):
        self.fixture()
        self.run_update()
        by_name = {}
        for artifact in self.artifacts():
            metadata = fields(artifact)
            if metadata["architecture"] == "amd64":
                by_name[metadata["package"]] = metadata
        runtime = by_name["gimp-bundled-runtime"]["depends"]
        self.assertIn("libpng16-16t64", runtime)
        self.assertIn("libssl3t64", runtime)
        self.assertNotIn("libmng1", runtime)
        self.assertNotIn("python3-gi", runtime)
        application = by_name["gimp"]["depends"]
        self.assertIn("libmng1", application)
        self.assertIn("python3-gi", application)
        self.assertIn("libheif-plugin-j2kdec (>= 1.19.8)", application)
        self.assertIn("libpng16-16t64", by_name["libgimp-3.0-0"]["depends"])
        self.assertNotIn("gjs", application)
        for arch in ("amd64", "arm64"):
            self.assertIn("libmng1", self.index(arch))

    def test_unknown_dependency_in_loaded_module_fails(self):
        def mutate(source, lib, arch):
            subprocess.run(["patchelf", "--add-needed", "libfuture-module.so.99",
                            lib / "gegl-0.4/fixture.so"], check=True, capture_output=True)
        self.fixture(missing_arm64=True, mutation=mutate)
        self.env["ARCHES"] = "amd64"
        result = self.run_update(expected=1)
        self.assertIn("libfuture-module.so.99", result.stdout + result.stderr)
        self.assertEqual(self.artifacts(), [])

    def test_invalid_release_metadata_fails(self):
        def mutate(source, lib, arch):
            (source / "usr/share/gimp/3.0/gimp-release").write_text("[other]\nrevision=1\n")
        self.fixture(missing_arm64=True, mutation=mutate)
        self.env["ARCHES"] = "amd64"
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_invalid_extension_metadata_fails(self):
        def mutate(source, lib, arch):
            extension = lib / "gimp/3.0/extensions/org.gimp.extension.goat-exercises"
            (extension / "org.gimp.extension.goat-exercises.metainfo.xml").write_text("<component/>\n")
        self.fixture(missing_arm64=True, mutation=mutate)
        self.env["ARCHES"] = "amd64"
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])
