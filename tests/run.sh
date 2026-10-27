#!/bin/bash
# Run all checks from the project root; no environment setup is needed.
set -Eeuo pipefail

export FRAMEWORK_DIR="$PWD"
if [[ ! -f "$FRAMEWORK_DIR/tests/lib/common.sh" ]]; then
    echo 'Run tests from the project root.' >&2
    exit 1
fi
source "$FRAMEWORK_DIR/tests/lib/common.sh"
require_project_root
mkdir -p "$FRAMEWORK_DIR/build"
LOG_DIR=$(mktemp -d "$FRAMEWORK_DIR/build/test-run-XXXXXX")

if (( $# == 0 )); then
    run_logged "$LOG_DIR/regression.log" 30m python3 -m tests.run --offline
    run_logged "$LOG_DIR/signing.log" 10m bash "$FRAMEWORK_DIR/tests/test-signed-repo.sh"
else
    run_logged "$LOG_DIR/regression.log" 30m python3 -m tests.run "$@"
fi

echo 'All tests passed.'
