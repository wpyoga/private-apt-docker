#!/bin/bash
# One host-side command for all private-build-dependency verification.
set -Eeuo pipefail

export FRAMEWORK_DIR="$PWD"
source "$FRAMEWORK_DIR/tests/lib/common.sh"
require_project_root
mkdir -p "$FRAMEWORK_DIR/build"
LOG_DIR=$(mktemp -d "$FRAMEWORK_DIR/build/dependency-checks-XXXXXX")
IMAGE="${1:-private-apt-rebuild-amd64:local}"
STATUS=0

run_logged "$LOG_DIR/offline.log" 30m \
    bash tests/run.sh --offline || STATUS=1
run_logged "$LOG_DIR/docker.log" 20m \
    bash tests/test-build-dependencies.sh "$IMAGE" || STATUS=1
run_logged "$LOG_DIR/shell-syntax.log" 1m bash -c \
    'for SCRIPT in "$@"; do bash -n "$SCRIPT" || exit; done' shell-syntax \
    update.sh lib/update-package.sh lib/isolated-build.sh lib/build-worker.sh \
    rebuild.sh tests/test-build-dependencies.sh tests/verify-build-dependencies.sh \
    tests/fixtures/build-dependencies/provider-build \
    tests/fixtures/build-dependencies/consumer-build || STATUS=1
run_logged "$LOG_DIR/python-syntax.log" 1m python3 -m py_compile \
    lib/build-dependencies.py lib/build-context.py lib/checksum.py \
    tests/run.py tests/test_runner.py tests/test_build_dependencies.py \
    tests/build_dependency_integration.py || STATUS=1
run_logged "$LOG_DIR/diff.log" 1m git diff --check || STATUS=1

printf 'Verification finished (exit %s); logs: %s\n' "$STATUS" "$LOG_DIR"
exit "$STATUS"
