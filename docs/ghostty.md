# Ghostty packaging, decisions, and operations

This document preserves the Ghostty addition, readability refactor, Bash version
conversion bug, metadata design decision, testing history, and deployment advice
from the original conversation. It was checked against the working tree on
2026-11-13. Current paths and commands below supersede the original flat adapter
layout and single-repository deployment advice.

Use [README](../README.md) for the complete hook contract and operator settings,
[ARCHITECTURE](../ARCHITECTURE.md) for publisher design, and
[AGENTS](../AGENTS.md) for development conventions. This is maintenance
documentation, not an instruction to deploy or change production storage.

## Outcome and source choice

The requested feature was to add Ghostty as a discoverable package adapter,
then refactor it to the repository's readability conventions. The resulting
stream publishes one binary package, `ghostty`, for amd64 and arm64.

The selected source is
[mkasberg/ghostty-ubuntu](https://github.com/mkasberg/ghostty-ubuntu), the community
Debian/Ubuntu package project referenced by
[Ghostty's binary installation documentation](https://ghostty.org/docs/install/binary).
These links record the source selection; this documentation pass did not perform
a fresh upstream release query or download. Version examples are examples, not
claims about the latest release today.

The adapter imports prebuilt Debian Trixie packages. It does not compile Ghostty,
run an upstream installer, or use Ubuntu, Forky, AppImage, or nightly artifacts.
The selected binaries and upstream maintainer scripts come from a community
packager, not an official Ghostty Linux binary distribution. Its integrity check
compares against the SHA256 digest in GitHub release metadata; it does not add an
independent signature verification step.

Ghostty belongs to the **repack** repository because its Debian metadata and
package bytes change. It is not a byte-preserving redistribution stream.
Changing the repository suite name does not change which upstream distro asset
is selected: the filename suffix remains `_trixie.deb`. Dependencies are inherited
from that package; do not infer compatibility with other distributions merely
because the repository can publish under another suite name.

## Current implementation map

| File | Responsibility |
| --- | --- |
| [config](../packages/repack/ghostty/config) | `RELEASE_STREAM=ghostty`, `BINARY_PACKAGES=ghostty`. |
| [query](../packages/repack/ghostty/query) | Choose the stable community release, convert versions, select exact Trixie assets, and write query results. |
| [build](../packages/repack/ghostty/build) | Verify a selected download, validate Debian identity and fixed paths, rewrite metadata, and create the output package. |
| [helper-inputs](../packages/repack/ghostty/helper-inputs) | Declare shared packaging and GitHub helpers as recipe checksum inputs. |
| [package.sh](../lib/adapter/package.sh) | Verified downloads, Debian field comparisons, installed size, and package construction. |
| [github.sh](../lib/adapter/github.sh) | Fetch stable GitHub metadata, validate exact assets, and record publication dates. |
| [rewrite-control.py](../lib/adapter/rewrite-control.py) | Preserve unrelated Debian fields while replacing publisher-owned metadata. |
| [Ghostty tests](../tests/ghostty/test_ghostty.py) | Offline release, import, metadata, size, architecture, and revision regressions. |

The hooks receive exported context, including `FRAMEWORK_DIR`, `ADAPTER_DIR`,
`WORKSPACE`, and `ARCHES`; build also requires the stream, checksum, and global
maintainer. They do not discover their directories from their own script paths.
The interface remains `query` and `build VERSION ARCH OUTPUT_DIR`. The framework
provides a fresh workspace per stream and an empty output directory per build.

### Release selection and version conversion

The query asks GitHub for
`https://api.github.com/repos/mkasberg/ghostty-ubuntu/releases/latest`.
Shared release validation requires `draft` and `prerelease` to be false and an
assets array containing objects. Ghostty then accepts tags matching:

```text
MAJOR.MINOR.PATCH-DEBIAN_REVISION-ppaNUMBER
```

The Bash regular expression captures the application version, numeric Debian
revision, and `ppa` identifier into named variables before constructing the
different representations:

| Purpose | Example |
| --- | --- |
| Community release tag | `1.3.1-0-ppa2` |
| Selected amd64 asset | `ghostty_1.3.1-0.ppa2_amd64_trixie.deb` |
| Expected upstream control Version | `1.3.1-0~ppa2` |
| Version written to targets | `1.3.1+0.ppa2` |
| First publisher output | `ghostty_1.3.1+0.ppa2-1_amd64.deb` |

Community rebuilds therefore trigger an update even if the Ghostty application
version stays the same: `ppa3` produces a different tracked upstream version.
The publisher owns the final numeric `-1`, `-2`, etc. Existing published version
identities are not renamed when the recipe changes.

For each requested architecture, the query matches exactly one expected asset
name. Missing assets produce a warning and no target row for that architecture.
Duplicate matches, invalid digests, invalid URLs, malformed release data, and
unexpected tag formats fail; the adapter does not guess a different layout or
fall back to another release. URLs must be HTTPS without whitespace and digests
must have `sha256:` followed by 64 hexadecimal characters.

Query outputs are `WORKSPACE/targets.tsv` with newline-terminated version/tab/arch
rows, and `WORKSPACE/assets.json`, indexed by architecture. Each asset entry has
`version`, `deb_version`, `name`, `url`, and `sha256`. The available publication
timestamp goes into `WORKSPACE/release-date`; this alone does not enable an
inactivity threshold. No `stale-after-days` file is currently supplied by Ghostty.

### Build and validation order

1. Read the selected architecture's asset record. Confirm its tracked version
   equals the assigned package version with the final publisher revision removed.
2. Download with the shared `refresh` policy and verify SHA256. Downloads use a
   `.part` destination and become the final download path only after verification.
   No architecture's Ghostty executable is run during packaging.
3. Compare upstream control fields exactly: Package must be `ghostty`, Version
   must match `deb_version`, and Architecture must match the requested architecture.
4. Extract with `dpkg-deb --raw-extract`. Require these fixed paths:

   ```text
   usr/bin/ghostty
   usr/share/applications/com.mitchellh.ghostty.desktop
   usr/share/terminfo/x/xterm-ghostty
   ```

5. Calculate `Installed-Size` from the final staged tree in KiB using GNU `du`,
   excluding `DEBIAN/`. Replace missing or stale upstream values; compressed
   download size is not installed size, and `dpkg-deb --build` does not generate it.
6. Rewrite control metadata and build with root ownership metadata and gzip
   compression. Return exactly `ghostty_VERSION_ARCH.deb` in `OUTPUT_DIR`.

The adapter preserves upstream payload resources, executable permissions,
dependencies, desktop integration, shell resources, and maintainer scripts.
Preserved maintainer scripts are not executed during extraction or repackaging;
APT/dpkg can execute them later when a client installs the package.

Fixed-path checks currently test file existence using `-f`. They are not a full
ELF ABI, executable-mode, or archive link/special-file audit. They also do not
prove the GUI launches on a target desktop. Do not describe this importer as
having Codex's separate tar/link validation policy.

## Why metadata rewriting instead of control.in

Ghostty already arrives as a Debian package with control metadata appropriate
to its binary. Copying today's fields into our own template would freeze its
dependency requirements and other upstream fields. A future binary could change
those requirements while a static template continued to publish old values.

The chosen import model preserves upstream metadata and replaces only:

```text
Version
Installed-Size
Maintainer
X-Build-Inputs-SHA256
X-Publisher-Stream
```

The shared Python helper reads fields line by line. Field matching is
case-insensitive. Replacing a field also removes its continuation lines, while
unrelated fields and their continuations are retained. It appends the replacement
fields and writes a newline-terminated control file. Maintainer punctuation such
as backslash, ampersand, slash, and pipe is written directly rather than passed
through a sed replacement expression.

The original helper was adapter-local and initially used a dense regular
expression. The readability refactor replaced that expression with explicit
line processing. A later shared-helper refactor moved the implementation to
`lib/adapter/rewrite-control.py`; there is no longer a Ghostty-local Python file.
Its current arguments are `CONTROL_FILE PACKAGE_VERSION INSTALLED_SIZE` with
optional additional field/value pairs. Ghostty supplies no extra pairs.

An external `control.in` remains appropriate when generating metadata from
scratch or deliberately taking ownership of a package's complete metadata.
Changing Ghostty to that model would require reviewing dependency changes rather
than merely substituting a different rendering tool.

## Original Bash substitution bug

The initial query tried to turn `0-ppa2` into `0~ppa2` using:

```bash
PACKAGE_REVISION=0-ppa2
DEBIAN_REVISION="${PACKAGE_REVISION/-/~}"
```

Bash expanded the unescaped replacement tilde to the home directory. In the
original environment, the result was `0/home/williamppa2`, so build validation
expected `1.3.1-0/home/williamppa2` instead of `1.3.1-0~ppa2`. The download digest
passed, but the Version check correctly rejected the package before storage.

Escaping the tilde (`${PACKAGE_REVISION/-/\~}`) fixed that initial implementation.
The subsequent readability refactor removed the substitution entirely. Today's
query constructs the value explicitly:

```bash
DEB_VERSION="$RELEASE_VERSION-$DEBIAN_REVISION~$COMMUNITY_REVISION"
```

This retains the intended tilde without depending on replacement-expression
escaping. The architecture-selection test asserts the exact upstream version.

## Revisions, storage, and failure behavior

Stored package metadata supplies recipe/revision history. Ghostty uses the normal
repack rules: unchanged recipes reuse their revision, missing architectures can
complete that revision, and recipe changes allocate the next revision for current
targets. New community versions start their own revision history. Old versions
and bytes remain available; historical application versions are not rebuilt just
because the recipe changes.

The recipe includes adapter paths, contents, executable bits, Dockerfile, global
MAINTAINER, and declared shared helpers. Ghostty declares
`adapter/package.sh`, `adapter/rewrite-control.py`, and `adapter/github.sh`.
Changing one of those helpers can trigger a Ghostty rebuild. Query-time upstream
digests are download integrity inputs, not automatically recipe checksum inputs.
These notes live outside `packages/` so documentation edits do not rebuild Ghostty.

The framework validates outputs and stores them under
`REPACK_REPO_DIR/pool/main/ghostty/`. It then generates and signs indexes for
stored packages. Missing current arm64 assets retain earlier arm64 packages;
failed streams do not block the remaining streams. Failed signing preserves
previous live indexes. Do not edit signed indexes or remove stored packages to
force an update. See [revision rules](../README.md#checksums-and-debian-revisions).

## Hosting and client installation today

For an existing, configured deployment, rebuild and recreate the repack service
from the project root. Batch output into named logs and inspect it after completion:

```bash
mkdir -p build/logs
docker compose up -d --build codex-repo-updater \
    > build/logs/ghostty-deploy.log 2>&1
docker compose logs --no-color --tail=200 codex-repo-updater \
    > build/logs/ghostty-publisher.log 2>&1
```

Read both files. Startup begins an update cycle immediately, but `up -d` returning
does not mean publication has finished. If needed, take another bounded log
snapshot later. Look for Ghostty's stored/already-stored messages and
`Published signed repository: CODENAME`. A final cycle failure can belong to
another stream, so inspect the specific errors and publication status too.

`docker compose up -d --build` without the service name also starts/recreates the
other configured services. A plain `docker compose restart` does not copy updated
adapter files into an image. The original conversation used the all-services
command when there was only one publisher; the targeted command above suits
today's grouped repository layout.

The repack service mounts `REPACK_REPO_DIR` at `/repo` and
`REPACK_GNUPG_DIR` at `/gnupg`, uses `REPACK_GPG_KEY`, and selects
`packages/repack/`. These settings and UID/GID must already be valid in `.env`.
Adding Ghostty to an existing repack deployment does not require generating new
keys or rerunning setup. Older deployments that have not adopted the repository
split should follow the current README/storage migration guide first; the old
single `REPO_DATA_DIR` and `GPG_KEY` instructions are historical.

The publisher does not serve HTTP. With the documented Caddy root `/srv/apt`,
Ghostty is served through the existing `/repack/` endpoint. Keep keys outside the
web root. Existing clients that already trust and use this repack repository run:

```bash
sudo apt update
apt-cache policy ghostty
sudo apt install ghostty
```

Check `apt-cache policy` to confirm the candidate and repository. New clients must
first install the verified repack public key and add the repack source as described
in [Debian client setup](../README.md#debian-client). No Ghostty-specific public
key or source list is required. For path, URL, and signing migrations use
[storage and signing](storage-and-signing.md), not the historical chat commands.

## Verification evidence and limits

The initial addition had four Ghostty fixture tests. During the readability
refactor, the package suite grew to nine tests and the then-current full offline
suite passed **70 tests in 60.248 seconds**. The real signing/APT integration,
Bash syntax checks, and `git diff --check` also passed. The signing check initially
could not start GPG's agent in the sandbox; rerunning with local socket permission
passed using a throwaway key and isolated APT state. It simulated fixture package
selection, not live Ghostty installation.

Those are historical results for that checkout, not a certification of all later
changes. The original logs used `build/ghostty-refactor-tests.log` and related
paths; those files are no longer present at this documentation check. The later
[shared-helper handoff](adapter-refactor-handoff.md) records separate verification
for the shared operations refactor. Do not substitute its results for a fresh
run after a future code change.

Current Ghostty fixtures use fake downloads with real Debian package tools. They
cover both architecture outputs, exact version conversion, requested-architecture
selection, release dates, missing-architecture completion, rejected tags and
prereleases, bad digests/URLs, wrong Package/Version/Architecture, each missing
required path, executable-mode preservation, maintainer-script preservation
without execution, multiline fields, special maintainer characters, field
replacement, repeat updates, community rebuilds, recipe revisions, retained bytes,
and installed size. Size tests cover absent and stale upstream metadata; the
normal import test also checks the published index value.

For a future Ghostty code change, run from the project root as the host user:

```bash
mkdir -p build/logs
timeout 30m bash tests/run.sh ghostty > build/logs/ghostty-tests.log 2>&1
bash -n packages/repack/ghostty/query packages/repack/ghostty/build \
    > build/logs/ghostty-syntax.log 2>&1
git diff --check > build/logs/ghostty-diff.log 2>&1
```

Wait for completion, check exit statuses, then read the logs. The runner also
creates its own `build/test-run-*/regression.log`. Keep failure evidence. Use the
explicit runner rather than ordinary recursive unittest discovery, which no
longer selects every adapter. Run signing tests when signing changes or when
intentionally running the complete suite; documentation changes alone do not
require package or signing tests.

No live Ghostty download/build, container deployment, production publication, or
desktop launch was performed in the original addition/refactor conversation.
There is no evidence in this chat that the operator subsequently deployed it.
Treat those as separate acceptance checks when requested, not as completed work.

## History and continuation

Relevant commits visible in the current repository history:

| Commit | Change |
| --- | --- |
| `fe889c7` | Initial Ghostty support. |
| `aae5e35` | Ghostty readability and coding-convention refactor. |
| `f70ebc3` | Installed-size calculation across packages. |
| `64e2f8f` | Test layout and explicit runner selection. |
| `40745dc` | Shared adapter operations and helper declarations. |
| `c1d5691` | Repository split; Ghostty moved under repack. |

The original creation attempt was blocked by a read-only workspace and interrupted
before any files were created. After workspace write access was available, the
adapter was added and tested. The later refactor was explicitly approved and
completed. These events do not leave an outstanding permission request or an
unfinished implementation task.

Future maintenance should begin with current source, `git status`, and repository
guidance. Keep source/version/layout policy in Ghostty and shared mechanics in
declared helpers. Do not replace the repack stream with redistribution, change
version identities, add source compilation, or choose another distro artifact as
an incidental refactor. Those require an explicit packaging decision.

At this documentation pass, the working tree already contained many staged and
unstaged documentation changes from other work. This handoff preserves them and
does not stage, commit, revert, publish, or deploy anything. The original Ghostty
addition and requested refactor are complete; live deployment remains an
operator action unless separately requested.
