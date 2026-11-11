#!/bin/bash
# Host launcher: existing Compose coordinator plus a disposable-build worker.
set -Eeuo pipefail

export FRAMEWORK_DIR="${FRAMEWORK_DIR:-$PWD}"
if [[ ! -f "$FRAMEWORK_DIR/compose.yaml" || ! -f "$FRAMEWORK_DIR/update.sh" ]]; then
    echo 'Run rebuild.sh from the project root.' >&2
    exit 1
fi
if (( EUID == 0 )); then
    echo 'Run rebuild.sh as the host user; root package installation belongs in image layers.' >&2
    exit 1
fi
BUILD_ARCH="${1:?Supply amd64 or arm64}"
case "$BUILD_ARCH" in amd64|arm64) ;; *) echo "Unsupported build architecture: $BUILD_ARCH" >&2; exit 1 ;; esac
MODE="${2:---once}"
case "$MODE" in --once|--loop) ;; *) echo 'Use --once or --loop' >&2; exit 1 ;; esac

SERVICE="rebuild-$BUILD_ARCH"
CONFIGURATION=$(docker compose config --format json)
PUBLISHER_USER=$(jq -er --arg SERVICE "$SERVICE" '.services[$SERVICE].user' <<< "$CONFIGURATION")
if [[ "$PUBLISHER_USER" != "$(id -u):$(id -g)" ]]; then
    echo "Run the launcher as the configured publisher user $PUBLISHER_USER so workspaces and keys have the same owner." >&2
    exit 1
fi
STATE_DIR="$FRAMEWORK_DIR/build/workers/$BUILD_ARCH"
mkdir -p "$STATE_DIR/queue" "$STATE_DIR/tmp"
STATE_DIR=$(realpath "$STATE_DIR")
export BUILD_QUEUE_DIR="$STATE_DIR/queue"
export BUILD_ARCH
exec 7>"$STATE_DIR/launcher.lock"
flock -n 7 || { echo "A rebuild launcher already owns $STATE_DIR" >&2; exit 1; }

# Use the exact image selected by Compose, rather than a separately configured
# builder image. No private packages are required to construct this base image.
docker compose build "$SERVICE" > "$STATE_DIR/image-build.log" 2>&1
IMAGE_NAME=$(jq -er --arg SERVICE "$SERVICE" '.services[$SERVICE].image' <<< "$CONFIGURATION")
BUILD_IMAGE=$(docker image inspect --format '{{.Id}}' "$IMAGE_NAME")
if [[ -z "$BUILD_IMAGE" ]]; then
    echo "No image found for $SERVICE; see $STATE_DIR/image-build.log" >&2
    exit 1
fi
export BUILD_IMAGE
WORKER_PID=
COORDINATOR_PID=
COORDINATOR_NAME="private-apt-worker-coordinator-$BUILD_ARCH-$$"
cleanup() {
    docker rm -f "$COORDINATOR_NAME" >/dev/null 2>&1 || true
    if [[ -n "$WORKER_PID" ]]; then
        kill "$WORKER_PID" 2>/dev/null || true
        wait "$WORKER_PID" 2>/dev/null || true
    fi
    if [[ -n "$COORDINATOR_PID" ]]; then
        wait "$COORDINATOR_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT
trap 'exit 143' INT TERM
bash "$FRAMEWORK_DIR/lib/build-worker.sh" > "$STATE_DIR/worker.log" 2>&1 &
WORKER_PID=$!
DEADLINE=$((SECONDS + 30))
until [[ -f "$BUILD_QUEUE_DIR/worker.ready" ]]; do
    if ! kill -0 "$WORKER_PID" 2>/dev/null || (( SECONDS >= DEADLINE )); then
        echo "Build worker failed to start; inspect $STATE_DIR/worker.log" >&2
        exit 1
    fi
    sleep 1
done

COMMAND=(/opt/apt-publisher/entrypoint.sh)
if [[ "$MODE" == --once ]]; then
    COMMAND=(/bin/bash -Eeuo pipefail -c \
        'source "$FRAMEWORK_DIR/lib/gnupg.sh"; prepare_gnupg_socket_directory; gpgconf --launch gpg-agent; exec bash "$FRAMEWORK_DIR/update.sh"')
fi
echo "Running $SERVICE; log: $STATE_DIR/coordinator.log"
docker compose run --rm --no-deps --name "$COORDINATOR_NAME" \
    --volume "$STATE_DIR:$STATE_DIR" \
    --env "TMPDIR=$STATE_DIR/tmp" --env "BUILD_QUEUE_DIR=$BUILD_QUEUE_DIR" \
    --entrypoint "${COMMAND[0]}" "$SERVICE" "${COMMAND[@]:1}" \
    > "$STATE_DIR/coordinator.log" 2>&1 &
COORDINATOR_PID=$!
STATUS=0
wait -n -p FINISHED "$WORKER_PID" "$COORDINATOR_PID" || STATUS=$?
if [[ "$FINISHED" == "$WORKER_PID" ]]; then
    echo "Build worker stopped unexpectedly; inspect $STATE_DIR/worker.log" >&2
    exit 1
fi
exit "$STATUS"
