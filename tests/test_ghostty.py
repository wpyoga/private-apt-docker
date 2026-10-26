"""Offline Ghostty import tests using real Debian fixture packages."""
import hashlib
import io
import json
import shutil
import subprocess
import tarfile

from publisher_test_support import ROOT, PublisherTestCase, fields


class GhosttyTests(PublisherTestCase):
    def fixture(
        self,
        *,
        missing_arm64=False,
        corrupt=False,
        package="ghostty",
        version=None,
        package_architecture=None,
        missing_path=None,
        community_revision="ppa2",
        installed_size=None,
        payload_size=0,
    ):
        shutil.copytree(
            ROOT / "packages/ghostty",
            self.base / "adapters/ghostty",
            dirs_exist_ok=True,
        )
        if version is None:
            version = f"1.3.1-0~{community_revision}"

        assets = []
        for arch in ("amd64", "arm64"):
            if missing_arm64 and arch == "arm64":
                continue

            root = self.base / f"upstream-{arch}"
            (root / "DEBIAN").mkdir(parents=True, exist_ok=True)
            control_architecture = package_architecture or arch
            (root / "DEBIAN/control").write_text(
                f"Package: {package}\nVersion: {version}\n"
                f"Architecture: {control_architecture}\n"
                "Maintainer: Upstream <upstream@example.com>\n"
                "Depends: libgtk-4-1,\n libadwaita-1-0\n"
                "Description: Ghostty fixture\n Continued description\n"
                " .\n Another paragraph\n"
                "X-Publisher-Stream: old-stream\n"
                "X-Build-Inputs-SHA256: old-checksum\n"
            )
            postinst = root / "DEBIAN/postinst"
            if installed_size is not None:
                with (root / "DEBIAN/control").open("a") as control:
                    control.write(f"Installed-Size: {installed_size}\n")
            postinst.write_text("#!/bin/sh\nexit 42\n")
            postinst.chmod(0o755)

            required_paths = (
                "usr/bin/ghostty",
                "usr/share/applications/com.mitchellh.ghostty.desktop",
                "usr/share/terminfo/x/xterm-ghostty",
            )
            for relative_path in required_paths:
                destination = root / relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text("fixture\n")
                if relative_path == "usr/bin/ghostty":
                    with destination.open("ab") as binary:
                        binary.write(b"x" * payload_size)
                    destination.chmod(0o755)
            if missing_path:
                (root / missing_path).unlink()

            name = f"ghostty_1.3.1-0.{community_revision}_{arch}_trixie.deb"
            deb = self.base / "downloads" / name
            subprocess.run(
                ["dpkg-deb", "--build", str(root), str(deb)],
                check=True,
                capture_output=True,
            )
            digest = hashlib.sha256(deb.read_bytes()).hexdigest()
            if corrupt:
                digest = "0" * 64
            assets.append({
                "name": name,
                "digest": "sha256:" + digest,
                "browser_download_url": f"https://fixtures.invalid/{name}",
            })

        release = {
            "tag_name": f"1.3.1-0-{community_revision}",
            "draft": False,
            "prerelease": False,
            "published_at": "2026-04-01T03:36:27Z",
            "assets": assets,
        }
        (self.base / "downloads/release.json").write_text(json.dumps(release))

    def test_import_preserves_integration_and_rewrites_metadata(self):
        self.fixture()
        self.run_update()
        self.assertEqual(len(self.artifacts('ghostty')), 2)
        for artifact in self.artifacts('ghostty'):
            metadata = fields(artifact)
            self.assertEqual(metadata['version'], '1.3.1+0.ppa2-1')
            self.assertEqual(metadata['maintainer'], self.env['MAINTAINER'])
            self.assertEqual(metadata['depends'], 'libgtk-4-1,')
            self.assertEqual(metadata['x-publisher-stream'], 'ghostty')
            self.assertGreater(int(metadata['installed-size']), 0)
            self.assertIn(
                f"Installed-Size: {metadata['installed-size']}\n",
                self.index(metadata['architecture']),
            )
            self.assertRegex(metadata['x-build-inputs-sha256'], r'^[a-f0-9]{64}$')
            payload = subprocess.check_output(['dpkg-deb', '--fsys-tarfile', str(artifact)])
            with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
                self.assertEqual(archive.getmember('./usr/bin/ghostty').mode, 0o755)
                self.assertIsNotNone(archive.getmember('./usr/share/terminfo/x/xterm-ghostty'))
            control = self.base / ('control-' + metadata['architecture'])
            subprocess.run(['dpkg-deb', '--control', str(artifact), str(control)], check=True)
            self.assertEqual((control / 'postinst').read_text(), '#!/bin/sh\nexit 42\n')
        self.run_update()
        self.assertEqual(len(self.artifacts()), 2)

    def test_installed_size_replaces_stale_upstream_value(self):
        payload_size = 2 * 1024 * 1024
        self.fixture(installed_size=1, payload_size=payload_size)
        self.run_update()

        for artifact in self.artifacts('ghostty'):
            installed_size = int(fields(artifact)['installed-size'])
            self.assertGreaterEqual(installed_size, payload_size // 1024)
            self.assertLess(installed_size, payload_size // 1024 + 128)
            self.assertLess(artifact.stat().st_size, installed_size * 1024)

    def test_missing_architecture_is_published_later(self):
        self.fixture(missing_arm64=True)
        result = self.run_update()
        self.assertIn('No current upstream package for arm64', result.stderr)
        self.assertEqual(len(self.artifacts()), 1)
        self.fixture()
        self.run_update()
        self.assertEqual(len(self.artifacts()), 2)

    def test_bad_digest_and_unexpected_metadata_store_nothing(self):
        for options in ({'corrupt': True}, {'package': 'wrong'},
                        {'version': '9.9.9'}, {'package_architecture': 'i386'}):
            with self.subTest(options=options):
                self.fixture(**options)
                self.run_update(expected=1)
                self.assertEqual(self.artifacts(), [])

    def test_query_rejects_unstable_releases_and_invalid_digests(self):
        self.fixture()
        path = self.base / 'downloads/release.json'
        original = path.read_text()
        for change in ('tag', 'prerelease', 'digest', 'url'):
            with self.subTest(change=change):
                release = json.loads(original)
                if change == 'tag':
                    release['tag_name'] = 'tip'
                elif change == 'prerelease':
                    release['prerelease'] = True
                elif change == 'digest':
                    release['assets'][0]['digest'] = 'sha256:bad'
                else:
                    release['assets'][0]['browser_download_url'] = 'http://invalid/file.deb'
                path.write_text(json.dumps(release))
                self.run_update(expected=1)
                self.assertEqual(self.artifacts(), [])

    def test_query_selects_only_requested_architecture(self):
        self.fixture()
        self.env["ARCHES"] = "arm64"
        workspace = self.base / "query-workspace"
        workspace.mkdir()
        adapter = self.base / "adapters/ghostty"
        environment = {
            **self.env,
            "ADAPTER_DIR": str(adapter),
            "WORKSPACE": str(workspace),
        }
        subprocess.run([str(adapter / "query")], env=environment, check=True)

        self.assertEqual(
            (workspace / "targets.tsv").read_text(), "1.3.1+0.ppa2\tarm64\n"
        )
        assets = json.loads((workspace / "assets.json").read_text())
        self.assertEqual(set(assets), {"arm64"})
        self.assertEqual(assets["arm64"]["deb_version"], "1.3.1-0~ppa2")
        self.assertEqual(
            (workspace / "release-date").read_text(), "2026-04-01T03:36:27Z\n"
        )

    def test_each_required_path_is_validated(self):
        for relative_path in (
            "usr/bin/ghostty",
            "usr/share/applications/com.mitchellh.ghostty.desktop",
            "usr/share/terminfo/x/xterm-ghostty",
        ):
            with self.subTest(path=relative_path):
                self.fixture(missing_path=relative_path)
                result = self.run_update(expected=1)
                self.assertIn(f"Missing {relative_path}", result.stderr)
                self.assertEqual(self.artifacts(), [])

    def test_control_metadata_preserves_multiline_fields_and_special_characters(self):
        self.fixture()
        self.env["ARCHES"] = "amd64"
        maintainer = "Alice / Release & Ops | Team\\Name <alice@example.com>"
        self.env["MAINTAINER"] = maintainer
        self.run_update()
        artifact = self.artifacts()[0]
        control = subprocess.check_output(
            ["dpkg-deb", "--field", str(artifact)], text=True
        )
        self.assertIn("Depends: libgtk-4-1,\n libadwaita-1-0\n", control)
        self.assertIn(
            "Description: Ghostty fixture\n Continued description\n .\n Another paragraph\n",
            control,
        )
        self.assertEqual(fields(artifact)["maintainer"], maintainer)
        for field in ("Version", "Maintainer", "X-Build-Inputs-SHA256", "X-Publisher-Stream"):
            self.assertEqual(control.count(f"\n{field}:"), 1)
        self.assertNotIn("old-stream", control)
        self.assertNotIn("old-checksum", control)

    def test_control_rewrite_removes_owned_field_continuations(self):
        control = self.base / "control"
        control.write_text(
            "Package: ghostty\n"
            "mAiNtAiNeR: Old name\n <old@example.com>\n"
            "Description: Preserved\n Continued description\n"
            "Version: 0.0.0"
        )
        environment = {
            **self.env,
            "BUILD_INPUTS_SHA256": "a" * 64,
            "PUBLISHER_STREAM": "ghostty",
        }
        subprocess.run(
            ["python3", str(ROOT / "packages/ghostty/rewrite-control.py"),
             str(control), "1.3.1+0.ppa2-1", "2048"],
            env=environment,
            check=True,
        )
        rewritten = control.read_text()
        self.assertNotIn("old@example.com", rewritten)
        self.assertNotIn("0.0.0", rewritten)
        self.assertIn("Description: Preserved\n Continued description\n", rewritten)
        self.assertIn(f"Maintainer: {self.env['MAINTAINER']}\n", rewritten)
        self.assertIn("Version: 1.3.1+0.ppa2-1\n", rewritten)
        self.assertIn("Installed-Size: 2048\n", rewritten)

    def test_community_rebuild_and_recipe_change_preserve_old_artifacts(self):
        self.fixture()
        self.env["ARCHES"] = "amd64"
        self.run_update()
        original = self.artifacts()[0]
        original_bytes = original.read_bytes()

        self.fixture(community_revision="ppa3")
        self.run_update()
        self.assertEqual(self.versions("ghostty"), {"1.3.1+0.ppa2-1", "1.3.1+0.ppa3-1"})
        adapter_build = self.base / "adapters/ghostty/build"
        adapter_build.write_text(adapter_build.read_text() + "\n# Recipe change\n")
        self.run_update()
        self.assertEqual(
            self.versions("ghostty"),
            {"1.3.1+0.ppa2-1", "1.3.1+0.ppa3-1", "1.3.1+0.ppa3-2"},
        )
        self.assertEqual(original.read_bytes(), original_bytes)
