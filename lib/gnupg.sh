# Container GnuPG sockets must never use the bind-mounted signing directory.

prepare_gnupg_socket_directory() {
    : "${GNUPGHOME:?GNUPGHOME must be set and non-empty}"

    local RUNTIME_DIR="/run/user/$(id -u)/gnupg"
    local SOCKET_DIR

    # Compose and setup mount a private tmpfs at /run/user/UID. GnuPG needs
    # this explicit step to use it with a non-default home such as /gnupg.
    gpgconf --create-socketdir
    SOCKET_DIR=$(gpgconf --list-dirs socketdir)

    case "$SOCKET_DIR" in
        "$RUNTIME_DIR"|"$RUNTIME_DIR/"*) ;;
        *)
            echo "GnuPG socket directory $SOCKET_DIR must be under $RUNTIME_DIR; check the container tmpfs mount" >&2
            return 1
            ;;
    esac
}
