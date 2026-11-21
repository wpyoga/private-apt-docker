"""Check the Herdr desktop release stream."""

from tests.lib import herdr_test_support


class HerdrAppTests(herdr_test_support.HerdrArchiveTests):
    component = 'app'

    def test_invalid_core_minimum(self):
        self.fixture()
        self.change_manifest(lambda m: m.update(core_min='nightly'))
        self.assertIn('Invalid core_min', self.run_update(expected=1).stderr)
