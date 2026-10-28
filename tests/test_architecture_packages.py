"""Architecture-specific output sets retain the publisher's revision rules."""

import subprocess

from tests.lib.publisher_test_support import PublisherTestCase, fields


class ArchitecturePackageTests(PublisherTestCase):
    def adapter_with_variants(self, common=False):
        directory = self.adapter(stream="variants")
        suffix = " common-data" if common else ""
        (directory / "config").write_text(
            'RELEASE_STREAM=variants\n'
            f'BINARY_PACKAGES_AMD64="example-gtk{suffix}"\n'
            f'BINARY_PACKAGES_ARM64="example-x11{suffix}"\n'
        )
        return directory

    def test_variant_outputs_publish_and_resume_at_shared_revision(self):
        self.adapter_with_variants()
        self.run_update()
        self.assertEqual({(fields(p)['package'], fields(p)['architecture']) for p in self.artifacts()},
                         {('example-gtk', 'amd64'), ('example-x11', 'arm64')})
        retained = next(p for p in self.artifacts() if fields(p)['architecture'] == 'amd64')
        original = retained.read_bytes()
        next(p for p in self.artifacts() if fields(p)['architecture'] == 'arm64').unlink()
        self.run_update()
        self.assertEqual(self.versions('variants'), {'1.2.3-1'})
        self.assertEqual(retained.read_bytes(), original)
        self.run_update()
        self.assertEqual((self.base / 'events').read_text().count('/build'), 3)

    def test_revision_history_includes_unselected_architecture_names(self):
        self.adapter_with_variants()
        self.legacy('example-x11', '1.2.3-7', 'arm64')
        self.env['ARCHES'] = 'amd64'
        self.run_update()
        self.assertEqual(self.versions('variants'), {'1.2.3-8'})
        self.env['ARCHES'] = 'arm64'
        self.run_update()
        self.assertEqual(self.versions('variants'), {'1.2.3-8'})

    def test_shared_all_package_can_appear_in_both_lists(self):
        directory = self.adapter_with_variants(common=True)
        path = directory / 'build'
        script = path.read_text().replace(
            'for PACKAGE_NAME in $BINARY_PACKAGES; do',
            'for PACKAGE_NAME in $BINARY_PACKAGES; do\n'
            '    PACKAGE_ARCHITECTURE="$ARCHITECTURE"\n'
            '    if [[ "$PACKAGE_NAME" == common-data ]]; then PACKAGE_ARCHITECTURE=all; fi')
        script = script.replace('Architecture: $ARCHITECTURE', 'Architecture: $PACKAGE_ARCHITECTURE')
        script = script.replace('${VERSION}_${ARCHITECTURE}.deb', '${VERSION}_${PACKAGE_ARCHITECTURE}.deb')
        path.write_text(script)
        self.run_update()
        self.assertEqual(len(self.artifacts()), 3)
        self.run_update()
        self.assertEqual((self.base / 'events').read_text().count('/build'), 2)

    def test_wrong_variant_output_is_rejected(self):
        directory = self.adapter_with_variants()
        path = directory / 'build'
        path.write_text(path.read_text().replace('for PACKAGE_NAME in $BINARY_PACKAGES;',
                                                'for PACKAGE_NAME in example-x11;'))
        self.env['ARCHES'] = 'amd64'
        self.run_update(expected=1)
        self.assertEqual(self.artifacts(), [])

    def test_invalid_and_mixed_configurations_are_rejected(self):
        directory = self.adapter_with_variants()
        for declarations in (
            'BINARY_PACKAGES_AMD64=example-gtk\n',
            'BINARY_PACKAGES_ARM64=example-x11\n',
            'BINARY_PACKAGES_AMD64=" "\nBINARY_PACKAGES_ARM64=example-x11\n',
            'BINARY_PACKAGES_AMD64=example-gtk example-gtk\nBINARY_PACKAGES_ARM64=example-x11\n',
            'BINARY_PACKAGES=example\nBINARY_PACKAGES_AMD64=example-gtk\nBINARY_PACKAGES_ARM64=example-x11\n',
        ):
            with self.subTest(declarations=declarations):
                (directory / 'config').write_text('RELEASE_STREAM=variants\n' + declarations)
                result = subprocess.run(['bash', str(self.publisher / 'lib/config.sh')],
                                        env={**self.env, 'ADAPTER_DIR': str(directory)},
                                        capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
