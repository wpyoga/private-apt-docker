# Private APT publisher

Build Debian packages from upstream releases and publish them to a signed APT
repository. Each package owns its release query and packaging method. The shared
runner handles scheduling, locking, artifact validation, and repository publishing.

The included `codex` adapter repackages official OpenAI Codex release executables
as `codex-cli`. This is an unofficial package. The container does not expose HTTP;
serve the published directory with an existing Caddy instance.

## Existing deployments

Run these commands from this directory:

```sh
docker compose build
docker compose up -d
docker compose logs -f
```

The Compose service name, default storage paths under `/srv/apt/codex`, signing
key, and Debian client configuration remain compatible. Existing `CODEX_UID` and
`CODEX_GID` settings still work; `REPO_UID` and `REPO_GID` take precedence if set.
Existing repository identity is preserved. Do not rerun setup just to upgrade.

Codex revisions are now automatic; remove any old `DEB_REVISION` setting from
`.env` (it is no longer used). The first update establishes a recipe fingerprint
and rebuilds the current upstream version once at the next published revision.
For example, an existing `1.2.3-3` becomes `1.2.3-4`. A fresh upstream version
starts at revision `1`.

## First-time setup

Install Docker Compose, GnuPG, Python 3, and sudo on the host. Run:

```sh
./codex-repo-setup.sh
docker compose up -d --build
docker compose logs -f
```

Setup creates the system user `codexrepo`, repository directories, and a dedicated
signing key if none exists. It writes `REPO_UID`, `REPO_GID`, and the primary-key
fingerprint to `.env` with mode 0600, preserving unrelated settings. It exports
`repo-pubkey.asc` and prints the fingerprint. Setup does not start the container.

An existing dedicated key may be imported into `/srv/apt/codex/gnupg` before setup.
When multiple primary secret keys exist, select one explicitly:

```sh
GPG_KEY=YOUR_FULL_FINGERPRINT ./codex-repo-setup.sh
```

The unattended publisher requires a signing key it can use without interactive
passphrase entry. Protect the signing-key directory and Docker daemon.

## Configuration

Set these values in `.env` as needed:

| Setting | Default | Purpose |
| --- | --- | --- |
| `REPO_UID`, `REPO_GID` | Required; legacy `CODEX_*` fallback | Container user |
| `GPG_KEY` | Required | Full signing-key fingerprint |
| `PACKAGES` | `codex` | Space-separated adapter directory names |
| `ARCHES` | `amd64 arm64` | Requested Debian architectures |
| `CODENAME` | `trixie` | APT distribution |
| `CHECK_INTERVAL` | `21600` | Seconds between cycles; minimum 3600 |
| `REPO_DATA_DIR` | `/srv/apt/codex` | Host parent of `repo/` and `gnupg/` |
| `REPO_ORIGIN`, `REPO_LABEL` | `Private APT Repository` | Identity for a new repository |
| `REPO_DESCRIPTION` | `Privately packaged Debian software` | Description for a new repository |

Repository settings initialize `repo/conf/distributions` only when absent.
Existing signing-key, codename, or architecture mismatches fail with an error;
update that file deliberately when changing the repository configuration.

The runner also accepts `REPO_DIR`, `GNUPGHOME`, and `PACKAGES_DIR` when invoked
directly. Compose supplies the container paths `/repo` and `/gnupg`.

## Add a package

Create a directory under `packages/` with these files:

```text
packages/example/
    package-name    # One Debian package name, such as example-cli
    query           # Executable release-discovery hook
    build           # Executable .deb creation hook
```

By default, adapters provide complete Debian versions. To opt into automatic
revision assignment, add a `revision-policy` file containing `automatic`. In this
mode, the query provides upstream versions without a packaging revision, and the
runner passes the assigned full Debian version to the build hook. The Codex
adapter uses this mode.

The hook interface is:

```sh
query WORKDIR
build WORKDIR VERSION ARCH OUTPUT
```

`query` writes `WORKDIR/targets.tsv`: one version and architecture per row,
separated by a tab and ending with a newline. Versions are complete Debian
versions by default, or upstream versions with the automatic revision policy. An
empty file means there are no eligible updates. For example:

```text
1.2.3-1	amd64
1.2.3-1	arm64
```

The runner validates the whole manifest before building. Architectures must be
requested by `ARCHES`; duplicate version/architecture pairs are rejected. Use
`printf '%s\t%s\n' "$version" "$arch"` to write actual tabs.

`build` must create a `.deb` at `OUTPUT` with the declared package name and the
requested version and architecture. Each adapter has an isolated temporary
workspace shared between its query and builds. Store additional release metadata
there in any format; the runner does not interpret it. Hooks inherit configuration
such as `ARCHES` and may define package-specific environment settings.

A minimal query hook could look like:

```bash
#!/bin/bash
set -Eeuo pipefail
workspace=$1
version=1.2.3-1  # Replace with this package's upstream query.
for arch in $ARCHES; do
    printf '%s\t%s\n' "$version" "$arch"
done > "$workspace/targets.tsv"
```

The build hook can repack an archive, compile source, or download an upstream
`.deb`. It owns downloads, integrity checks, metadata, installed files, and package
dependencies. See `packages/codex/` for a complete implementation. Add any build
tools to the Dockerfile, make both hooks executable, set `PACKAGES='codex example'`
in `.env`, and rebuild the image. Add package-specific settings to Compose's
`environment` mapping when needed.

Updates already published for the same package, version, and architecture are
skipped. An adapter failure stops that adapter's work, then the runner continues
with remaining adapters. Successful publications remain available; the overall
cycle reports failure and retries at the next interval. Repository export is
attempted even after an adapter fails. Shared configuration failures stop the
cycle before package processing. The repository lock prevents overlapping runs.

## Automatic packaging revisions

The shared runner fingerprints adapter file paths, contents, and executable
permissions, along with the Dockerfile and revision-assignment helper. It excludes
caches and generated `build/` directories. File timestamps, polling, container
restarts, and architecture selection do not change the fingerprint. Changes to
any included file, even comments, conservatively count as recipe changes.

| Situation | Result |
| --- | --- |
| New upstream version | Start at revision `1` |
| Same upstream version and recipe | Reuse the revision; skip published architectures |
| Same upstream version, changed recipe | Increment the revision for all architectures |
| Existing packages without fingerprint state | Use the highest published revision plus `1` |

State lives in `repo/.state/revisions/CODENAME/PACKAGE.json`. The runner reserves a
revision atomically before building and records successful publication separately
for each architecture. Failed builds retry the same revision while the recipe is
unchanged. A partial publication resumes the missing architectures; a process
interrupted after publication can recover from reprepro's package listing. Recipe
reverts also receive a new revision. Keep `.state/` with the repository when moving
or backing it up; losing it causes a conservative rebuild at a higher revision.

If configuration affects package output, an adapter can add `revision-env` with
one environment-variable name per line. Those values enter the fingerprint;
pass them through Compose's `environment` mapping. Do not include variables such
as `ARCHES` unless changing them should rebuild already published architectures.
Invalid state or unrecognized existing Debian revision formats fail rather than
silently resetting the revision.

This detects declared recipe inputs. An unchanged Dockerfile can still resolve
a different base image or different dependency versions during a rebuild. Those
resolved inputs are not fingerprinted automatically; pin them in the Dockerfile
when reproducible revision tracking is needed.

## Local testing

Use `build/` for generated files. Manual local repository data belongs in
`build/local/repo` and `build/local/gnupg`; both Git and Docker ignore `build/`.
To initialize and run a separate local repository:

```sh
export REPO_DATA_DIR="$PWD/build/local"
./codex-repo-setup.sh
docker compose up -d --build
```

Keep `REPO_DATA_DIR` exported for subsequent Compose commands, or record its
absolute path in `.env`. Setup updates `.env` for the selected key and user;
use a separate checkout if you also manage a production deployment from here.

The offline tests use temporary directories under `build/`, clean them up, and
stub GitHub downloads, GPG, and reprepro. They build real fixture `.deb` files
without using a production signing key or repository. Host requirements are Bash,
Python 3.10+ with tarfile's data extraction filter, and Debian's `dpkg` tools.

```sh
python3 -m unittest discover -s tests -v
bash -n entrypoint.sh update.sh codex-repo-setup.sh lib/repository.sh \
    packages/codex/query packages/codex/build
```

## Serve with Caddy

Replace the example Tailnet IP with `tailscale ip -4` on the server:

```caddyfile
http://100.101.102.103:8080 {
    bind 100.101.102.103
    root * /srv/apt/codex/repo
    file_server
}
```

The publisher uses umask 022. Caddy needs read access to `repo/` and traversal
access through its parent directories. Never grant Caddy access to `gnupg/`.

## Debian client

Transfer `repo-pubkey.asc` securely and verify its fingerprint out of band. For an
existing deployment, its original public key and source-list filenames remain
valid. For a new client:

```sh
sudo install -d -m 0755 /etc/apt/keyrings
sudo install -m 0644 repo-pubkey.asc /etc/apt/keyrings/private-repo.asc
printf '%s\n' \
    'deb [signed-by=/etc/apt/keyrings/private-repo.asc] http://100.101.102.103:8080/ trixie main' \
    | sudo tee /etc/apt/sources.list.d/private-repo.list
sudo apt update
sudo apt install codex-cli
```

## Operational notes

- Codex downloads use GitHub TLS and verify GitHub-provided SHA256 digests; these
  are not independent upstream signature verification.
- Codex selects stable `rust-vX.Y.Z` releases and supports amd64 and arm64.
- Release asset names and layouts are upstream assumptions that may change.
- Package-file retention follows reprepro's existing behavior; no additional
  history or retention mechanism is added.
- Tests cover local fixtures. Container builds and live release publication should
  also be verified in your deployment environment.
