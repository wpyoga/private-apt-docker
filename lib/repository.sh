# Shared configuration checks. Sourced by entrypoint.sh and update.sh.

validate_repository_config() {
    : "${REPO_DIR:?REPO_DIR must be set and non-empty}"
    : "${PACKAGES_DIR:?PACKAGES_DIR must be set and non-empty}"
    : "${GNUPGHOME:?GNUPGHOME must be set and non-empty}"
    : "${GPG_KEY:?GPG_KEY must be set and non-empty}"
    : "${MAINTAINER:?MAINTAINER must be set and non-empty}"
    : "${REPO_NAME:?REPO_NAME must be set and non-empty}"
    : "${REPO_DESCRIPTION:?REPO_DESCRIPTION must be set and non-empty}"
    : "${CODENAME:?CODENAME must be set and non-empty}"
    : "${ARCHES:?ARCHES must be set and non-empty}"
    : "${REPO_ARCHITECTURES:?REPO_ARCHITECTURES must be set and non-empty}"

    if [[ ! -d "$PACKAGES_DIR" ]]; then
        echo "PACKAGES_DIR does not exist: $PACKAGES_DIR" >&2
        return 1
    fi

    local VALUE ARCHITECTURE
    for VALUE in "$MAINTAINER" "$REPO_NAME" "$REPO_DESCRIPTION"; do
        if [[ "$VALUE" == *$'\n'* || "$VALUE" == *$'\r'* ]]; then
            echo 'Maintainer and repository identity must be single-line values' >&2
            return 1
        fi
    done
    if [[ ! "$CODENAME" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]]; then
        echo 'Invalid CODENAME' >&2
        return 1
    fi
    if [[ ! "$GPG_KEY" =~ ^[[:xdigit:]]{40}$ && ! "$GPG_KEY" =~ ^[[:xdigit:]]{64}$ ]]; then
        echo 'GPG_KEY must be a full signing-key fingerprint' >&2
        return 1
    fi
    for ARCHITECTURE in $REPO_ARCHITECTURES; do
        case "$ARCHITECTURE" in
            amd64|arm64) ;;
            *)
                echo "Unsupported repository architecture: $ARCHITECTURE" >&2
                return 1
                ;;
        esac
    done
    for ARCHITECTURE in $ARCHES; do
        if [[ " $REPO_ARCHITECTURES " != *" $ARCHITECTURE "* ]]; then
            echo "Selected architecture $ARCHITECTURE is not in REPO_ARCHITECTURES" >&2
            return 1
        fi
    done
}

initialize_repository() {
    gpg --batch --list-secret-keys "$GPG_KEY" >/dev/null
    mkdir -p "$REPO_DIR/pool"
}
