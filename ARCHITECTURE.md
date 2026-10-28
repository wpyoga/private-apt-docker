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

`update.sh` holds a nonblocking kernel `flock` on `REPO_DIR/.state/update.lock`.
This protects against another container or a manual update using the same data.
The kernel releases the lock when its holders exit; the empty lock file may
remain. Its existence does not mean an update is running.

## Configuration and ownership

The operator-owned `.env` is central configuration. Setup sources it as trusted
shell-compatible assignments; Compose reads it and supplies runtime settings.
`.env.example` documents the settings without storing private configuration.
`MAINTAINER` is global package metadata. `REPO_NAME` supplies repository Origin
and Label. Setup creates or reuses the host account, storage, and signing key,
then writes UID, GID, and the key fingerprint back to `.env`.

The framework explicitly supplies its directories and stream context. Scripts
require missing or empty inputs to fail early rather than guessing paths.
Docker sets fixed container paths; direct host invocations supply their own.

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

`ARCHES` selects which architectures to process this cycle. Separately,
`REPO_ARCHITECTURES` selects which indexes to publish. This separation lets an
amd64-only update retain an arm64 index. Supported architectures are amd64 and
arm64. A build may also emit architecture-independent `all` packages. They are
stored once, satisfy completion checks for either architecture, and appear in
both architecture indexes. Every build returns the full set declared for its
architecture. A name may appear in both architecture lists; revision selection
scans their union, while completion checks and output validation use the selected
architecture's list. Query receives the union as `BINARY_PACKAGES`; build receives
its selected list. Existing common-list adapters keep their original behavior.

## The adapter boundary

The public interface is two executable hooks:

```text
query
build VERSION ARCH OUTPUT_DIR
```

Both receive exported `ADAPTER_DIR` and a fresh per-stream `WORKSPACE`, along with
the framework's other context. `query` receives no positional workspace argument.
`build` receives the final Debian version, architecture, and an existing empty
output directory. See the README's
[hook contract](README.md#query-and-build-hooks) for every environment variable.

The query chooses the latest eligible release for each requested architecture,
using that upstream's actual version rules. Semantic versioning is not assumed by
the framework. Query writes newline-terminated `VERSION<TAB>ARCH` rows to
`WORKSPACE/targets.tsv`, with at most one row per requested architecture. An empty
file means no eligible releases. Downloads, checksums, or other query results can
be shared with build in workspace files; `assets.json` is an adapter convention,
not a required framework schema.

When an architecture is unavailable, return only the available targets. The
framework warns, keeps existing packages, and retries discovery next cycle.
Network or malformed-metadata errors should fail rather than masquerading as an
empty release list. An adapter decides which release channel it follows; the
framework does not infer major/minor streams from package names.

Build may repack an archive, compile source, or import a `.deb`. It verifies
download integrity and expected metadata/layout before producing packages. Use
fixed expected paths for the stream. Unexpected changes are maintainer-visible
errors, not an invitation to guess another root or search for a replacement file.
Archive extraction tools supply path protections, but valid archive entries can
still violate an adapter's expectations. Link and file-type rules belong to the
adapter; explicitly handle anything it needs before later reads or permission
changes can follow unexpected links.

Write exactly one `NAME_VERSION_ARCH.deb` per declared binary package, with no
extra outputs. Include `X-Build-Inputs-SHA256` and `X-Publisher-Stream` in control
metadata. Every adapter must calculate `Installed-Size` in KiB from each final
staged package tree, excluding `DEBIAN/`, so APT can estimate disk usage. This
also applies to imported `.deb` files: replace upstream size metadata after
staging, even when upstream supplied a value. `dpkg-deb --build` does not generate
the field. The framework validates the entire output set before storing any of it.
If a resumed build regenerates an existing matching output, preserve the stored
bytes and install only missing packages. Each new file is installed completely
before it becomes visible, and an existing destination cannot be overwritten.
This is per-file publication, not a transaction across all outputs.

### Existing packaging examples

- **Laya** repackages the stable PyPI universal wheel into a Python library,
  CLI, and HTTP interface. It validates wheel metadata, dependencies, RECORD
  hashes, and fixed paths without executing upstream code. Click is pinned and
  bundled privately for its launchers; other dependencies come from Debian
  Trixie and selected Forky packages. [Laya packaging notes](docs/laya.md) explain
  client APT preferences, optional features, and verification limits.

- **Codex** queries GitHub's latest stable release with Bash and jq, verifies its
  archive digest, and expects `bin/` and `codex-package.json` at the archive root.
  It replaces bundled bubblewrap/ripgrep paths with wrappers for Debian tools and
  renders `control.in` with sed. Extraction checks live in its build script.
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
are excluded. Framework helpers and architecture selection are not fingerprinted.
Adapter comments and documentation count as inputs, so general developer docs
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

Packages live under `pool/main/STREAM/`. Publication scans all stored versions
with `dpkg-scanpackages --multiversion`, creates release metadata with
`apt-ftparchive`, and signs it with GPG. Generation and signing finish before live
indexes are changed, so signing failures leave previous live indexes intact.
Live metadata files are replaced individually; publication is not a single
atomic directory swap. Retained by-hash indexes let clients with an older signed
Release finish fetching its indexes during updates.

All stored versions and previous by-hash indexes are retained. There is no
automatic cleanup policy. Neither removing an adapter nor a missing upstream
release deletes its published packages. Serve only the repository directory,
never the keyring. The publisher itself runs no HTTP server.

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

Run tests from the project root. `bash tests/run.sh --offline` runs
offline regression tests using temporary repositories, fake downloads/signatures,
and real Debian tools. Package-specific tests mirror adapter directories under
`tests/`; publisher/setup/runner tests remain at the test root. Shared fixtures
and shell helpers live in `tests/lib/`, separate from production `lib/`.
Package-local helpers stay with their tests. Explicit per-directory discovery
includes names such as `gimp-3.2`, which ordinary recursive discovery skips.
`bash tests/run.sh gimp-3.2` selects that adapter's offline tests, while
`--framework` selects only framework/setup tests. Unknown selectors fail early.

`bash tests/test-signed-repo.sh` checks real signing and APT version selection
using a throwaway key and redirected APT state. It simulates installs rather than
installing host packages. `bash tests/run.sh` runs both suites. Tests establish
their own context and clean up temporary data. GPG may need permission to bind a
local socket. Run appropriate checks for the change; documentation-only edits do
not need builds or signing tests. Package selections never run real signing or
Docker tests implicitly; the GIMP installation coordinator is invoked explicitly
from `tests/gimp-3.2/test-install.sh` with existing built packages.

The shell helpers redirect command output to retained log files and enforce
timeouts. Logs are examined after completion instead of streamed for progress.
Test coordinators run as the host user, with matching UID/GID for containers
writing bind-mounted workspaces. Reuse useful downloads and validated packages;
remove obsolete temporary copies once no investigation needs them.

Temporary artifacts belong under ignored `build/`. Manual local repository data
uses `build/local/repo` and `build/local/gnupg`. Do not use production storage or
operator secrets for fixtures. Container builds and live upstream publication
are separate deployment verification; offline tests do not establish that a GUI
application works on a target desktop.

When resuming, inspect current files and working-tree changes first. This document
records decisions, not a frozen task queue. The GIMP 3.2 adapter continues the
native AppImage-repack investigation; its maintained design and deferred issues
are recorded in [docs/gimp-3.2.md](docs/gimp-3.2.md). Generated investigation
payloads and local dependency-root/native-root trees are not adapter inputs.
