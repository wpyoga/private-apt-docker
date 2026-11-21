"""Check the Herdr core release stream."""

from tests.lib import herdr_test_support


class HerdrCoreTests(herdr_test_support.HerdrArchiveTests):
    component = 'core'
