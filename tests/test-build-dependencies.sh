#!/bin/bash
set -Eeuo pipefail
export FRAMEWORK_DIR="$PWD"
source "$FRAMEWORK_DIR/tests/lib/common.sh"
require_project_root
if (( EUID == 0 )); then
    echo 'Run this test as the host user; dependency installation happens in image layers.' >&2
    exit 1
fi
export BUILD_IMAGE="${1:-private-apt-rebuild-amd64:local}"
run_logged "$FRAMEWORK_DIR/build/dependency-system/logs/docker-integration.log" 15m \
    python3 -m tests.build_dependency_integration
