# Shared repository configuration. Sourced by update.sh.

configuration_value() {
    sed -n "s/^$1:[[:space:]]*//p" "$REPO_DIR/conf/distributions"
}

initialize_repository() {
    local CONFIG_FILE="$REPO_DIR/conf/distributions"
    local CONFIGURED_KEY CONFIGURED_CODENAME ARCHITECTURE VALUE

    if [[ ! "$CODENAME" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]]; then
        echo 'Invalid CODENAME' >&2
        return 1
    fi
    if [[ ! "$GPG_KEY" =~ ^[[:xdigit:]]{40}$ && ! "$GPG_KEY" =~ ^[[:xdigit:]]{64}$ ]]; then
        echo 'GPG_KEY must be a full signing-key fingerprint' >&2
        return 1
    fi
    gpg --batch --list-secret-keys "$GPG_KEY" >/dev/null
    mkdir -p "$REPO_DIR/conf" "$REPO_DIR/pool"
    if [[ ! -f "$CONFIG_FILE" ]]; then
        local ORIGIN=${REPO_ORIGIN:-Private APT Repository}
        local LABEL=${REPO_LABEL:-Private APT Repository}
        local DESCRIPTION=${REPO_DESCRIPTION:-Privately packaged Debian software}
        for VALUE in "$ORIGIN" "$LABEL" "$DESCRIPTION"; do
            if [[ "$VALUE" == *$'\n'* || "$VALUE" == *$'\r'* ]]; then
                echo 'Repository identity settings must be single-line values' >&2
                return 1
            fi
        done
        cat > "$CONFIG_FILE" <<DIST
Origin: $ORIGIN
Label: $LABEL
Codename: $CODENAME
Suite: $CODENAME
Architectures: amd64 arm64
Components: main
Description: $DESCRIPTION
SignWith: $GPG_KEY
DIST
    fi
    # Reuse the existing file's identity when migrating from reprepro.
    CONFIGURED_KEY=$(configuration_value SignWith)
    CONFIGURED_CODENAME=$(configuration_value Codename)
    if [[ "$CONFIGURED_KEY" != "$GPG_KEY" || "$CONFIGURED_CODENAME" != "$CODENAME" ]]; then
        echo 'Signing key or codename mismatch in repository configuration' >&2
        return 1
    fi
    if [[ "$(configuration_value Components)" != main ]]; then
        echo 'This publisher supports the main component only' >&2
        return 1
    fi
    REPO_ARCHITECTURES=$(configuration_value Architectures)
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
            echo "Architecture $ARCHITECTURE is missing from $CONFIG_FILE" >&2
            return 1
        fi
    done
    REPO_ORIGIN=$(configuration_value Origin)
    REPO_LABEL=$(configuration_value Label)
    REPO_DESCRIPTION=$(configuration_value Description)
    REPO_SUITE=$(configuration_value Suite)
    export REPO_ARCHITECTURES REPO_ORIGIN REPO_LABEL REPO_DESCRIPTION REPO_SUITE
}
