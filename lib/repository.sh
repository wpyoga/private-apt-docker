# Shared repository configuration. Sourced by update.sh.

configuration_value() {
    sed -n "s/^$1:[[:space:]]*//p" "$REPO_DIR/conf/distributions"
}

initialize_repository() {
    local configuration="$REPO_DIR/conf/distributions" configured_key configured_codename
    local arch value
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
    if [[ ! -f "$configuration" ]]; then
        local origin=${REPO_ORIGIN:-Private APT Repository}
        local label=${REPO_LABEL:-Private APT Repository}
        local description=${REPO_DESCRIPTION:-Privately packaged Debian software}
        for value in "$origin" "$label" "$description"; do
            if [[ "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
                echo 'Repository identity settings must be single-line values' >&2
                return 1
            fi
        done
        cat > "$configuration" <<DIST
Origin: $origin
Label: $label
Codename: $CODENAME
Suite: $CODENAME
Architectures: amd64 arm64
Components: main
Description: $description
SignWith: $GPG_KEY
DIST
    fi
    # Reuse the existing file's identity when migrating from reprepro.
    configured_key=$(configuration_value SignWith)
    configured_codename=$(configuration_value Codename)
    if [[ "$configured_key" != "$GPG_KEY" || "$configured_codename" != "$CODENAME" ]]; then
        echo 'Signing key or codename mismatch in repository configuration' >&2
        return 1
    fi
    if [[ "$(configuration_value Components)" != main ]]; then
        echo 'This publisher supports the main component only' >&2
        return 1
    fi
    REPO_ARCHITECTURES=$(configuration_value Architectures)
    for arch in $REPO_ARCHITECTURES; do
        case "$arch" in
            amd64|arm64) ;;
            *) echo "Unsupported repository architecture: $arch" >&2; return 1 ;;
        esac
    done
    for arch in $ARCHES; do
        if [[ " $REPO_ARCHITECTURES " != *" $arch "* ]]; then
            echo "Architecture $arch is missing from $configuration" >&2
            return 1
        fi
    done
    REPO_ORIGIN=$(configuration_value Origin)
    REPO_LABEL=$(configuration_value Label)
    REPO_DESCRIPTION=$(configuration_value Description)
    REPO_SUITE=$(configuration_value Suite)
    export REPO_ARCHITECTURES REPO_ORIGIN REPO_LABEL REPO_DESCRIPTION REPO_SUITE
}
