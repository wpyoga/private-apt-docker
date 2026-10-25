#!/bin/bash
# Run all checks from the project root; no environment setup is needed.
set -Eeuo pipefail

export FRAMEWORK_DIR="$PWD"
if [[ ! -f "$FRAMEWORK_DIR/update.sh" || ! -d "$FRAMEWORK_DIR/packages" ]]; then
    echo 'Run tests from the project root.' >&2
    exit 1
fi

echo 'Running offline regression tests'
python3 -m unittest discover -s "$FRAMEWORK_DIR/tests" -v

echo 'Running the signed repository integration test'
bash "$FRAMEWORK_DIR/tests/test-signed-repo.sh"

echo 'All tests passed.'
