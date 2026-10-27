"""Discover framework or adapter tests, including non-importable stream names."""

import argparse
from pathlib import Path
import sys
import unittest


def select_directories(root, packages, *, offline=False, framework=False):
    available = sorted(path.name for path in (root / "packages").iterdir()
                       if path.is_dir() and not path.name.startswith("."))
    unknown = sorted(set(packages) - set(available))
    if unknown:
        raise ValueError(f"Unknown package test selector: {', '.join(unknown)}")
    if packages and (offline or framework):
        raise ValueError("Package selectors cannot be combined with --offline or --framework")
    if not packages and not (offline or framework):
        raise ValueError("Select packages, --offline, or --framework")

    directories = [root / "tests"] if offline or framework else []
    selected = available if offline else list(dict.fromkeys(packages))
    for name in selected:
        directory = root / "tests" / name
        if not directory.is_dir() or not list(directory.glob("test_*.py")):
            raise ValueError(f"Missing regression tests for package: {name}")
        directories.append(directory)
    return directories


def discover_tests(directories):
    suite = unittest.TestSuite()
    for directory in directories:
        # Each stream is a discovery root. A name such as gimp-3.2 is not a
        # Python package, and unittest's ordinary recursive search skips it.
        loader = unittest.TestLoader()
        suite.addTests(loader.discover(str(directory), top_level_dir=str(directory)))
    return suite


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="all offline tests")
    mode.add_argument("--framework", action="store_true", help="framework/setup tests only")
    parser.add_argument("packages", nargs="*", help="adapter directory names")
    arguments = parser.parse_args()
    root = Path.cwd()
    if not (root / "update.sh").is_file() or not (root / "packages").is_dir():
        parser.error("Run tests from the project root.")
    try:
        directories = select_directories(root, arguments.packages,
                                         offline=arguments.offline, framework=arguments.framework)
    except ValueError as error:
        parser.error(str(error))
    result = unittest.TextTestRunner(verbosity=2).run(discover_tests(directories))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
