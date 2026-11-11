#!/bin/bash
# Run on the Docker host. Requests come from one architecture coordinator.
set -Eeuo pipefail

: "${BUILD_QUEUE_DIR:?BUILD_QUEUE_DIR must be set and non-empty}"
: "${BUILD_IMAGE:?BUILD_IMAGE must be set and non-empty}"
: "${BUILD_ARCH:?BUILD_ARCH must be set and non-empty}"

mkdir -p "$BUILD_QUEUE_DIR"
exec 8>"$BUILD_QUEUE_DIR/worker.lock"
flock -n 8 || { echo "A build worker already owns $BUILD_QUEUE_DIR" >&2; exit 1; }
shopt -s nullglob
JOB_PID=
BASE_TAG="private-apt-worker-base-$BUILD_ARCH:$$"
stop_job() {
    if [[ -n "$JOB_PID" ]]; then
        kill -- "-$JOB_PID" 2>/dev/null || true
        wait "$JOB_PID" 2>/dev/null || true
    fi
    rm -f -- "$BUILD_QUEUE_DIR/worker.ready"
    docker image rm "$BASE_TAG" >/dev/null 2>&1 || true
}
trap stop_job EXIT
trap 'exit 143' TERM INT
BASE_ID=$(docker image inspect --format '{{.Id}}' "$BUILD_IMAGE")
# BuildKit interprets a bare sha256 image ID as a registry name. A worker-owned
# tag pins the inspected local image without depending on a mutable service tag.
docker image tag "$BASE_ID" "$BASE_TAG"
BUILD_IMAGE=$BASE_TAG
touch "$BUILD_QUEUE_DIR/worker.ready"

run_job() (
    local JOB=$1 ARCHITECTURE WORKSPACE OUTPUT_DIR VERSION USER_ID IMAGE_ID CONTAINER_NAME
    ARCHITECTURE=$(cat "$JOB/architecture")
    [[ "$ARCHITECTURE" == "$BUILD_ARCH" ]] || return 1
    WORKSPACE=$(cat "$JOB/workspace")
    OUTPUT_DIR=$(cat "$JOB/output")
    VERSION=$(cat "$JOB/version")
    USER_ID=$(cat "$JOB/user")
    [[ "$USER_ID" =~ ^[0-9]+:[0-9]+$ ]] || return 1
    # Coordinator and host use identical absolute workspace paths.
    [[ "$WORKSPACE" == "${BUILD_QUEUE_DIR%/queue}"/tmp/* ]] || return 1
    [[ "$OUTPUT_DIR" == "$WORKSPACE"/* && -d "$OUTPUT_DIR" ]] || return 1
    IMAGE_ID=
    CONTAINER_NAME="apt-build-${JOB##*/}-$$"
    cleanup_job() {
        docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
        if [[ -n "$IMAGE_ID" ]]; then
            docker image rm "$IMAGE_ID" >/dev/null 2>&1 || true
        fi
    }
    trap cleanup_job EXIT
    trap 'exit 143' TERM INT
    docker build --build-arg "BUILD_IMAGE=$BUILD_IMAGE" \
        --build-arg "TARGET_ARCH=$ARCHITECTURE" --iidfile "$JOB/image" "$JOB" || return
    IMAGE_ID=$(cat "$JOB/image")
    docker run --rm --name "$CONTAINER_NAME" --init --user "$USER_ID" \
        --security-opt no-new-privileges:true --cap-drop ALL \
        --memory 2g --pids-limit 512 \
        --mount "type=bind,src=$WORKSPACE,dst=$WORKSPACE" \
        --env-file "$JOB/environment" "$IMAGE_ID" -Eeuo pipefail -c \
        'cp /build-installed-packages "$WORKSPACE/worker-installed-packages"; exec "$ADAPTER_DIR/build" "$@"' \
        worker "$VERSION" "$ARCHITECTURE" "$OUTPUT_DIR"
    local STATUS=$?
    if [[ -f "$WORKSPACE/worker-installed-packages" ]]; then
        cp -- "$WORKSPACE/worker-installed-packages" "$JOB/installed-packages"
    fi
    return "$STATUS"
)
export -f run_job
export BUILD_QUEUE_DIR BUILD_IMAGE BUILD_ARCH

while :; do
    for JOB in "$BUILD_QUEUE_DIR"/job-*; do
        if [[ ! -f "$JOB/ready" || -f "$JOB/result" || -f "$JOB/cancelled" ]]; then
            continue
        fi
        if [[ -f "$JOB/running" ]]; then
            echo 'Previous worker stopped before completing this job; submit a new build request.' >> "$JOB/build.log"
            printf '1\n' > "$JOB/result"
            continue
        fi
        touch "$JOB/running"
        # No live output polling: inspect the completed log on failure.
        setsid timeout --kill-after=30s 115m bash -c 'run_job "$1"' worker "$JOB" \
            > "$JOB/build.log" 2>&1 &
        JOB_PID=$!
        if wait "$JOB_PID"; then
            STATUS=0
        else
            STATUS=$?
        fi
        JOB_PID=
        printf '%s\n' "$STATUS" > "$JOB/result.part"
        mv -- "$JOB/result.part" "$JOB/result"
    done
    sleep 1
done
