# Private APT publisher

This container checks upstream releases, builds Debian packages, and publishes
one signed APT repository. It includes an unofficial repackaging of the official
OpenAI Codex executables as `codex-cli`, community Ghostty Debian packages as
`ghostty`, native GIMP 3.2 packages from the official AppImages, and the official
Zed editor binaries repackaged with Debian shared libraries as `zed`, and
[Laya's Python library, CLI, and HTTP server](docs/laya.md) as `python3-laya`,
`laya-cli`, and `laya-http`. Laya uses selected Debian Forky dependencies and
privately bundled Click; its client setup is documented separately.

The containers do not serve HTTP. Point an existing Caddy instance at `/srv/apt`
to serve the repack and rebuild repositories from separate URL subdirectories.

For development, read [AGENTS.md](AGENTS.md) for coding conventions and
[ARCHITECTURE.md](ARCHITECTURE.md) for the design rationale, adapter development
workflow, and guidance for resuming work in another session.

## How an update works

1. Take the repository lock so another updater cannot write at the same time.
2. Read adapter directories under the service’s selected package group, in alphabetical order.
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

The host needs Docker Compose, sudo, and the usual core utilities. Setup builds
the publisher image and runs GnuPG inside temporary containers.
From the project directory:

```sh
cp .env.example .env
chmod 600 .env
# Edit .env: set your MAINTAINER, REPO_NAME, key identity, and storage directory.
./codex-repo-setup.sh
docker compose up -d --build
docker compose logs -f
```

Setup reads exactly `$FRAMEWORK_DIR/.env`, validates its required inputs, creates
the configured system user and storage directories, and generates a dedicated
signing key if none exists. It writes `REPO_UID`, `REPO_GID`, `REPACK_GPG_KEY`, and `REBUILD_GPG_KEY` back to
that file with mode 0600, preserving other settings. It exports `repack-pubkey.asc`
and `rebuild-pubkey.asc` and prints their fingerprints. All key operations run in
temporary containers using the publisher UID/GID. Their agents stop when those
containers exit; setup leaves no host GPG agent running. Setup does not start the
publisher services.

You may import an existing dedicated key into the configured `gnupg/` directory
first. If it contains multiple primary secret keys, set the repository-specific fingerprint in `.env` to the
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
| `REPACK_REPO_DIR`, `REBUILD_REPO_DIR` | Public repository outputs under `/srv/apt` |
| `REPACK_GNUPG_DIR`, `REBUILD_GNUPG_DIR` | Private signing directories under `/var/lib/apt-publisher/gnupg` |
| `REPO_USER` | System user created or reused by setup |
| `GPG_KEY_NAME`, `GPG_KEY_TYPE`, `GPG_KEY_VALIDITY` | Explicit signing-key creation settings |
| `REPO_UID`, `REPO_GID`, `REPACK_GPG_KEY`, `REBUILD_GPG_KEY` | Setup outputs; supply existing values when upgrading |

Changing `MAINTAINER` rebuilds every package at the next packaging revision. Changing
`REPO_NAME` updates signed repository metadata without rebuilding package files.
Maintainer and repository identity values must be single-line strings.

Docker defines its fixed paths explicitly: `FRAMEWORK_DIR=/opt/apt-publisher`,
`PACKAGES_DIR=/opt/apt-publisher/packages/repack` (overridden for rebuild services), `REPO_DIR=/repo`, and `GNUPGHOME=/gnupg`.
Direct host invocations must export their own values for those paths and the
required settings. There are no path-discovery fallbacks.

Both amd64 and arm64 are supported. Selecting only amd64 for a cycle does not
remove arm64 packages when `REPO_ARCHITECTURES` still includes arm64. Missing or
empty required settings fail before repository files are written; Compose also
rejects missing settings before starting the container.

## One directory per configured release stream

Each immediate, non-hidden directory under `packages/repack/` or
`packages/rebuild/` contains one adapter. Its
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
without shell expansion. Declare `RELEASE_STREAM` and either `BINARY_PACKAGES`
or both architecture-specific lists, with each key appearing once:

```sh
RELEASE_STREAM=usbimager
BINARY_PACKAGES_AMD64=usbimager-gtk
BINARY_PACKAGES_ARM64=usbimager-x11
```

The two forms cannot be mixed. Both architecture lists must be nonempty, even
when a cycle selects just one architecture. A package name can occur in both
lists, including a shared `Architecture: all` package. Every build must return
exactly the names declared for its architecture. Revision allocation scans the
union of both lists, keeping one revision across architecture variants.
Package names form a space-separated list of distinct Debian package names.
Stream IDs use lowercase letters, digits, dots, underscores, and hyphens, beginning
with a letter or digit. They must be unique among adapters in a cycle; duplicate
IDs report an error and the later adapter is skipped.

One directory follows one configured release stream. The query hook owns how that
stream selects upstream releases; the stream ID is an identity, not a channel
name that the runner interprets. Codex follows GitHub's latest stable release and
supports amd64 and arm64. Its `query` hook declares its tag and asset rules and uses shared
GitHub helpers implemented with Bash and `jq`. Its build hook renders `@VARNAME@` placeholders in
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
scripts default FRAMEWORK_DIR to the current working directory and export it to
hooks. Run host commands from the project root; no manual export is required.
Docker sets it to `/opt/apt-publisher`. An explicit FRAMEWORK_DIR remains supported. The runner
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
| `BINARY_PACKAGES` | Query: union of configured names; build: names required for its architecture, separated by spaces |
| `BINARY_PACKAGES_AMD64`, `BINARY_PACKAGES_ARM64` | Architecture-specific lists, or empty for a common `BINARY_PACKAGES` declaration |
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
scripts. See `packages/repack/codex/` for the included adapter.

## Ghostty

`packages/repack/ghostty/` imports the latest stable release from
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

## USBImager

`packages/repack/usbimager/` imports the official GTK Debian package as `usbimager-gtk`
on amd64 and repackages the official X11 archive with embedded Unifont as
`usbimager-x11` on arm64. Both provide the virtual package `usbimager` and use
`/usr/bin/usbimager`. Arm64 compatibility is maintained as an exercise; there is
currently no arm64 consumer. See [packaging and verification notes](docs/usbimager.md)
for dependencies, device permissions, release selection, and validation limits.

## Zed

`packages/repack/zed/` follows the latest stable
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

`packages/repack/gimp-3.2/` selects the newest stable **3.2.x** release from GIMP's
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
[GIMP packaging and validation notes](docs/gimp-3.2.md). The adapter deliberately
fails on unexpected layouts, architectures, Debian baselines, or external SONAMEs.
Adding a newer release series requires a separate adapter.

## GIMP help 3.2

`packages/repack/gimp-help-3.2/` independently imports the GIMP 3.2 user manuals from
Debian sid. It selects a consistent release of all 32 declared language packages
and their common package. Clients do not need sid configured and can install
`gimp-help-en` or another language from this repository.

All manuals are architecture-independent and appear in both supported indexes.
Manual source updates and packaging changes rebuild this stream independently
of the application. Versions such as `1:3.2.0+deb3-1` retain the Debian source
revision and use an epoch to upgrade earlier application-numbered manuals.
API documentation remains in the application stream; `gimp-data-extras` remains
supplied by Debian stable.

See [GIMP help packaging and validation notes](docs/gimp-help-3.2.md) for release
selection, package validation, and verification limits.

## Thorium

The two Thorium release streams, `thorium-browser` and `thorium-browser-gz83`,
each repackage official Debian binaries into distinct SSE3, SSE4, AVX, and AVX2
packages. Alex313031 stable releases use names such as
`thorium-browser-avx2`; collaborator gz83 releases, including beta builds, use
names such as `thorium-browser-gz83-avx2`. On amd64, `thorium-browser` and
`thorium-browser-gz83` select their family's AVX package. On arm64,
`thorium-browser-gz83` contains the native browser.
Each amd64 build emits all four CPU tiers and its default metapackage at the
same version/revision, selecting the newest upstream release with a complete
asset set. An incomplete upstream release leaves the existing packages available.

Variants have separate installation paths, commands, and desktop entries, and
share Thorium's normal profile unless users supply `--user-data-dir`. Normal
Chromium instance locking still applies. Moving a shared profile from a newer
browser back to an older one may not work.

After rebuilding the publisher image and publishing an update cycle, install a
specific variant with `sudo apt install thorium-browser-avx2`, for example.
AVX/AVX2 require compatible CPUs; APT does not select a CPU tier automatically.
gz83's AppArmor profile is relocated for each variant, and the upstream setuid
sandbox helper is preserved. Verification is currently static; installation,
browser launch, and desktop behavior have not been verified.
See [Thorium packaging and investigation notes](docs/thorium.md) for all names,
upstream inventories, integrity checks, integration behavior, and limitations.
Compose allows 512 MiB of memory for upstream XZ imports; Alex's packages alone
require a 256 MiB decoder dictionary. Both Thorium adapters stream the
payload through `ar` and XZ’s single-threaded decoder with a 384 MiB decoder
limit during validation and extraction; dpkg’s one-worker setting alone still
uses its threaded decoder API. After updating this checkout, rebuild
and recreate the publisher with `docker compose up -d --build --force-recreate`
to apply both the adapter and memory-limit changes.

## Cromite

`packages/repack/cromite/` repackages the latest stable official Linux amd64 archive
from [uazo/cromite](https://github.com/uazo/cromite). It verifies GitHub's SHA256,
checks the fixed payload and Debian 13 ELF baseline, preserves bundled runtime
libraries, and removes `.pak.info` build metadata. Linux arm64 is unavailable.

Install with `sudo apt install cromite` after rebuilding the publisher image and
publishing an update cycle. The package supplies command-line and desktop
launchers and relies on the unprivileged user-namespace sandbox. Validation is
currently static and offline; browser launch and desktop behavior are unverified.
See [Cromite packaging and verification notes](docs/cromite.md) for release
versions, dependencies, licensing, inspection measurements and limitations.

## Checksums and Debian revisions

Our input checksum answers whether the packaging recipe changed. It covers:

- Adapter file paths, contents, and executable permissions.
- Shared implementation files listed in the adapter’s `helper-inputs`.
- The Dockerfile.
- The global `MAINTAINER` value.

Other framework files remain excluded, along with inactivity settings, caches,
generated `build/` directories, timestamps, and architecture selection. Changes to included comments
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
signed release while new indexes are being published. Back up both complete
repository outputs and the signing keys separately.

The default host layout separates public repositories from private signing keys:

```text
/srv/apt/                         # Caddy document root
├── repack/                       # pool/, dists/, and repository state
└── rebuild/                      # pool/, dists/, and repository state

/var/lib/apt-publisher/gnupg/
├── repack/                       # private keyring, mode 0700
└── rebuild/                      # private keyring, mode 0700
```

Each service mounts its output at `/repo` and its keyring at `/gnupg` inside the
container. Host paths are configured independently in `.env`.

For Caddy, replace the Tailnet IP with your server's address:

```caddyfile
http://100.101.102.103:8080 {
    bind 100.101.102.103
    root * /srv/apt
    file_server
}
```

This serves both repositories on one IP and port, at `/repack/` and `/rebuild/`.
Caddy needs read access to both outputs and traversal access through their parents.
The publisher uses umask 022. Keep both keyrings outside the web root and owned by
the publisher account with mode 0700. Never grant Caddy access to them.

Each container stores GPG agent sockets in its own tmpfs under `/run/user/UID`,
separate from the persistent `/gnupg` mount. Startup fails if GnuPG would put its
sockets in the signing directory instead. The two rebuild containers share keys
but have separate agents; stopping a container stops its agent. Setup uses the
same socket isolation in temporary containers and never invokes host GPG.

When upgrading from host-based setup, stop publishers and shut down the old host
agents once, using the current signing paths:

```sh
docker compose stop
sudo -u aptrepo gpgconf --homedir /var/lib/apt-publisher/gnupg/repack --kill gpg-agent
sudo -u aptrepo gpgconf --homedir /var/lib/apt-publisher/gnupg/rebuild --kill gpg-agent
docker compose up -d --build --force-recreate
```

Replace `aptrepo` with your configured `REPO_USER` and adjust custom keyring paths.
Keep the existing keys and fingerprints; setup does not need to be rerun.

### Moving existing storage

Existing paths remain supported; setup does not move data automatically. Before
changing Caddy to serve `/srv/apt`, move any signing directories out of that tree:

1. Stop all publishers with `docker compose stop`, and stop any manual update jobs.
   Keep Caddy stopped during the move if it already serves `/srv/apt`.
2. Back up both complete repository outputs and both keyrings. Record the current
   signing fingerprints from `.env`.
3. Move each existing keyring to its new path under
   `/var/lib/apt-publisher/gnupg/`, preserving ownership and permissions. Keep each
   keyring directory at mode 0700. Do not leave keyring copies or backups under
   `/srv/apt`.
4. Move the complete repository outputs, including hidden files, to
   `/srv/apt/repack` and `/srv/apt/rebuild`. For the old
   `/srv/apt/repack/repo` layout, move the contents of `repo/` into its parent;
   do the same for rebuild. Preserve all packages, indexes, by-hash files, and
   `.state/`. Check for destination conflicts before moving anything.
5. Update all four directory settings in `.env` to the new paths. Keep
   `REPACK_GPG_KEY`, `REBUILD_GPG_KEY`, `REPO_UID`, and `REPO_GID` unchanged.
   Do not run setup to generate replacement keys.
6. Verify that `/srv/apt` contains only repository data, then update Caddy's root
   and reload it. Recreate publishers with `docker compose up -d --force-recreate`
   so their bind mounts use the new paths.
7. If the repository URL changed, update client source lists to use `/repack/`
   or `/rebuild/` and run `sudo apt update`. Existing trusted public keys remain
   valid because the signing identities have not changed.

## Debian client

Transfer `repack-pubkey.asc` securely and verify its fingerprint out of band:

```sh
sudo install -d -m 0755 /etc/apt/keyrings
sudo install -m 0644 repack-pubkey.asc /etc/apt/keyrings/private-repo.asc
printf '%s\n' \
    'deb [signed-by=/etc/apt/keyrings/private-repo.asc] http://100.101.102.103:8080/repack/ trixie main' \
    | sudo tee /etc/apt/sources.list.d/private-repo.list
sudo apt update
sudo apt install codex-cli
```

For rebuild packages, install `rebuild-pubkey.asc` into a separate keyring and
add a source entry using that keyring and `http://100.101.102.103:8080/rebuild/`.

Existing deployments may keep their original key and source-list filenames.
For same-name streams, select a particular published version using
`apt install PACKAGE=VERSION`; configure APT preferences to stay within a stream.
Using Debian's package name permits replacement, but APT version, priority, and
dependency rules still determine which package is chosen.

## Local testing

Generated files belong under ignored `build/`. Manual local repository data uses
`build/local/repo` and `build/local/gnupg`:

```sh
# In .env, point both output and GnuPG directory pairs under build/local.
./codex-repo-setup.sh
docker compose up -d --build
```

Setup updates the shared `.env`. Use separate output paths and signing storage
for local testing so production data is never used.

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

For tools used only by this checkout, see
[project-local Debian tools](docs/local-tools.md). They can be extracted under
ignored `build/tools/` and enabled for individual commands without sudo or Docker.

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
both target architectures without executing their binaries. GIMP download tests
use real curl against a loopback server and need permission to open local sockets;
they do not contact the internet. Their shared
temporary fixtures live in `tests/lib/publisher_test_support.py`; shared shell
coordination is in `tests/lib/common.sh`, separate from production `lib/`.
GIMP-specific fixtures stay in its test directory. The setup test uses fake sudo and Docker commands;
it does not change host users, production configuration, or signing keys.

The real signing/APT integration check is a standalone Bash script:

```sh
bash tests/test-signed-repo.sh
```

It creates a throwaway key and two fixture streams, verifies that APT accepts the
signed repository, and simulates selecting both versions. It redirects APT state
into the test directory and never installs packages on the host. GPG agent startup
requires permission to bind a local socket, even with a writable temporary homedir. Both checks clean up their test data.

To verify GPG agent isolation with real containers, run:

```sh
bash tests/test-container-gpg.sh
```

This builds the publisher image, generates a throwaway key inside a temporary
container, and starts two publishers sharing that keyring. It checks real signing,
private sockets, independent agent lifetimes, and agent exit when containers stop.
Run it as the host user with Docker access. Logs and isolated test data remain
under `build/container-gpg-*`; production storage and keys are never used.

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

## Repository groups and deployment

Adapters live under `packages/repack/` and `packages/rebuild/`. Their parent
selects repository membership; config files do not contain a repository key.
One checkout, `.env`, and Compose project run three services: the existing
`codex-repo-updater` for repacks, plus `rebuild-amd64` and `rebuild-arm64`.
Both rebuild services share one output and signing identity; the existing lock
serializes their cycles. Each builds one architecture and indexes both.

Set `REPACK_REPO_DIR` and `REBUILD_REPO_DIR` to distinct absolute output
directories, defaulting to `/srv/apt/repack` and `/srv/apt/rebuild`.
`REPACK_GNUPG_DIR` and `REBUILD_GNUPG_DIR` default to
`/var/lib/apt-publisher/gnupg/repack` and `/var/lib/apt-publisher/gnupg/rebuild`.
This keeps both signing keys outside the shared `/srv/apt` web root. Setup prepares
both outputs with mode 0755 and each signing directory with mode 0700.
The repack identity remains REPO_NAME; the rebuild Origin and Label are `rebuild`.
Remove the obsolete REPOSITORY setting from .env. No data migration or cleanup
is automatic. Serve the two outputs at separate web endpoints.

Start all three services with `docker compose up -d --build`. Compose must
support `build.additional_contexts` with service contexts. The rebuild Dockerfile
uses the publisher service image as its base. Source builds currently require
an amd64 server; rootless-daemon ownership mapping remains unverified.

Grouping changes the shared Dockerfile, so current package targets receive a
one-time recipe revision. Later xfce4-terminal patch edits remain local to its
adapter. Existing stored artifacts are never deleted.

See [xfce4-terminal deployment and patches](docs/xfce4-terminal.md).

Signing configuration uses separate `REPACK_GNUPG_DIR` and `REBUILD_GNUPG_DIR`
and separate `REPACK_GPG_KEY` and `REBUILD_GPG_KEY` fingerprints in the one .env.
Setup generates or selects keys independently, exports `repack-pubkey.asc` and
`rebuild-pubkey.asc`, and never copies or synchronizes keyrings. Both rebuild
containers mount only the rebuild keyring; repack mounts only its own.
Existing deployments can keep their current paths when the web root excludes
both keyrings. To adopt the shared `/srv/apt` web root, follow the
[storage migration instructions](#moving-existing-storage) before serving it.
Keep existing signing fingerprints when moving keyrings.
Remove obsolete REPO_DATA_DIR and GPG_KEY settings after configuring these fields.
Never serve either signing directory over HTTP.
