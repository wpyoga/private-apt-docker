#!/bin/bash
# Check agent isolation and lifetime with throwaway keys and real containers.
set -Eeuo pipefail

export FRAMEWORK_DIR="$PWD"
if [[ ! -f "$FRAMEWORK_DIR/tests/lib/common.sh" ]]; then
    echo 'Run tests from the project root.' >&2
    exit 1
fi
source "$FRAMEWORK_DIR/tests/lib/common.sh"
require_project_root

if [[ "${1:-}" != --worker ]]; then
    mkdir -p "$FRAMEWORK_DIR/build"
    WORK_DIR=$(mktemp -d "$FRAMEWORK_DIR/build/container-gpg-XXXXXX")
    run_logged "$WORK_DIR/build.log" 15m \
        docker build --tag private-apt-publisher:local "$FRAMEWORK_DIR"
    run_logged "$WORK_DIR/isolation.log" 5m \
        bash "$FRAMEWORK_DIR/tests/test-container-gpg.sh" --worker "$WORK_DIR"
    echo "Container GPG test passed; logs: $WORK_DIR"
    exit 0
fi

WORK_DIR="$2"
TEST_UID=$(id -u)
TEST_GID=$(id -g)
KEYRING_DIR="$WORK_DIR/keyring"
CONTAINERS=()

cleanup() {
    if (( ${#CONTAINERS[@]} > 0 )); then
        docker rm --force "${CONTAINERS[@]}" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT
trap 'exit 1' TERM INT

mkdir -m 700 "$KEYRING_DIR"
mkdir "$WORK_DIR/repo"
# An old host socket or file in the keyring must never be used or replaced.
printf 'Do not use this socket path\n' > "$KEYRING_DIR/S.gpg-agent"

CONTAINER_ARGS=(
    --rm --init --network none
    --user "$TEST_UID:$TEST_GID"
    --cap-drop ALL --security-opt no-new-privileges:true
    --mount "type=bind,src=$KEYRING_DIR,dst=/gnupg"
    --tmpfs "/run/user/$TEST_UID:rw,noexec,nosuid,nodev,mode=0700,uid=$TEST_UID,gid=$TEST_GID"
    --entrypoint /bin/bash
)

docker run "${CONTAINER_ARGS[@]}" private-apt-publisher:local -c '
    set -Eeuo pipefail
    source "$FRAMEWORK_DIR/lib/gnupg.sh"
    prepare_gnupg_socket_directory
    gpg --batch --pinentry-mode loopback --passphrase "" \
        --quick-generate-key "Container test <test@localhost>" ed25519 sign 1d
    gpg --batch --with-colons --list-secret-keys
' > "$WORK_DIR/key-list.txt"
GPG_KEY=$(awk -F: '$1 == "fpr" { print $10; exit }' "$WORK_DIR/key-list.txt")
: "${GPG_KEY:?Container did not generate a key}"

for INSTANCE in first second; do
    NAME="apt-agent-test-${WORK_DIR##*/}-$INSTANCE"
    CONTAINERS+=("$NAME")
    docker run -d --name "$NAME" "${CONTAINER_ARGS[@]}" \
        --mount "type=bind,src=$WORK_DIR/repo,dst=/repo" \
        --env "GPG_KEY=$GPG_KEY" --env CHECK_INTERVAL=3600 \
        --env 'MAINTAINER=Test <test@localhost>' --env REPO_NAME=Test \
        --env REPO_DESCRIPTION=Test --env CODENAME=trixie \
        --env ARCHES=amd64 --env REPO_ARCHITECTURES=amd64 \
        private-apt-publisher:local -c '
            set -Eeuo pipefail
            export PACKAGES_DIR=/tmp/streams
            mkdir "$PACKAGES_DIR"
            exec bash "$FRAMEWORK_DIR/entrypoint.sh"
        '

    # Wait for the real entrypoint to initialize its private socket directory.
    READY=0
    for ATTEMPT in {1..100}; do
        if docker exec "$NAME" gpg-connect-agent --no-autostart /bye; then
            READY=1
            break
        fi
        sleep 0.2
    done
    [[ "$READY" == 1 ]]
    docker exec "$NAME" bash -c '
        set -Eeuo pipefail
        SOCKET=$(gpgconf --list-dirs agent-socket)
        [[ "$SOCKET" == /run/user/"$(id -u)"/gnupg/* ]]
        [[ -S "$SOCKET" ]]
        gpg --batch --local-user "$GPG_KEY" --detach-sign \
            --output /tmp/signature "$FRAMEWORK_DIR/entrypoint.sh"
        gpg --verify /tmp/signature "$FRAMEWORK_DIR/entrypoint.sh"
    '
done

# Record the second agent, stop the first container, and verify the second agent
# is unchanged and still usable. Shared key storage must not share agent lifetime.
SECOND_AGENT=$(docker exec "${CONTAINERS[1]}" gpg-connect-agent 'GETINFO pid' /bye)
docker stop "${CONTAINERS[0]}"
[[ "$(docker exec "${CONTAINERS[1]}" gpg-connect-agent 'GETINFO pid' /bye)" == "$SECOND_AGENT" ]]
docker exec "${CONTAINERS[1]}" gpg --batch --yes --local-user "$GPG_KEY" \
    --detach-sign --output /tmp/signature /opt/apt-publisher/entrypoint.sh

# Track the host PIDs to confirm the agent dies with its container.
AGENT_PIDS=$(docker top "${CONTAINERS[1]}" -eo pid,comm | awk '$2 == "gpg-agent" { print $1 }')
: "${AGENT_PIDS:?Container has no GPG agent}"
docker stop "${CONTAINERS[1]}"
while read -r AGENT_PID; do
    [[ ! -e "/proc/$AGENT_PID" ]]
done <<< "$AGENT_PIDS"

[[ "$(cat "$KEYRING_DIR/S.gpg-agent")" == 'Do not use this socket path' ]]
[[ -z "$(find "$KEYRING_DIR" -type s -print -quit)" ]]
echo 'Both containers signed with isolated agents; agents exited with their containers.'
