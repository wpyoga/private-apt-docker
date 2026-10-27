# Private APT publisher

This container checks upstream releases, builds Debian packages, and publishes
one signed APT repository. It includes an unofficial repackaging of the official
OpenAI Codex executables as `codex-cli`, community Ghostty Debian packages as
`ghostty`, native GIMP 3.2 packages from the official AppImages, and the official
Zed editor binaries repackaged with Debian shared libraries as `zed`, and
[Laya's Python library, CLI, and HTTP server](docs/laya.md) as `python3-laya`,
`laya-cli`, and `laya-http`. Laya uses selected Debian Forky dependencies and
privately bundled Click; its client setup is documented separately.

The container does not serve HTTP. Point an existing Caddy instance at `repo/`.

For development, read [AGENTS.md](AGENTS.md) for coding conventions and
[ARCHITECTURE.md](ARCHITECTURE.md) for the design rationale, adapter development
workflow, and guidance for resuming work in another session.

## How an update works

1. Take the repository lock so another updater cannot write at the same time.
2. Read adapter directories under `packages/`, in alphabetical order.
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

## Framework scripts

Scripts receive their directories and stream settings through the exported
environment. They require that context rather than searching for paths or
reading the adapter configuration again.

| File | Responsibility |
| --- | --- |
| `entrypoint.sh` | Run an update, wait for the configured interval, repeat |
| `update.sh` | Lock the repository, discover streams, process them, publish |
| `lib/config.sh` | Read and validate one adapter's configuration as data |
| `lib/repository.sh` | Check the shared repository settings |
| `lib/update-package.sh` | Query and build one stream |
| `lib/resolve-builds.py` | Validate query targets and choose revisions and missing builds |
| `lib/store-packages.sh` | Validate the whole output set and store packages without replacing existing files |
| `lib/publish.sh` | Generate indexes, sign them, then publish them |
| `lib/checksum.py` | Fingerprint the packaging inputs |
| `lib/check-activity.py` | Compare the upstream release date with the inactivity threshold |
| `codex-repo-setup.sh` | Prepare host storage and signing identity, then update `.env` |

Shell handles process coordination, file installation, and the setup config
update. Python handles revision bookkeeping, file fingerprints, and dates with
timezones. Target validation lives with revision selection because both use the
same query results. Package storage has its own script because it handles the
finished artifacts rather than deciding which builds to run.

## Existing deployments

From this directory:

```sh
docker compose build
docker compose up -d
docker compose logs -f
```

Existing client source lists, public keys, storage paths, and the Compose service
name remain valid. Set `REPO_UID` and `REPO_GID` explicitly in `.env`; legacy
`CODEX_UID` and `CODEX_GID` fallbacks are no longer used. Do not rerun setup just to
upgrade an existing deployment.

The operator-owned `.env` is the central configuration file. Compare your existing
file with `.env.example` and supply every required setting before rebuilding.
Set `REPO_NAME` to the current repository identity if you want to preserve it.
The publisher no longer reads or generates `repo/conf/distributions`; it uses the
configured name and signing key directly. Existing repository databases and
revision JSON files are left untouched and are no longer read.

Remove obsolete `PACKAGES`, `DEB_REVISION`, `REPO_ORIGIN`, and `REPO_LABEL` settings.
Directory listing selects adapters; package metadata supplies revision history.
Existing artifacts without our metadata remain available. Their first automatic
rebuild uses the next revision and establishes the metadata, for example `-3` to
`-4`. No revision state or checksum sidecar files are created.

## First-time setup

The host needs Docker Compose, GnuPG, sudo, and the usual core utilities.
From the project directory:

```sh
cp .env.example .env
chmod 600 .env
# Edit .env: set your MAINTAINER, REPO_NAME, key identity, and storage directory.
export FRAMEWORK_DIR="$PWD"
./codex-repo-setup.sh
docker compose up -d --build
docker compose logs -f
```

Setup reads exactly `$FRAMEWORK_DIR/.env`, validates its required inputs, creates
the configured system user and storage directories, and generates a dedicated
signing key if none exists. It writes `REPO_UID`, `REPO_GID`, and `GPG_KEY` back to
that file with mode 0600, preserving other settings. It exports `repo-pubkey.asc`
and prints the fingerprint. Setup does not start the container.

You may import an existing dedicated key into the configured `gnupg/` directory
first. If it contains multiple primary secret keys, set `GPG_KEY` in `.env` to the
full fingerprint of the key you intend to use.

Signing must work without interactive passphrase entry. Protect the signing key
and Docker daemon. Verify the public-key fingerprint out of band before using it
on clients.

## Central configuration

`.env.example` lists the required settings with explicit example values. Copy it
to `.env` and edit it using shell-compatible `NAME=value` assignments. Setup
sources this operator-owned file; Compose reads it as its environment file. The
scripts do not invent missing settings or search for alternate config paths.

| Setting | Purpose |
| --- | --- |
| `MAINTAINER` | Debian package maintainer, in `Name <email>` form |
| `REPO_NAME` | APT repository name, used for both Origin and Label |
| `REPO_DESCRIPTION` | APT repository description |
| `CODENAME` | APT distribution and suite |
| `ARCHES` | Architectures to check and build this cycle |
| `REPO_ARCHITECTURES` | Architectures whose repository indexes are published |
| `CHECK_INTERVAL` | Seconds to wait after a cycle; minimum 3600 |
| `REPO_DATA_DIR` | Host parent of `repo/` and `gnupg/` |
| `REPO_USER` | System user created or reused by setup |
| `GPG_KEY_NAME`, `GPG_KEY_TYPE`, `GPG_KEY_VALIDITY` | Explicit signing-key creation settings |
| `REPO_UID`, `REPO_GID`, `GPG_KEY` | Setup outputs; supply existing values when upgrading |

Changing `MAINTAINER` rebuilds every package at the next packaging revision. Changing
`REPO_NAME` updates signed repository metadata without rebuilding package files.
Maintainer and repository identity values must be single-line strings.

Docker defines its fixed paths explicitly: `FRAMEWORK_DIR=/opt/apt-publisher`,
`PACKAGES_DIR=/opt/apt-publisher/packages`, `REPO_DIR=/repo`, and `GNUPGHOME=/gnupg`.
Direct host invocations must export their own values for those paths and the
required settings. There are no path-discovery fallbacks.

Both amd64 and arm64 are supported. Selecting only amd64 for a cycle does not
remove arm64 packages when `REPO_ARCHITECTURES` still includes arm64. Missing or
empty required settings fail before repository files are written; Compose also
rejects missing settings before starting the container.

## One directory per configured release stream

Each immediate, non-hidden directory under `packages/` contains one adapter. Its
name is descriptive only: renaming it does not change stream identity, package
names, storage paths, recipe checksums, or revision history. Directory names affect
only processing order and diagnostic paths.

Each adapter contains:

```text
config             Release stream identity and binary package names
query              Executable upstream query script
build              Executable packaging script
stale-after-days   Optional: inactivity warning threshold
```

For Codex, `config` contains:

```sh
RELEASE_STREAM=codex
BINARY_PACKAGES=codex-cli
```

A build producing several packages can use:

```sh
RELEASE_STREAM=example-stable
BINARY_PACKAGES="example-cli example-common"
```

Adapter configuration is parsed as data, never sourced as shell code. Use one `key=value`
per line, with no spaces around `=`. Blank lines and whole-line comments are
allowed. Values may have matching single or double quotes; quotes are removed
without shell expansion. Only the two keys above are accepted, each exactly once.
Package names form a space-separated list of distinct Debian package names.
Stream IDs use lowercase letters, digits, dots, underscores, and hyphens, beginning
with a letter or digit. They must be unique among adapters in a cycle; duplicate
IDs report an error and the later adapter is skipped.

One directory follows one configured release stream. The query hook owns how that
stream selects upstream releases; the stream ID is an identity, not a channel
name that the runner interprets. Codex follows GitHub's latest stable release and
supports amd64 and arm64. Its `query` hook contains both the release download
and JSON processing using Bash and `jq`, with no inline Python or separate
release helper. Its build hook renders `@VARNAME@` placeholders in
`control.in` using `sed`. Extraction and validation live in short functions
inside the build hook. Codex expects `bin/` and `codex-package.json` directly at
the archive root. A wrapper directory or changed layout fails with a missing-file
error; update the adapter deliberately when upstream changes its layout.
GNU tar handles extraction paths. Packaging checks reject special files and
external links before copying or changing permissions, and validate the expected
files, version, and entrypoint. There is no Python code in the Codex adapter.
Multiple adapters may declare the same Debian package name to
publish different release streams. APT applies its normal version and priority
rules; client-side pinning is needed to stay on an older stream.

To add or remove an adapter, change its directory and rebuild the container image.
Previously published packages remain available. Incomplete adapters report an
error without blocking the other adapters. There is no central package registry.

Existing custom adapters must replace `package-name` with `config` and use the
uppercase keys `RELEASE_STREAM` and `BINARY_PACKAGES`; lowercase keys are no longer
accepted. They must also adopt the
environment-based context and output-directory build interface below. Set
`RELEASE_STREAM` to the previous stream directory name to retain existing package metadata identity. Configuration
and build recipe changes allocate a new revision; existing artifacts stay intact.

## Query and build hooks

The hook interface is:

```sh
query
build VERSION ARCH OUTPUT_DIR
```

`query` writes `WORKSPACE/targets.tsv`. Each row contains a version, a tab, an
architecture, and a newline. Return at most one current version per requested
architecture. Use `printf '%s\t%s\n' "$VERSION" "$ARCHITECTURE"` to produce
actual tabs.
An empty file means no eligible artifacts are available.

Query versions are upstream versions; the runner always assigns Debian revisions:

```text
1.2.3<TAB>amd64
1.2.3<TAB>arm64
```

The runner assigns a Debian revision, such as `1.2.3-2`, before calling `build`.

If an upstream release has only amd64 available, return that row. The runner
publishes it, warns about arm64, retains any previous arm64 package, and checks
again during the next cycle. Do not invent rows for missing downloads. Actual
query errors should return a nonzero exit status.

The framework exports the context below before calling query and build hooks.
Hooks are part of the framework: they must use `ADAPTER_DIR` to locate their files,
and must not rediscover their directory from `$0` or `BASH_SOURCE`. Production entry
scripts require a non-empty `FRAMEWORK_DIR`, without directory-discovery fallbacks.
Docker sets it to `/opt/apt-publisher`; on the host, export `FRAMEWORK_DIR="$PWD"`
from the project directory before running shell entry points. The runner
exports a fresh `WORKSPACE` for each adapter. Query hooks take no arguments;
build hooks take only the changing version, architecture, and output directory.
Declare required context with `: "${WORKSPACE:?WORKSPACE must be set and non-empty}"`
(and the same check for other required inputs). This fails before work begins if
an input is missing or empty. Do not add standalone fallbacks. Shell
variables use `UPPER_CASE`; functions retain descriptive lowercase names.

Query and build hooks receive these environment variables:

| Variable | Meaning |
| --- | --- |
| `ADAPTER_DIR` | Absolute path to the current adapter directory |
| `FRAMEWORK_DIR` | Absolute path to the framework root |
| `WORKSPACE` | Absolute path to this adapter’s temporary working directory |
| `PUBLISHER_STREAM` | Configured `RELEASE_STREAM` |
| `BINARY_PACKAGES` | Configured binary package names, separated by spaces |
| `MAINTAINER` | Global Debian package maintainer from `.env` |
| `BUILD_INPUTS_SHA256` | Current packaging-input checksum; provided before build |
| `ARCHES` | Architectures selected for this cycle |

Include these fields in the binary package control file:

```text
X-Build-Inputs-SHA256: <value of BUILD_INPUTS_SHA256>
X-Publisher-Stream: <value of PUBLISHER_STREAM>
```

Every output package must also contain `Installed-Size`, the estimated unpacked
disk usage in KiB used by APT. Calculate it from the final staged package tree,
excluding the `DEBIAN/` metadata directory, before building the `.deb`:

```bash
INSTALLED_SIZE=$(du --summarize --block-size=1024 --exclude=DEBIAN "$PACKAGE_DIR" | cut -f1)
```

Write that integer into the control file as `Installed-Size: VALUE`. Recalculate
the field for imported packages as well, replacing any upstream value.
`dpkg-deb --build` does not calculate it automatically. Test both the final
package field and the published index; importers must handle missing or stale
upstream size metadata.

Every adapter must expect a fixed layout inside its selected upstream artifact.
Check the required paths and metadata before producing packages. If upstream moves
or removes expected files, log an error naming the missing path and exit nonzero.
Do not search for alternative roots, unwrap arbitrary directories, or silently
adapt to a changed layout. The maintainer must update the adapter explicitly.

The framework logs the failed stream, version, and architecture. Existing packages
remain available and other streams continue processing. Logs are the maintainer
notification mechanism for now; no email or external alerts are sent.

File-type and link restrictions are adapter-specific packaging policy. Codex
rejects special files and links outside its extraction directory because its
expected bundle does not need them, and later build steps read or modify files.
Other adapters must explicitly handle any such entries their package needs.

The runner calls `build` once per needed architecture, allowing one download or
compilation to produce all declared binary packages. `OUTPUT_DIR` is an existing,
empty directory. Write exactly one `NAME_VERSION_ARCH.deb` per declared package
there, with no extra files. All outputs use the assigned version. Each output
uses either the requested architecture or `all`, including the filename suffix.
An `all` package is stored once and included in both architecture indexes. The
hook still emits its complete declared set when another architecture needs a build.

The runner validates the entire output set, including name, version, architecture,
and the fields above, before storing any output. On a resumed build, matching
stored outputs retain their original bytes and only missing packages are stored.
A failed hook or invalid output set stores nothing from that invocation. A build
hook may repack binaries, compile source, or import an upstream `.deb`; an importer
must add the fields and assigned version to the control metadata before returning
its output.

Each stream has a temporary workspace shared by query and build. Store download
URLs, archive checksums, or other query results there in any convenient format.
The hook owns download integrity checks, dependencies, file layout, and maintainer
scripts. See `packages/codex/` for the included adapter.

## Ghostty

`packages/ghostty/` imports the latest stable release from
[mkasberg/ghostty-ubuntu](https://github.com/mkasberg/ghostty-ubuntu), the community
Debian package source linked by Ghostty's installation documentation. It selects
Debian Trixie assets for amd64 and arm64, regardless of the repository suite name.
These are community binaries, not official Ghostty Linux binaries.

The adapter verifies GitHub's SHA256 digest and the package name, version,
architecture, and required executable, desktop entry, and terminfo paths. It
preserves upstream dependencies, resources, and maintainer scripts, and replaces
version, maintainer, and publisher metadata without executing those scripts.
Community rebuilds remain part of the tracked version: release `1.3.1-0-ppa2`
becomes `1.3.1+0.ppa2-1`. Missing architectures retain previously published packages.
After rebuilding the publisher image and publishing an update cycle, clients can
install it with `sudo apt install ghostty`.

## Zed

`packages/zed/` follows the latest stable
[official Zed release](https://github.com/zed-industries/zed/releases/latest)
for amd64 and arm64. It verifies GitHub's SHA256 digest and repackages the fixed
Linux archive layout for Debian 13. This is unofficial Debian packaging of
official binaries, not an official Zed APT repository.

The package uses Debian shared libraries instead of all nine upstream bundled
libraries. A small `/usr/bin/zed` wrapper disables Zed's built-in updater and
directs users to APT. Desktop launching uses the same wrapper. A working Vulkan
GPU/driver and desktop portal backend are needed for desktop functionality.
Install it with `sudo apt install zed` after rebuilding the publisher image and
publishing an update cycle.

See [Zed packaging and validation notes](docs/zed.md), particularly the
`libXdmcp -> libbsd` dependency difference and pending laptop desktop checks.

## GIMP 3.2

`packages/gimp-3.2/` selects the newest stable **3.2.x** release from GIMP's
[official release metadata](https://www.gimp.org/gimp_versions.json). It checks
the official SHA256 digest and extracts the amd64 or arm64 AppImage as data;
it does not execute AppRun, require FUSE, or run target binaries during builds.
The packages target Debian 13 and retain the official binaries' CPU requirements.

The stream produces `gimp`, `gimp-data`, `libgimp-3.0-0`, `gir1.2-gimp-3.0`,
`gimp-bundled-runtime`, `libgimp-3.0-bin`, `libgimp-3.0-dev`, and
`libgimp-3.0-doc`. The development package includes matching private Babl/GEGL
headers and pkg-config entries; the documentation package imports upstream's
generated HTML API reference. Only babl/GEGL and their modules/typelibs remain
private. Other libraries use Debian packages. GIMP depends explicitly on
`libheif1` and its six codec plugins, including JPEG2000 encoding and decoding.
The existing Debian babl/GEGL packages are not replaced. Each binary package
declares its own linked and reviewed indirect dependencies. Updates come through
APT; the package disables upstream update checks. JavaScript/Lua example plug-ins
are omitted, while upstream format support (including MNG) is retained.
Optional remote-file support is provided by the suggested gvfs-backends package.

After rebuilding the publisher image and completing an update cycle, clients
can use `sudo apt install gimp`. The tested replacement sequence removes Debian
GIMP without purging before installing this repack. Direct upgrades and third-party
plugins have not been validated. Existing package names and the GIMP 3 API's
`3.0` directory names are preserved.

An unresolved TIFF-thumbnail round-trip discrepancy is deferred; see
[GIMP packaging and validation notes](packages/gimp-3.2/gimp-3.2.md). The adapter deliberately
fails on unexpected layouts, architectures, Debian baselines, or external SONAMEs.
Adding a newer release series requires a separate adapter.

The same adapter imports the precompiled GIMP 3.2 user manuals from Debian sid,
including all 32 declared languages and their matching common package. This
brings the complete family to 41 packages per architecture build. The pinned
help source versions and checksums live in `packages/gimp-3.2/help-assets`, so
updating them changes the recipe checksum. No sid APT configuration is added.
Clients can install `gimp-help-en` or another language from this repository.
Help outputs share the application's assigned package version; their original
Debian version is recorded in X-Upstream-Version. Missing declared languages,
changed dependencies, or mixed manual source versions fail the build.
`gimp-data-extras` remains supplied by Debian stable.

## Checksums and Debian revisions

Our input checksum answers whether the packaging recipe changed. It covers:

- Adapter file paths, contents, and executable permissions.
- The Dockerfile.
- The global `MAINTAINER` value.

It excludes revision helpers, inactivity settings, caches, generated `build/`
directories, timestamps, and architecture selection. Changes to included comments
also count as recipe changes.

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
| Latest artifact for this stream has the same recipe checksum | Reuse its revision; build incomplete architectures |
| Recipe changed, or existing artifacts have no matching metadata | Use the highest existing revision plus 1 |
| New upstream version | Start its revision at 1 |

No binary package is the source of truth for the revision. Revision allocation
inspects all declared binary package names across all streams for the upstream
version and uses their highest existing revision to avoid collisions. All outputs
of a build share the resulting version. A stream reuses its own latest matching
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
upstream release's publication timestamp to `WORKSPACE/release-date`, for example:

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
export FRAMEWORK_DIR="$PWD"
# In .env, set REPO_DATA_DIR to the absolute path of build/local.
./codex-repo-setup.sh
docker compose up -d --build
```

Setup updates `.env` for the chosen repository; use a separate checkout if you
also manage a production deployment from here.

From the project root, run every check with:

```sh
bash tests/run.sh
```

The master script runs the regression suite and then the signing/APT check.
For package-specific work, run that package's regression and installation tests.
Run the signing/APT check only when signing code changes or when intentionally
running the full suite; it is not part of a package-specific test run.
Both suites can also be run independently. Tests establish their own context and
temporary fixtures; you do not need to export `FRAMEWORK_DIR` or other settings.
The shell test entry points use the project-root working directory explicitly,
rather than searching for it or depending on production environment variables.

To run only the offline regression suite:

```sh
bash tests/run.sh --offline
```

It uses temporary directories under `build/`, fixture downloads, fake signatures,
and real Debian package/index tools. Host requirements are Bash, GNU tar, Python
3.10+, `dpkg-dev`, `apt-utils`, `jq`, and GnuPG.

Framework, setup, runner, and signing tests stay directly under `tests/`.
Adapter tests live in matching `tests/codex/`, `tests/ghostty/`,
`tests/gimp-3.2/`, and `tests/zed/` directories. To select just one adapter,
run `bash tests/run.sh gimp-3.2`; multiple adapter names are also accepted.
Use `bash tests/run.sh --framework` for framework/setup tests only. These
selected runs never invoke the real signing test or Docker installation tests.
Unknown selectors fail before tests start. The runner discovers each adapter
directory explicitly, so names such as `gimp-3.2` are not skipped by Python's
ordinary recursive unittest discovery.
Zed's tests require `patchelf` and `binutils`. GIMP's offline tests also
require `patchelf` and `squashfs-tools`; they use real SquashFS fixtures and inspect
both target architectures without executing their binaries. Their shared
temporary fixtures live in `tests/lib/publisher_test_support.py`; shared shell
coordination is in `tests/lib/common.sh`, separate from production `lib/`.
GIMP-specific fixtures stay in its test directory. The setup test uses fake sudo and GPG commands;
it does not change host users, production configuration, or signing keys.

The real signing/APT integration check is a standalone Bash script:

```sh
bash tests/test-signed-repo.sh
```

It creates a throwaway key and two fixture streams, verifies that APT accepts the
signed repository, and simulates selecting both versions. It redirects APT state
into the test directory and never installs packages on the host. GPG agent startup
requires permission to bind a local socket, even with a writable temporary homedir. Both checks clean up their test data.

Container image builds and live upstream publication remain deployment checks.

To validate real amd64 GIMP adapter outputs separately, run:

```sh
bash tests/gimp-3.2/test-install.sh /absolute/path/to/the/complete/amd64/output
```

Run this coordinator directly as your host user. Docker performs package
installation as root inside image layers; running the coordinator itself as
container root would create root-owned directories through a bind mount.
Its temporary directories intentionally use mode 700. Containers writing build
workspaces must use the host UID/GID.

To reuse an existing host-owned context and run only the replacement test:

```sh
GIMP_TEST_CONTEXT="$PWD/build/gimp-install-IoF2og" \
    bash tests/gimp-3.2/test-install.sh build/gimp-expanded-live/gimp/output/amd64 reinstall
```

Batch development commands with stdout/stderr redirected to log files, wait for
completion or a bounded timeout, then read the logs. Do not stream logs for
progress monitoring. Retain failure evidence and useful verified downloads;
reuse successful builds and remove obsolete temporary staging trees when no
open investigation requires them. Stored repository packages and keys are not
part of this temporary-data cleanup policy.

This optional Docker test checks clean APT installation, Debian GIMP removal
without purging followed by repack installation, configuration preservation,
system babl/GEGL coexistence, ELF relocation, and headless/Xvfb codec round trips.
It requires network access to Debian during setup and disables it during image
tests. Runner output is written to named logs with bounded timeouts; failed test contexts are retained
under `build/`. It neither installs host packages nor publishes a repository.
