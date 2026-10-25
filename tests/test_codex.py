"""Offline tests for the Codex query, archive layout, and package build."""

import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

from publisher_test_support import ROOT, PublisherTestCase, fields


class CodexTests(PublisherTestCase):
    def codex_fixture(
        self,
        *,
        wrapped=False,
        metadata_version="1.2.3",
        corrupt_digest=False,
        missing_arm64=False,
    ):
        shutil.copytree(
            ROOT / "packages/codex",
            self.base / "adapters/codex",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        assets = []
        for target in ("x86_64-unknown-linux-musl", "aarch64-unknown-linux-musl"):
            if missing_arm64 and target.startswith("aarch64"):
                continue
            name = f"codex-package-{target}.tar.gz"
            path = self.base / "downloads" / name
            prefix = "wrapper/" if wrapped else ""
            files = {
                "bin/codex": b"#!/bin/sh\necho fixture\n",
                "bin/codex-code-mode-host": b"#!/bin/sh\necho host\n",
                "codex-resources/bwrap": b"bundled bwrap",
                "codex-path/rg": b"bundled rg",
                "codex-package.json": json.dumps({
                    "version": metadata_version,
                    "entrypoint": "bin/codex",
                }).encode(),
            }
            with tarfile.open(path, "w:gz") as archive:
                for relative, data in files.items():
                    entry = tarfile.TarInfo(prefix + relative)
                    entry.size = len(data)
                    entry.mode = 0o644
                    archive.addfile(entry, io.BytesIO(data))
            digest = "0" * 64 if corrupt_digest else hashlib.sha256(path.read_bytes()).hexdigest()
            assets.append({
                "name": name,
                "digest": "sha256:" + digest,
                "browser_download_url": "https://fixtures.invalid/" + name,
            })
        (self.base / "downloads/release.json").write_text(json.dumps({
            "tag_name": "rust-v1.2.3", "draft": False, "prerelease": False,
            "published_at": "2000-01-01T00:00:00Z", "assets": assets,
        }))

    def run_codex_query(self, success=True):
        workspace = self.base / "codex-query"
        workspace.mkdir(exist_ok=True)
        adapter = self.base / "adapters/codex"
        environment = {
            **self.env,
            "ADAPTER_DIR": str(adapter),
            "WORKSPACE": str(workspace),
        }
        result = subprocess.run(
            [str(adapter / "query")],
            env=environment,
            text=True,
            capture_output=True,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_codex_query_rejects_malformed_json(self):
        self.codex_fixture()
        (self.base / "downloads/release.json").write_text("{not valid JSON")
        self.run_codex_query(success=False)
        self.assertFalse((self.base / "codex-query/targets.tsv").exists())

    def test_codex_query_rejects_invalid_release_tags(self):
        self.codex_fixture()
        path = self.base / "downloads/release.json"
        release = json.loads(path.read_text())
        for tag in ("v1.2.3", "rust-v1.2", "rust-v1.2.3-beta"):
            with self.subTest(tag=tag):
                release["tag_name"] = tag
                path.write_text(json.dumps(release))
                result = self.run_codex_query(success=False)
                self.assertIn("Unexpected release tag", result.stderr)

    def test_codex_query_rejects_missing_or_invalid_digests(self):
        self.codex_fixture()
        path = self.base / "downloads/release.json"
        original = path.read_text()
        invalid_digests = (
            None,
            "sha256:abc",
            "md5:" + "a" * 64,
            "sha256:" + "a" * 64 + "\n",
        )
        for digest in invalid_digests:
            with self.subTest(digest=digest):
                release = json.loads(original)
                asset = release["assets"][0]
                if digest is None:
                    del asset["digest"]
                else:
                    asset["digest"] = digest
                path.write_text(json.dumps(release))
                result = self.run_codex_query(success=False)
                self.assertIn("Missing or invalid SHA256 digest", result.stderr)

    def test_codex_query_rejects_invalid_download_urls(self):
        self.codex_fixture()
        path = self.base / "downloads/release.json"
        release = json.loads(path.read_text())
        invalid_urls = (
            "http://fixtures.invalid/archive.tar.gz",
            "https://fixtures.invalid/bad url.tar.gz",
            "https://fixtures.invalid/archive.tar.gz\n",
        )
        for url in invalid_urls:
            with self.subTest(url=url):
                release["assets"][0]["browser_download_url"] = url
                path.write_text(json.dumps(release))
                result = self.run_codex_query(success=False)
                self.assertIn("Invalid asset URL", result.stderr)

    def test_codex_query_returns_only_requested_architectures(self):
        self.codex_fixture()
        self.env["ARCHES"] = "arm64"
        self.run_codex_query()
        workspace = self.base / "codex-query"
        self.assertEqual((workspace / "targets.tsv").read_text(), "1.2.3\tarm64\n")
        self.assertEqual((workspace / "release-date").read_text(), "2000-01-01T00:00:00Z\n")
        downloads = json.loads((workspace / "assets.json").read_text())
        self.assertEqual(set(downloads), {"arm64"})
        self.assertEqual(downloads["arm64"]["version"], "1.2.3")
        self.assertRegex(downloads["arm64"]["sha256"], r"^[a-f0-9]{64}$")

    def test_codex_query_handles_no_matching_downloads(self):
        self.codex_fixture()
        path = self.base / "downloads/release.json"
        release = json.loads(path.read_text())
        release["assets"] = []
        path.write_text(json.dumps(release))
        result = self.run_codex_query()
        self.assertIn("No upstream archive for amd64", result.stderr)
        self.assertIn("No upstream archive for arm64", result.stderr)
        workspace = self.base / "codex-query"
        self.assertEqual((workspace / "targets.tsv").read_text(), "")
        self.assertEqual(json.loads((workspace / "assets.json").read_text()), {})

    def test_codex_layout_dependencies_and_embedded_metadata(self):
        self.codex_fixture()
        self.run_update()
        artifact = next(path for path in self.artifacts("codex") if path.name.endswith("amd64.deb"))
        metadata = fields(artifact)
        self.assertEqual(metadata["depends"], "bubblewrap, ripgrep")
        self.assertEqual(metadata["recommends"], "git")
        self.assertEqual(metadata["x-publisher-stream"], "codex")
        self.assertRegex(metadata["x-build-inputs-sha256"], r"^[a-f0-9]{64}$")
        contents = subprocess.check_output(["dpkg-deb", "--fsys-tarfile", str(artifact)])
        with tarfile.open(fileobj=io.BytesIO(contents)) as archive:
            for name in ("codex", "codex-code-mode-host"):
                link = archive.getmember(f"./usr/bin/{name}")
                self.assertEqual(link.linkname, f"../lib/openai-codex/bin/{name}")
                binary = archive.getmember(f"./usr/lib/openai-codex/bin/{name}")
                self.assertEqual(binary.mode, 0o755)
                self.assertEqual((binary.uid, binary.gid), (0, 0))
            for relative, executable in (("codex-resources/bwrap", "bwrap"), ("codex-path/rg", "rg")):
                wrapper = archive.extractfile(f"./usr/lib/openai-codex/{relative}")
                expected = f'#!/bin/sh\nexec /usr/bin/{executable} "$@"\n'
                self.assertEqual(wrapper.read(), expected.encode())
        self.assertIn(metadata["x-build-inputs-sha256"], self.index())

    def test_codex_missing_architecture_can_be_published_later(self):
        self.codex_fixture(missing_arm64=True)
        result = self.run_update()
        self.assertIn("No current upstream package for arm64", result.stderr)
        self.assertEqual(len(self.artifacts()), 1)
        self.codex_fixture()
        self.run_update()
        self.assertEqual(len(self.artifacts()), 2)
        self.assertEqual(self.versions("codex"), {"1.2.3-1"})

    def test_codex_unexpected_wrapper_layout_fails(self):
        self.codex_fixture(wrapped=True)
        result = self.run_update(expected=1)
        self.assertIn("Missing bin/codex", result.stderr)
        self.assertEqual(self.artifacts(), [])

    def test_codex_checksum_and_metadata_failures(self):
        self.codex_fixture(corrupt_digest=True)
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])
        self.codex_fixture(metadata_version="9.9.9")
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_codex_prereleases_are_rejected(self):
        self.codex_fixture()
        path = self.base / "downloads/release.json"
        release = json.loads(path.read_text())
        release["prerelease"] = True
        path.write_text(json.dumps(release))
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_codex_maintainer_comes_from_global_configuration(self):
        self.codex_fixture()
        self.run_update()
        maintainer = "Alice / Release & Ops | Team\\Name <alice@example.com>"
        self.env["MAINTAINER"] = maintainer
        self.run_update()
        self.assertEqual(self.versions("codex"), {"1.2.3-1", "1.2.3-2"})
        for artifact in self.artifacts("codex"):
            metadata = fields(artifact)
            if metadata["version"] == "1.2.3-2":
                self.assertEqual(metadata["maintainer"], maintainer)

    def test_codex_control_template_is_a_packaging_input(self):
        self.codex_fixture()
        self.run_update()
        template = self.base / "adapters/codex/control.in"
        template.write_text(template.read_text() + "Homepage: https://example.invalid\n")
        self.run_update()
        self.assertEqual(self.versions("codex"), {"1.2.3-1", "1.2.3-2"})
        updated = [path for path in self.artifacts("codex") if "1.2.3-2" in path.name]
        for artifact in updated:
            self.assertEqual(fields(artifact)["homepage"], "https://example.invalid")

    def archive_members(self):
        files = {
            "bin/codex": b"codex executable",
            "bin/codex-code-mode-host": b"host executable",
            "codex-package.json": b'{"version":"1.2.3","entrypoint":"bin/codex"}',
        }
        members = []
        for name, content in files.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            entry.mode = 0o644
            members.append((entry, content))
        return members

    def build_archive(self, members, success):
        archive = self.base / "downloads/archive.tar.gz"
        with tarfile.open(archive, "w:gz") as source:
            for entry, content in members:
                payload = io.BytesIO(content) if content is not None else None
                source.addfile(entry, payload)

        workspace = Path(tempfile.mkdtemp(prefix="archive-build-", dir=self.base))
        output = workspace / "output"
        output.mkdir()
        downloads = {
            "amd64": {
                "version": "1.2.3",
                "name": archive.name,
                "url": "https://fixtures.invalid/" + archive.name,
                "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            }
        }
        (workspace / "assets.json").write_text(json.dumps(downloads))
        environment = {
            **self.env,
            "ADAPTER_DIR": str(ROOT / "packages/codex"),
            "WORKSPACE": str(workspace),
            "PUBLISHER_STREAM": "codex",
            "BUILD_INPUTS_SHA256": "a" * 64,
        }
        result = subprocess.run([
            str(ROOT / "packages/codex/build"), "1.2.3-1", "amd64", str(output),
        ], env=environment, capture_output=True, text=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((output / "codex-cli_1.2.3-1_amd64.deb").exists())
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list(output.iterdir()), [])
        return workspace / "extract-amd64"

    def test_archive_rejects_external_symlinks_before_touching_targets(self):
        protected = self.base / "protected"
        protected.write_text("unchanged")
        protected.chmod(0o666)
        link = tarfile.TarInfo("external-link")
        link.type = tarfile.SYMTYPE
        link.linkname = str(protected)
        self.build_archive(self.archive_members() + [(link, None)], success=False)
        self.assertEqual(protected.read_text(), "unchanged")
        self.assertEqual(protected.stat().st_mode & 0o777, 0o666)

    def test_archive_does_not_write_through_directory_symlinks(self):
        outside = self.base / "outside"
        outside.mkdir()
        protected = outside / "protected"
        protected.write_text("unchanged")
        link = tarfile.TarInfo("escape")
        link.type = tarfile.SYMTYPE
        link.linkname = str(outside)
        members = self.archive_members() + [(link, None)]
        for name in ("escape/protected", "escape/new-file"):
            entry = tarfile.TarInfo(name)
            entry.size = len(b"overwrite")
            members.append((entry, b"overwrite"))
        self.build_archive(members, success=False)
        self.assertEqual(protected.read_text(), "unchanged")
        self.assertFalse((outside / "new-file").exists())

    def test_archive_rejects_external_hard_links(self):
        protected = self.base / "protected"
        protected.write_text("unchanged")
        for target in (str(protected), "../../protected"):
            with self.subTest(target=target):
                link = tarfile.TarInfo("external-hard-link")
                link.type = tarfile.LNKTYPE
                link.linkname = target
                destination = self.build_archive(
                    self.archive_members() + [(link, None)], success=False
                )
                self.assertFalse((destination / "external-hard-link").exists())
                self.assertEqual(protected.stat().st_nlink, 1)

    def test_archive_allows_links_within_the_extraction_directory(self):
        members = self.archive_members()
        for name, kind in (("symbolic-link", tarfile.SYMTYPE), ("hard-link", tarfile.LNKTYPE)):
            link = tarfile.TarInfo(name)
            link.type = kind
            link.linkname = "bin/codex"
            members.append((link, None))
        destination = self.build_archive(members, success=True)
        for name in ("symbolic-link", "hard-link"):
            self.assertEqual((destination / name).read_bytes(), b"codex executable")

    def test_archive_rejects_special_files_before_extraction(self):
        entry = tarfile.TarInfo("named-pipe")
        entry.type = tarfile.FIFOTYPE
        destination = self.build_archive(
            self.archive_members() + [(entry, None)], success=False
        )
        self.assertFalse(destination.exists())

    def test_archive_removes_privileged_permissions(self):
        members = self.archive_members()
        members[0][0].mode = 0o6777
        destination = self.build_archive(members, success=True)
        mode = (destination / "bin/codex").stat().st_mode
        self.assertEqual(mode & 0o7000, 0)
        self.assertEqual(mode & 0o022, 0)
        self.assertEqual(mode & 0o700, 0o700)

    def test_archive_path_traversal_is_rejected(self):
        entry = tarfile.TarInfo("../escaped")
        entry.size = 1
        destination = self.build_archive([(entry, b"x")], success=False)
        self.assertFalse((destination.parent / "escaped").exists())

if __name__ == "__main__":
    unittest.main()
