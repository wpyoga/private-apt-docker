#!/bin/bash
# Live downloads and packaging, isolated from operator configuration and storage.
set -Eeuo pipefail

export FRAMEWORK_DIR="$PWD"
source "$FRAMEWORK_DIR/tests/lib/common.sh"
require_project_root
if (( EUID == 0 )); then
    echo 'Run this coordinator as your host user.' >&2
    exit 1
fi

mkdir -p "$FRAMEWORK_DIR/build"
CONTEXT=${GIMP_PUBLISHER_CONTEXT:-$(mktemp -d "$FRAMEWORK_DIR/build/gimp-publisher-XXXXXX")}
mkdir -p "$CONTEXT"
CONTEXT=$(realpath "$CONTEXT")
if [[ $(stat -c '%u' "$CONTEXT") != "$EUID" || "$CONTEXT" != "$FRAMEWORK_DIR/build/"* ]]; then
    echo 'Test context must be host-owned and under build/.' >&2
    exit 1
fi
IMAGE=private-apt-gimp-publisher-test:local
NAME="gimp-publisher-${CONTEXT##*/}"
echo "Preserved publisher test context: $CONTEXT"
cp "$FRAMEWORK_DIR/tests/gimp-3.2/publisher-cycle.sh" "$CONTEXT/publisher-cycle.sh"
run_logged "$CONTEXT/image-build.log" 20m \
    docker build --progress=plain -t "$IMAGE" "$FRAMEWORK_DIR"

# Keep the container until its exit and cgroup statistics have been inspected.
STATUS=0
run_logged "$CONTEXT/publisher.log" 90m \
    docker run --name "$NAME" --init \
    --user "$(id -u):$(id -g)" \
    --memory 256m --pids-limit 128 \
    --security-opt no-new-privileges:true --cap-drop ALL \
    --mount "type=bind,src=$CONTEXT,dst=/test" \
    --mount "type=bind,src=$CONTEXT/publisher-cycle.sh,dst=/publisher-cycle.sh,readonly" \
    --env "ARCHES=${ARCHES:-amd64 arm64}" \
    --entrypoint /bin/bash "$IMAGE" /publisher-cycle.sh || STATUS=$?
if [[ $(docker inspect --format '{{.State.Running}}' "$NAME") == true ]]; then
    docker stop --time 30 "$NAME" > "$CONTEXT/container-stop.log"
fi
docker inspect "$NAME" > "$CONTEXT/container.json"
docker rm "$NAME" > "$CONTEXT/container-remove.log"
if (( STATUS == 0 )); then
    run_logged "$CONTEXT/verification.log" 5m \
        python3 "$FRAMEWORK_DIR/tests/gimp-3.2/check-publisher.py" "$CONTEXT"
fi
exit "$STATUS"
