# Architecture and design decisions

This document explains how the publisher fits together and why it is designed
this way. [AGENTS.md](AGENTS.md) contains development conventions;
[README.md](README.md) contains operator instructions and the full hook contract.

## Purpose and philosophy

The publisher checks upstream releases, turns selected artifacts into Debian
packages, and writes a signed APT repository. A separate web server serves the
result. Each upstream can have its own query and packaging method.

Simplicity means a maintainer can read a script from top to bottom and explain
what it does. Target an average high-school student's code comprehension. Favor
clear steps and short functions. Neither reducing line count nor eliminating all
duplication is a goal. Split code when it has distinct responsibilities; combine
small helpers when a separate file only adds navigation and argument plumbing.

Use shell for commands and file handling, jq for straightforward JSON, and Python
where its data structures or date handling make the logic easier to follow. The
language choice follows the job. A new adapter does not need to use every tool or
justify a new general framework.

## The update cycle

```text
entrypoint.sh
  update.sh                         one complete cycle, holding the lock
    for each adapter directory:
      config.sh                     validate stream identity and package names
      update-package.sh             isolate this stream in a fresh Bash process
        query                       upstream discovery owned by the adapter
        checksum.py                 fingerprint packaging inputs
        resolve-builds.py           validate targets, select revisions/builds
        check-activity.py           optional inactivity warning
        for each missing target:
          build                     packaging owned by the adapter
          store-packages.sh         validate outputs, install new artifacts
    publish.sh                      generate, sign, and publish indexes
  wait CHECK_INTERVAL
  repeat
```

The first cycle starts immediately. Processing is sequential: finish one stream
before moving to the next, including its architecture builds. Publication runs
after the stream loop even when a stream failed. The cycle returns a failure
status if any stream or publication failed, while retaining successful artifacts.

The wait starts after the entire cycle finishes. With a six-hour interval, an
08:00 start and twenty-minute cycle produce a 14:20 next start. This is not a
fixed wall-clock schedule. No parallel worker pool or scheduler is needed.

`update.sh` holds a blocking kernel `flock` on `REPO_DIR/.state/update.lock`.
This protects against another container or a manual update using the same data.
Another updater waits for the lock, then runs its complete cycle even if the
previous updater failed. The kernel releases the lock when its holders exit;
the empty lock file may remain. Its existence does not mean an update is running.

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

## Configuration and ownership

The operator-owned `.env` is central configuration. Setup sources it as trusted
shell-compatible assignments; Compose reads it and supplies runtime settings.
`.env.example` documents the settings without storing private configuration.
`MAINTAINER` is global package metadata. `REPO_NAME` supplies repository Origin
and Label. Setup creates or reuses the host account, storage, and signing key,
then writes UID, GID, and the key fingerprint back to `.env`.

Setup builds the publisher image directly, before Compose can require the generated
UID/GID and fingerprints. It runs every GPG operation in a temporary container as
the publisher UID/GID; it never invokes host GPG or leaves a host agent running.
Setup containers use `--rm` and `--init`, and their agents die when they exit.

Each publisher and setup container mounts a private tmpfs at `/run/user/UID`.
`lib/gnupg.sh` creates GnuPG's socket directory there and rejects fallback to the
persistent keyring. The entrypoint starts its own agent before the update loop.
This lets both rebuild containers share stored keys without connecting to each
other's agent or a host agent through a bind-mounted socket. Agent lifetime is
bounded by the container lifetime. Stored keys and signing fingerprints are
unchanged by this isolation.

The framework explicitly supplies its directories and stream context. Scripts
require missing or empty inputs to fail early rather than guessing paths.
Docker sets fixed container paths. Host entry points default FRAMEWORK_DIR to
the current directory and export it; invoke them from the project root. Internal
hooks still require exported context.

Adapter `config` files are different: they are parsed as data and never sourced.
They declare `RELEASE_STREAM` and either a common `BINARY_PACKAGES` list or
both `BINARY_PACKAGES_AMD64` and `BINARY_PACKAGES_ARM64`. The directory listing
selects adapters, while the configured stream ID supplies persistent identity.
Renaming a directory therefore does not rename the stream or reset its history.

Each directory follows one stream. A future upstream 3.4 stream can have its own
directory, dependencies, and installation method alongside a 3.2 stream. Both
may publish a Debian package named `gimp`; unique Debian names are not required.
APT version ordering and client preferences decide which version is installed.
The publisher does not implement stream migration.

Build architecture selection is separate from index architecture selection, so
an amd64-only update can retain an arm64 index. Architecture-independent packages
are stored once and indexed for both. Revision selection considers all declared
names, while completion and output checks use the selected architecture's names.
See [central configuration](README.md#central-configuration) and the
[adapter configuration format](README.md#one-directory-per-configured-release-stream)
for the settings and list forms.

## The adapter boundary

Adapters own upstream release selection, integrity checks, dependencies, and
packaging. The publisher owns revision selection, output validation, storage,
and publication. This boundary supports repacking archives, compiling source,
and importing `.deb` files without imposing one upstream layout or version scheme.

Query and build share a fresh per-stream workspace. Workspace metadata such as
`assets.json` is an adapter convention, not a framework schema. Queries select
current releases for their stream; packaging changes do not select historical
versions for rebuilding. Missing architectures retain their stored packages and
are retried next cycle, while network or malformed-metadata errors fail clearly.

Adapters validate fixed expected paths and metadata. A changed layout needs a
maintainer's decision rather than an automatic search for replacement files.
Archive extraction protections alone do not establish that files and links are
safe for the adapter's later reads or permission changes; those rules belong
with the upstream-specific validation.

The complete [query and build contract](README.md#query-and-build-hooks) defines
arguments, environment, target rows, package metadata, and output validation.
The [shared adapter operations](README.md#shared-adapter-operations) provide common
mechanics while leaving upstream policy inside adapters.

### Shared adapter operations

Shared helpers implement publisher mechanics such as downloads, control rendering,
and package creation. Adapters explicitly declare helper dependencies so changes
to used helpers affect their recipe checksum without rebuilding unrelated streams.
The API and `helper-inputs` format are documented with the
[hook contract](README.md#shared-adapter-operations).

### Existing packaging examples

- **Thorium** imports official Debian binaries through two streams:
  `thorium-browser` follows Alex313031 stable, and `thorium-browser-gz83` follows
  gz83 (including beta). Each emits SSE3, SSE4, AVX, and AVX2 packages plus an
  AVX-default metapackage on amd64; the gz83 stream emits its native browser on
  arm64. Query selects the newest complete CPU asset set per architecture, and
  each output set shares a version and revision. Concrete packages have private paths and desktop IDs,
  while profiles remain shared. Setuid sandbox modes and per-variant AppArmor
  integration are preserved. Release selection scans paginated assets because
  GitHub's latest release can be an announcement without binaries. Adapter-local
  implementation copies keep upstream assumptions out of publisher helpers and
  inside each stream's recipe checksum. [Thorium notes](docs/thorium.md) record
  the verified artifacts and pending installation/runtime checks.

- **Laya** repackages the stable PyPI universal wheel into a Python library,
  CLI, and HTTP interface. It validates wheel metadata, dependencies, RECORD
  hashes, and fixed paths without executing upstream code. Click is pinned and
  bundled privately for its launchers; other dependencies come from Debian
  Trixie and selected Forky packages. [Laya packaging notes](docs/laya.md) explain
  client APT preferences, optional features, and verification limits.

- **Codex** queries GitHub's latest stable release with Bash and jq, verifies its
  archive digest, and expects `bin/` and `codex-package.json` at the archive root.
  It replaces bundled bubblewrap/ripgrep paths with wrappers for Debian tools and
  renders `control.in` with sed. Extraction checks live in its build script:
  GNU tar handles extraction paths;
  adapter checks reject special files and external links before later reads or
  permission changes, and validate the metadata version and entrypoint.
- **Ghostty** imports community Debian Trixie packages from
  `mkasberg/ghostty-ubuntu`. It checks the digest, package identity, and fixed
  executable/desktop/terminfo paths. It preserves dependencies, resources, and
  maintainer scripts while rewriting publisher-owned fields. The Python control
  helper handles multiline Debian fields. Upstream scripts are not executed
  during repackaging; preserved scripts can run when clients install the package.
  Community rebuild identifiers are included in the tracked upstream version.

- **GIMP 3.2** selects the latest stable 3.2.x AppImages from GIMP's release
  metadata, verifies SHA256, and extracts SquashFS without executing upstream
  code. Fixed GIMP-owned paths and upstream HTML API documentation become eight
  native packages, including developer tools, headers, and documentation. babl/GEGL remain
  private; known external SONAMEs map to explicit Debian dependencies. This map
  checks new upstream requirements without relying on installed host packages.
  Architecture checks, link/file-type validation and native ELF patching work
  for amd64 and arm64 without target execution. General notes and the deferred
  TIFF-thumbnail issue live in [docs/gimp-3.2.md](docs/gimp-3.2.md).

- **GIMP help 3.2** independently imports all declared language packages and
  their common package from Debian sid's package index. It selects a consistent
  3.2 release, verifies SHA256 and fixed payload layout, preserves licensing,
  removes the known legacy migration scripts, and recalculates Installed-Size.
  Versions use an epoch to upgrade manuals formerly numbered after GIMP, retain
  Debian source revisions as upstream version components, and append the normal
  publisher revision. Its recipe checksum is independent of the application.
  [GIMP help packaging notes](docs/gimp-help-3.2.md) describe selection and validation.

- **Cromite** repackages official stable amd64 Linux tarballs, retaining upstream
  graphics libraries and Qt shims while using Debian's external dependencies.
  It removes locale resource-build annotations and replaces the development
  wrapper with packaged desktop/CLI integration. Static ELF checks enforce the
  Debian 13 baseline. [Cromite packaging notes](docs/cromite.md) record version
  ordering, sandbox assumptions and the requested static-only validation limit.

- **Zed** selects official stable GitHub tarballs and verifies their SHA256.
  It preserves the relative CLI/editor layout but replaces all bundled shared
  libraries with Debian dependencies. ELF inspection validates architectures,
  known SONAMEs, and the Trixie symbol baseline without target execution.
  A wrapper disables the built-in updater for terminal and desktop launches.
  [Zed packaging notes](docs/zed.md) record the bundled libXdmcp/libbsd dependency
  difference and the desktop compatibility checks still needed on the laptop.

These examples illustrate different methods. Document the actual source and
compatibility requirements of a community package rather than presenting it as
an official binary.

## Checksums and revision history

Stored packages supply the history. There is no revision database, reservation
file, or checksum sidecar. Reading `.deb` control metadata does not require
decompressing its main payload.

`lib/checksum.py` fingerprints sorted adapter-relative file paths, file contents,
executable permission bits, the Dockerfile text, and global `MAINTAINER`. Directory
names, timestamps, caches, generated `build/` directories, and `stale-after-days`
are excluded. Declared shared adapter helpers are fingerprinted; other framework
helpers and architecture selection are not. Adapter comments and documentation count as inputs, so general developer docs
belong outside `packages/`.

The recipe checksum is distinct from upstream download hashes. Query results and
remote asset digests are not currently recipe inputs. The Dockerfile text cannot
detect changed dependencies or base images that resolve from unchanged text.
Changing the checksum algorithm itself can cause packaging revisions; treat that
as a behavior change rather than incidental formatting.

For each queried upstream version, inspect all declared binary package names
across streams to find the highest existing numeric Debian revision. With no
existing packages, start at `-1`. If this stream's latest artifact has the same
checksum, reuse its revision and fill missing outputs or architectures. Otherwise
use the highest existing revision plus one. All declared outputs for that
upstream version share the selected revision.

A second stream's higher revision does not prevent reuse of this stream's own
matching revision. A completely failed build leaves no artifact and retries the
same next revision. Partial success supplies the metadata needed to resume.
Reverting a recipe still needs a new revision because its checksum differs from
the stream's latest artifact. New upstream versions have separate revision
histories. Packaging changes affect current query targets, not older releases.

Global maintainer changes trigger current package rebuilds. Repository name or
description changes only update repository metadata. Do not reintroduce
`revision-env` or a configurable revision policy for these existing rules.

## Publication, storage, and failures

Packages live under `pool/main/STREAM/`. The framework validates a build's entire
output set before storing any files. Each new package becomes visible only when
complete, and existing destinations cannot be overwritten. Resumed builds retain
stored bytes and install only missing packages. Storage is atomic per file, not a
transaction across the output set.

Publication scans all stored versions with `dpkg-scanpackages --multiversion`,
creates release metadata with
`apt-ftparchive`, and signs it with GPG. Generation and signing finish before live
indexes are changed, so signing failures leave previous live indexes intact.
Live metadata files are replaced individually; publication is not a single
atomic directory swap. Retained by-hash indexes let clients with an older signed
Release finish fetching its indexes during updates.

All stored versions and previous by-hash indexes are retained. There is no
automatic cleanup policy. Neither removing an adapter nor a missing upstream
release deletes its published packages. Serve only the repository directory,
never the keyring. The publisher itself runs no HTTP server.

Successful cycles remove their temporary workspace. Failed cycles retain theirs
and log its path, including when querying, building, or publication fails. While
holding the repository lock, a new failure removes the previous failed workspace
for the same user, repository path, adapter root, and architecture selection.
This bounds temporary failure evidence to one cycle per builder without deleting
stored packages. A successful retry leaves that evidence available. Temporary
workspaces live in the system temporary directory and do not survive container
replacement unless copied out; they are separate from served repository data.

Optional per-stream `stale-after-days` sets a positive inactivity threshold.
Query supplies a timezone-aware timestamp in `WORKSPACE/release-date`. Old
releases produce a warning every cycle; missing or invalid monitoring data also
warns without blocking publication. Changing packaging does not reset upstream
release age. There is no universal release cadence, automatic retirement, or
external alert delivery. Logs are the notification mechanism.

## Adding or changing an adapter

1. Read the hook contract and the closest existing adapter. Verify current
   upstream documentation and release artifacts; do not assume GitHub, semantic
   versions, or the same packaging method as Codex.
2. Define one stream and the Debian output names. Decide which upstream releases
   qualify, how upstream rebuilds map into Debian version ordering, and how
   amd64/arm64 map to artifact names. Existing Debian names may be reused.
3. Choose the packaging method based on available artifacts and the target
   clients. Establish dependencies, desktop/command integration, and fixed
   required paths/metadata. Check that the publisher can build both architectures
   without accidentally executing binaries for the other architecture.
4. Implement query, integrity checks, and build using the established context.
   Keep upstream assumptions local and make changed layouts fail clearly.
   Preserve necessary upstream integration when importing packages. Use an
   external control template when generating metadata from scratch.
5. Add offline fixtures and tests for selection, missing architectures, invalid
   metadata/digests, unexpected layouts, final package contents/dependencies, and
   repeat updates. Check `Installed-Size` in the package and published index;
   importers must handle missing or stale upstream values. Exercise revision
   reuse or rebuilds where behavior changes.
6. Document the source, stream policy, packaging method, compatibility limits,
   and client installation name. Rebuild the container as a separate deployment
   step: adapters are copied into the image, not loaded live from the checkout.

Use the directory listing rather than adding a registry entry. Avoid changing the
framework just to accommodate one upstream when its adapter can handle the job.
New build dependencies in the Dockerfile affect every stream's checksum.

## Testing and resuming work

Offline tests exercise publisher behavior with temporary repositories, fixture
downloads, fake signatures, and real Debian tools. Separate integration checks
exercise real signing/APT and container agent isolation. Offline validation does
not establish that a GUI application works on a target desktop; container builds
and live publication are separate deployment checks.

Adapter tests mirror their directories under `tests/`. Explicit per-directory
discovery includes names such as `gimp-3.2`, which ordinary recursive discovery
skips. Shared test fixtures and shell coordination live in `tests/lib/`, separate
from production `lib/`; adapter-specific fixtures stay with their tests.

See [local testing](README.md#local-testing) for commands, prerequisites, isolated
storage, and installation checks. [AGENTS.md](AGENTS.md#verification) defines the
verification workflow and handling of temporary data.

When resuming, inspect current files and working-tree changes first. This document
records decisions, not a frozen task queue. Maintained adapter investigations and
limitations belong in their linked packaging notes, outside recipe inputs.

## Repository groups and deployment

The parent directory, `packages/repack/` or `packages/rebuild/`, selects repository
membership. Keeping this out of adapter config avoids a second source of truth.
Repack and rebuild have separate outputs and signing identities. The two rebuild
services share their repository and keyring, using the repository lock to serialize
cycles and private container agents to isolate GPG sockets.

The Dockerfile shares a `tools` stage between the default `publisher` target and
the architecture-specific `rebuild` target. Rebuild dependencies are installed
before copying the framework and adapters, so adapter edits reuse dependency
layers. The dependency declarations in
`packages/rebuild/xfce4-terminal/install-build-dependencies` and
`packages/rebuild/xfce4-screensaver/install-build-dependencies` affect both build
architectures. Dockerfile changes affect every stream's recipe checksum; later
adapter-only patch edits remain local to that adapter.

`packages/rebuild/libgit2-1.9/install-build-dependencies` adds the target CMake
library dependencies for libgit2. That adapter selects Debian sid's latest
stable 1.9 source and rebuilds against Trixie, preserving Debian's normal and
experimental library packages. Its explicit debhelper 14-to-13 adaptation
restores automatic dependency substitutions. See [libgit2 notes](docs/libgit2-1.9.md).

See [repository groups and deployment](README.md#repository-groups-and-deployment)
for services, settings, host requirements, signing identities, and deployment
commands, and [storage migration](README.md#moving-existing-storage) for existing
data. [xfce4-terminal notes](docs/xfce4-terminal.md) describe its patches and
source-build requirements.
