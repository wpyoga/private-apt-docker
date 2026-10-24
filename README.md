# Private APT publisher

This container checks upstream releases, builds Debian packages, and publishes
one signed APT repository. It includes an unofficial repackaging of the official
OpenAI Codex executables as `codex-cli`.

The container does not serve HTTP. Point an existing Caddy instance at `repo/`.

## How an update works

1. Take the repository lock so another updater cannot write at the same time.
2. Read the stream directories under `packages/`, in alphabetical order.
3. Finish one stream before starting the next: query, choose package revisions,
   build missing architectures, and store the results.
4. Generate and sign repository indexes containing all stored package versions.
5. Wait six hours after the entire cycle finishes, then start again.

The first cycle starts immediately. A twenty-minute cycle starting at 08:00 is
followed by a six-hour wait, so the next starts at 14:20. There is no parallel
package processing. A stream failure does not prevent other streams from running.
Successful artifacts remain stored and index publication is still attempted.

The lock uses `flock`, rather than testing whether a lock file exists. The
operating system releases it when the processes holding it exit. The empty file
may remain; it is not a stale lock. The lock protects against a second container
or a manual invocation using the same storage.

## Existing deployments

From this directory:

```sh
docker compose build
docker compose up -d
docker compose logs -f
```

Existing client source lists, public keys, storage paths, and the Compose service
name remain valid. `CODEX_UID` and `CODEX_GID` still work; `REPO_UID` and `REPO_GID`
take precedence when set. Do not rerun setup just to upgrade.

This implementation replaces reprepro with Debian's index-generation tools. It
reuses the identity and signing configuration in `repo/conf/distributions` and
indexes existing `.deb` files in `repo/pool/`. Old reprepro databases and revision
JSON files are left untouched and are no longer read.

Remove obsolete `PACKAGES` and `DEB_REVISION` settings from `.env`. Directory
listing now selects streams; package metadata now supplies revision history.
Existing artifacts without our metadata remain available. Their first automatic
rebuild uses the next revision and establishes the metadata, for example `-3` to
`-4`. No revision state or checksum sidecar files are created.

## First-time setup

The host needs Docker Compose, GnuPG, Python 3, sudo, and the usual core utilities.
Run:

```sh
./codex-repo-setup.sh
docker compose up -d --build
docker compose logs -f
```

Setup creates the `codexrepo` system user, storage directories, and a dedicated
signing key if none exists. It writes `REPO_UID`, `REPO_GID`, and `GPG_KEY` to `.env`
with mode 0600, preserving unrelated settings. It exports `repo-pubkey.asc` and
prints the fingerprint. Setup does not start the container.

You may import an existing dedicated key into `/srv/apt/codex/gnupg` first. If that
keyring has multiple primary secret keys, select one explicitly:

```sh
GPG_KEY=YOUR_FULL_FINGERPRINT ./codex-repo-setup.sh
```

Signing must work without interactive passphrase entry. Protect the signing key
and Docker daemon. Verify the public-key fingerprint out of band before using it
on clients.

## Configuration

Set these values in `.env` as needed:

| Setting | Default | Purpose |
| --- | --- | --- |
| `REPO_UID`, `REPO_GID` | Required; legacy `CODEX_*` fallback | Container user |
| `GPG_KEY` | Required | Full signing-key fingerprint |
| `ARCHES` | `amd64 arm64` | Architectures to check and build |
| `CODENAME` | `trixie` | APT distribution |
| `CHECK_INTERVAL` | `21600` | Seconds to wait after a cycle; minimum 3600 |
| `REPO_DATA_DIR` | `/srv/apt/codex` | Host parent of `repo/` and `gnupg/` |
| `REPO_ORIGIN`, `REPO_LABEL` | `Private APT Repository` | Identity for a new repository |
| `REPO_DESCRIPTION` | `Privately packaged Debian software` | Description for a new repository |

Existing repository configuration is preserved. Signing-key, codename, component,
or architecture mismatches fail explicitly. The supported component is `main`.
New repositories configure both amd64 and arm64. Selecting only amd64 for a cycle
does not remove already published arm64 packages from the indexes.

Direct invocations also accept `REPO_DIR`, `GNUPGHOME`, and `PACKAGES_DIR`.
Compose supplies `/repo` and `/gnupg` inside the container.

## One directory per stream

A stream is an upstream release line that we choose to follow. For example:

```text
packages/
    codex/
    gimp-3.2/
    gimp-3.4/
```

Each directory is independent and contains:

```text
package-name       Debian package name, such as gimp
query              Executable upstream query script
build              Executable packaging script
revision-policy    Optional: automatic
revision-env       Optional: build environment variable names, one per line
stale-after-days   Optional: inactivity warning threshold
```

Directory names may contain lowercase letters, digits, dots, underscores, and
hyphens, and must start with a letter or digit. Hidden directories are not selected.
All other immediate directories are processed; an incomplete stream reports an
error without stopping the others. There is no central package registry.

Both `gimp-3.2` and `gimp-3.4` may declare `gimp` as their Debian package name. Their
different versions are published in the same repository. APT applies its normal
version and priority rules. Merely publishing both does not keep a client on the
older stream; use client-side pinning when that is desired.

The query script selects the latest eligible release in its own stream. It owns
upstream-specific naming, channels, version conversion, and release ordering. The
runner does not infer semantic versioning or switch streams automatically. Codex
uses GitHub's latest stable release and supports amd64 and arm64.

To add a stream, add its directory and rebuild the container image. To stop
tracking one, remove its directory and rebuild. Its previously published packages
remain available. No real GIMP adapters are included; those names illustrate the
directory design.

## Query and build hooks

The interface remains:

```sh
query WORKDIR
build WORKDIR VERSION ARCH OUTPUT
```

`query` writes `WORKDIR/targets.tsv`. Each row contains a version, a tab, an
architecture, and a newline. Return at most one current version per requested
architecture. Use `printf '%s\t%s\n' "$version" "$arch"` to produce actual tabs.
An empty file means no eligible artifacts are available.

With `revision-policy` set to `automatic`, query versions are upstream versions:

```text
1.2.3<TAB>amd64
1.2.3<TAB>arm64
```

The runner assigns a Debian revision, such as `1.2.3-2`, before calling `build`.
Without that policy, query versions must already be complete Debian versions;
the adapter owns their revisions.

If an upstream release has only amd64 available, return that row. The runner
publishes it, warns about arm64, retains any previous arm64 package, and checks
again during the next cycle. Do not invent rows for missing downloads. Actual
query errors should return a nonzero exit status.

The build hook receives these environment variables:

| Variable | Meaning |
| --- | --- |
| `PUBLISHER_STREAM` | Stream directory name |
| `BUILD_INPUTS_SHA256` | Current packaging-input checksum |
| `ARCHES` | Architectures selected for this cycle |

For automatic revisions, include these fields in the binary package control file:

```text
X-Build-Inputs-SHA256: <value of BUILD_INPUTS_SHA256>
X-Publisher-Stream: <value of PUBLISHER_STREAM>
```

The runner verifies these fields, name, version, and architecture before accepting
the output. A build hook may repack binaries, compile source, or import an upstream
`.deb`; an importer using automatic revisions must add the fields and assigned
version to the control metadata before returning its output.

Each stream has a temporary workspace shared by query and build. Store download
URLs, archive checksums, or other query results there in any convenient format.
The hook owns download integrity checks, dependencies, file layout, and maintainer
scripts. See `packages/codex/` for the included adapter.

## Checksums and Debian revisions

Our input checksum answers whether the packaging recipe changed. It covers:

- Adapter file paths, contents, and executable permissions.
- The Dockerfile.
- Environment values named in the adapter's `revision-env` file.

It excludes revision helpers, inactivity settings, caches, generated `build/`
directories, timestamps, and architecture selection. Changes to included comments
also count as recipe changes. Do not list `ARCHES` in `revision-env` unless selecting
another architecture should rebuild the existing ones.

This checksum is embedded in the `.deb`; there are no separate checksum files.
Inspect it without unpacking the main payload:

```sh
dpkg-deb --field PACKAGE.deb X-Build-Inputs-SHA256
dpkg-deb --field PACKAGE.deb X-Publisher-Stream
```

The runner reads filenames and control metadata to decide what to build:

| Situation | Result |
| --- | --- |
| No package for this upstream version | Start at revision 1 |
| Latest artifact for this stream has the same recipe checksum | Reuse its revision; build only missing architectures |
| Recipe changed, or existing artifacts have no matching metadata | Use the highest existing revision plus 1 |
| New upstream version | Start its revision at 1 |

Revision allocation considers all streams producing the same Debian package and
upstream version, so they do not collide. A stream reuses its own latest matching
artifact even when another stream has a higher revision. Reverting a recipe also
requires a new revision. Historical upstream versions are not rebuilt merely
because the packaging script changed.

A completely failed attempt leaves no artifact and retries the same next revision.
A partial success carries the metadata needed to resume at that revision. Complete
files appear atomically in `pool/main/STREAM/`; different contents cannot replace
an existing package/version/architecture identity.

The recipe checksum differs from a download checksum. Codex verifies each archive
against GitHub's SHA256 digest during download. Those digests are not currently
part of recipe change detection. Unchanged Dockerfile text may also resolve a
changed base image or dependency version; pin those inputs when needed.

## Inactivity warnings

Put a positive day count in a stream's `stale-after-days` file to enable monitoring.
There is no universal threshold. The query should then write the latest matching
upstream release's publication timestamp to `WORKDIR/release-date`, for example:

```text
2026-10-23T08:00:00Z
```

If that release is older than the threshold, every cycle logs a prominent warning
with its date, age, and threshold. Checking and publishing continue normally.
Missing or invalid dates report that activity cannot be assessed; they do not
block publication. Network/query errors remain separate failures.

A new upstream release updates the release age. Changing the packaging script
does not. Streams are never automatically paused, retired, deleted, or migrated.

## Repository storage and serving

All stored `.deb` versions remain available, including old stream releases and
packaging revisions. There is no automatic cleanup policy. Indexes are generated
with `dpkg-scanpackages --multiversion`; `apt-ftparchive` creates release metadata,
and GPG signs it. Generation and signing finish before live indexes are replaced.
Signing failures leave the previous live indexes intact. Stored artifacts are
available for the next publication attempt without rebuilding.

Hash-addressed indexes are retained so APT clients can finish fetching an earlier
signed release while new indexes are being published. Back up the entire `repo/`
and the signing key separately. Never serve the signing-key directory.

For Caddy, replace the Tailnet IP with your server's address:

```caddyfile
http://100.101.102.103:8080 {
    bind 100.101.102.103
    root * /srv/apt/codex/repo
    file_server
}
```

Caddy needs read access to `repo/` and traversal access through its parents. The
publisher uses umask 022. Never grant Caddy access to `gnupg/`.

## Debian client

Transfer `repo-pubkey.asc` securely and verify its fingerprint out of band:

```sh
sudo install -d -m 0755 /etc/apt/keyrings
sudo install -m 0644 repo-pubkey.asc /etc/apt/keyrings/private-repo.asc
printf '%s\n' \
    'deb [signed-by=/etc/apt/keyrings/private-repo.asc] http://100.101.102.103:8080/ trixie main' \
    | sudo tee /etc/apt/sources.list.d/private-repo.list
sudo apt update
sudo apt install codex-cli
```

Existing deployments may keep their original key and source-list filenames.
For same-name streams, select a particular published version using
`apt install PACKAGE=VERSION`; configure APT preferences to stay within a stream.
Using Debian's package name permits replacement, but APT version, priority, and
dependency rules still determine which package is chosen.

## Local testing

Generated files belong under ignored `build/`. Manual local repository data uses
`build/local/repo` and `build/local/gnupg`:

```sh
export REPO_DATA_DIR="$PWD/build/local"
./codex-repo-setup.sh
docker compose up -d --build
```

Keep the variable exported for subsequent Compose commands, or save its absolute
path in `.env`. Setup updates `.env` for the chosen repository; use a separate
checkout if you also manage a production deployment from here.

Run the offline regression suite:

```sh
python3 -m unittest discover -s tests -v
```

It uses temporary directories under `build/`, fixture downloads, fake signatures,
and real Debian package/index tools. Host requirements are Bash, Python 3.10+ with
tarfile's data extraction filter, `dpkg-dev`, `apt-utils`, and GnuPG.

The real signing/APT integration check is a standalone Bash script:

```sh
bash tests/test-signed-repo.sh
```

It creates a throwaway key and two fixture streams, verifies that APT accepts the
signed repository, and simulates selecting both versions. It redirects APT state
into the test directory and never installs packages on the host. GPG agent startup
requires permission to create a local socket. Both checks clean up their test data.

Container image builds and live upstream publication remain deployment checks.
