# Shared repository initialization. Sourced by update.sh.

initialize_repository() {
    local configuration="$REPO_DIR/conf/distributions" configured_key configured_codename
    local configured_arches arch value
    if [[ ! "$CODENAME" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]]; then
        echo 'Invalid CODENAME' >&2
        return 1
    fi
    [[ "$GPG_KEY" =~ ^[[:xdigit:]]{40}$ || "$GPG_KEY" =~ ^[[:xdigit:]]{64}$ ]] || {
        echo 'GPG_KEY must be a full signing-key fingerprint' >&2
        return 1
    }
    gpg --batch --list-secret-keys "$GPG_KEY" >/dev/null
    mkdir -p "$REPO_DIR/conf"
    if [[ ! -f "$configuration" ]]; then
        local origin=${REPO_ORIGIN:-Private APT Repository}
        local label=${REPO_LABEL:-Private APT Repository}
        local description=${REPO_DESCRIPTION:-Privately packaged Debian software}
        for value in "$origin" "$label" "$description"; do
            [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] || {
                echo 'Repository identity settings must be single-line values' >&2
                return 1
            }
        done
        cat > "$configuration" <<DIST
Origin: $origin
Label: $label
Codename: $CODENAME
Suite: $CODENAME
Architectures: $ARCHES
Components: main
Description: $description
SignWith: $GPG_KEY
DIST
    fi
    configured_key=$(sed -n 's/^SignWith:[[:space:]]*//p' "$configuration")
    configured_codename=$(sed -n 's/^Codename:[[:space:]]*//p' "$configuration")
    configured_arches=$(sed -n 's/^Architectures:[[:space:]]*//p' "$configuration")
    if [[ "$configured_key" != "$GPG_KEY" ]]; then
        echo 'SignWith mismatch in repository configuration' >&2
        return 1
    fi
    if [[ "$configured_codename" != "$CODENAME" ]]; then
        echo 'Codename mismatch in repository configuration' >&2
        return 1
    fi
    for arch in $ARCHES; do
        [[ " $configured_arches " == *" $arch "* ]] || {
            echo "Architecture $arch is missing from $configuration; update it before continuing" >&2
            return 1
        }
    done
}
