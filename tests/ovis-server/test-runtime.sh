#!/bin/bash
set -Eeuo pipefail

export FRAMEWORK_DIR="$PWD"
source "$FRAMEWORK_DIR/tests/lib/common.sh"
require_project_root
: "${1:?Supply the amd64 Ovis server Debian package}"
: "${2:?Supply the amd64 Herdr core Debian package}"
CONTEXT=$(mktemp -d "$FRAMEWORK_DIR/build/ov-XXXXXX")
run_logged "$CONTEXT/runtime.log" 2m \
    python3 "$FRAMEWORK_DIR/tests/ovis-server/check_runtime.py" "$1" "$2" "$CONTEXT"
printf 'Runtime check files: %s\n' "$CONTEXT"
