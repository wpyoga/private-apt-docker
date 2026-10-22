#!/bin/bash
set -Eeuo pipefail
: "${REPO_DIR:=/repo}" "${CODENAME:=trixie}" "${GNUPGHOME:=/gnupg}" "${ARCHES:=amd64}" "${DEB_REVISION:=3}"
: "${GPG_KEY:?Missing GPG_KEY}"
export GNUPGHOME
mkdir -p "$REPO_DIR/conf" "$REPO_DIR/.state"
if [[ ! -f "$REPO_DIR/conf/distributions" ]]; then
  cat > "$REPO_DIR/conf/distributions" <<DIST
Origin: Private Codex Repository
Label: Private Codex Repository
Codename: $CODENAME
Suite: $CODENAME
Architectures: amd64 arm64
Components: main
Description: Precompiled OpenAI Codex CLI
SignWith: $GPG_KEY
DIST
fi
configured_key=$(sed -n 's/^SignWith:[[:space:]]*//p' "$REPO_DIR/conf/distributions" | head -1)
[[ "$configured_key" == "$GPG_KEY" ]] || { echo "SignWith mismatch: config=$configured_key env=$GPG_KEY" >&2; exit 1; }
gpg --batch --list-secret-keys "$GPG_KEY" >/dev/null
exec 9>"$REPO_DIR/.state/update.lock"
flock -n 9 || { echo 'Update already running'; exit 0; }
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
curl -fLsS --retry 3 -H 'Accept: application/vnd.github+json' -H 'User-Agent: private-codex-deb' \
  https://api.github.com/repos/openai/codex/releases/latest -o "$work/release.json"
python3 - "$work/release.json" "$work/assets.tsv" "$ARCHES" <<'PY'
import json, re, sys
r=json.load(open(sys.argv[1])); tag=r['tag_name']
if r.get('draft') or r.get('prerelease') or not re.fullmatch(r'rust-v\d+\.\d+\.\d+',tag):
    raise SystemExit(f'Unexpected release tag: {tag}')
version=tag.removeprefix('rust-v')
assets={a['name']:a for a in r['assets']}
with open(sys.argv[2],'w') as f:
    for arch in sys.argv[3].split():
        target={'amd64':'x86_64-unknown-linux-musl','arm64':'aarch64-unknown-linux-musl'}.get(arch)
        if not target: raise SystemExit(f'Unsupported architecture: {arch}')
        name=f'codex-package-{target}.tar.gz'
        a=assets.get(name)
        if not a or not re.fullmatch(r'sha256:[0-9a-fA-F]{64}',a.get('digest') or ''):
            raise SystemExit(f'Missing archive or SHA256 digest in GitHub release: {name}')
        f.write('\t'.join((version,arch,name,a['browser_download_url'],a['digest'][7:]))+'\n')
PY
while IFS=$'\t' read -r version arch name url sha; do
  package_version="${version}-${DEB_REVISION}"
  # Check architecture explicitly: do not skip amd64 because arm64 exists.
  if reprepro -b "$REPO_DIR" list "$CODENAME" "codex-cli" 2>/dev/null | grep -Fq "codex-cli ${package_version}"; then
    # reprepro list output may contain multiple architectures; verify with show.
    if reprepro -b "$REPO_DIR" list "$CODENAME" "codex-cli" 2>/dev/null | grep -F "${arch}: codex-cli ${package_version}" >/dev/null; then
      echo "Already published: $package_version ($arch)"; continue
    fi
  fi
  echo "Fetching $name"
  curl -fLsS --retry 3 "$url" -o "$work/$name"
  echo "$sha  $work/$name" | sha256sum -c -
  mkdir -p "$work/extract-$arch"
  python3 - "$work/$name" "$work/extract-$arch" <<'PY'
import sys, tarfile
with tarfile.open(sys.argv[1],'r:gz') as tar:
    tar.extractall(sys.argv[2],filter='data')
PY
  src="$work/extract-$arch"
  # Upstream packages normally have bin/ at the archive root; accept a single wrapper directory.
  if [[ ! -f "$src/bin/codex" ]]; then
    mapfile -t dirs < <(find "$src" -mindepth 1 -maxdepth 1 -type d)
    [[ ${#dirs[@]} == 1 && -f "${dirs[0]}/bin/codex" ]] || { echo 'Unexpected package layout' >&2; exit 1; }
    src="${dirs[0]}"
  fi
  for required in bin/codex bin/codex-code-mode-host codex-package.json; do
    [[ -f "$src/$required" ]] || { echo "Missing $required" >&2; exit 1; }
  done
  python3 - "$src/codex-package.json" "$version" <<'PY'
import json,sys
p=json.load(open(sys.argv[1])); expected=sys.argv[2]
if not str(p.get('version','')).startswith(expected):
    raise SystemExit(f'Package metadata version mismatch: {p.get("version")} != {expected}')
if p.get('entrypoint') != 'bin/codex':
    raise SystemExit(f'Unexpected entrypoint: {p.get("entrypoint")}')
PY
  pkg="$work/pkg-$arch"
  root="$pkg/usr/lib/openai-codex"
  mkdir -p "$root" "$pkg/usr/bin" "$pkg/DEBIAN"
  cp -a "$src/." "$root/"
  # Replace upstream bundled tools with distro-managed executables.
  # Keep the expected relative paths as Arch's PKGBUILD does.
  rm -f "$root/codex-resources/bwrap" "$root/codex-path/rg"
  mkdir -p "$root/codex-resources" "$root/codex-path"
  printf '%s\n' '#!/bin/sh' 'exec /usr/bin/bwrap "$@"' > "$root/codex-resources/bwrap"
  printf '%s\n' '#!/bin/sh' 'exec /usr/bin/rg "$@"' > "$root/codex-path/rg"
  chmod 755 "$root/codex-resources/bwrap" "$root/codex-path/rg"
  chmod 755 "$root/bin/codex" "$root/bin/codex-code-mode-host"
  for binary in "$root"/bin/*; do
    [[ -f "$binary" && -x "$binary" ]] || continue
    ln -s "../lib/openai-codex/bin/$(basename "$binary")" "$pkg/usr/bin/$(basename "$binary")"
  done
  cat > "$pkg/DEBIAN/control" <<CONTROL
Package: codex-cli
Version: $package_version
Section: devel
Priority: optional
Architecture: $arch
Maintainer: Private Codex Repository <repo@localhost>
Depends: bubblewrap, ripgrep
Recommends: git
Description: OpenAI Codex CLI (precompiled, Debian system tools)
 Upstream Codex binaries and metadata with Debian bubblewrap and ripgrep.
CONTROL
  out="$work/codex-cli_${package_version}_${arch}.deb"
  dpkg-deb --build --root-owner-group -Zgzip "$pkg" "$out"
  reprepro -b "$REPO_DIR" includedeb "$CODENAME" "$out"
  echo "Published $package_version ($arch)"
done < "$work/assets.tsv"
reprepro -b "$REPO_DIR" export "$CODENAME"
