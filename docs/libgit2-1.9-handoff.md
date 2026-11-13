# libgit2 1.9 packaging conversation handoff

Recorded on **2026-11-13** so the packaging conversation can be deleted. The
implementation and real build results below date from **2026-11-01**. This
handoff was checked against the current adapter, tests, retained packages,
downloaded source archives, and completed logs. No new upstream query, package
build, installation, signing, or deployment was performed while writing it.

The implementation is committed as `c305f98` (`feat: add libgit2-1.9`). Read
[the maintained libgit2 notes](libgit2-1.9.md),
[ARCHITECTURE.md](../ARCHITECTURE.md), [README.md](../README.md), and
[AGENTS.md](../AGENTS.md) for the current contract. Other staged or modified
documentation found during this handoff belonged to other work and was left
intact.

## Request, decisions, and result

The request was to package the latest libgit2 1.9 in the private repository.
The implemented release stream is `libgit2-1.9`, under `packages/rebuild/`.
It rebuilds Debian's source against Debian 13 Trixie dependencies rather than
importing sid binaries or building the upstream development branch directly.
This preserves Debian's package split, dependencies, symbols, licensing, and
normal versus experimental library integration while using the newer source.

The signed Debian sid source index selected `1.9.7+ds-1` during the original
run. Both Docker builds produced publisher version `1.9.7+ds-1+local-1`.
This is the source verified on November 1, not a claim that it remains the
latest release whenever this document is read.

The maintainer asked whether Docker would be used. The agreed and completed
approach used the project's Debian rebuild toolchain images on an amd64 host:
native amd64 compilation and arm64 cross-compilation. Containers writing build
workspaces ran with the host UID/GID. Root dependency installation and native
package installation tests happened in Docker image layers, not on the host.

The later question about development packages was answered by the actual
complete output set:

| Package | Architecture | Contents |
| --- | --- | --- |
| `libgit2-1.9` | amd64 and arm64 | Normal shared library, SONAME `libgit2.so.1.9` |
| `libgit2-dev` | amd64 and arm64 | Normal headers, static library, linker symlink, CMake and pkg-config metadata |
| `libgit2-experimental1.9` | amd64 and arm64 | Shared library with experimental SHA-256 support, SONAME `libgit2-experimental.so.1.9` |
| `libgit2-experimental-dev` | amd64 and arm64 | Experimental development files and compatibility links |
| `libgit2-fixtures` | all | Upstream test resources installed as documentation examples |

Each local architecture build emitted five files, including a copy of the
`Architecture: all` fixtures package. Together these represent nine distinct
Package/Version/Architecture identities. The publisher retains an already
stored fixtures package when completing the second architecture. Independently
built fixtures archives were not claimed to be byte-identical.

Automatic debug-symbol packages were disabled; there was no separate `-dbgsym`
output. Builds were binary-only and unsigned (`--build=binary -us -uc`), not new
Debian source uploads. The downloaded Debian source descriptor and archives
were retained separately.

The local builds and tests **did not publish to the live signed repository**.
At the original publication check, `REBUILD_GPG_KEY` was empty in local operator
configuration. UID/GID settings existed but did not supply a signing identity.
That is a historical observation, not a fresh audit of today's configuration.
Operator values and private signing material are not copied into this handoff.

## Source repositories and the cloning questions

Debian's packaging repository is:

```text
https://salsa.debian.org/debian/libgit2.git
```

The maintainer cloned it at `temp/libgit2-debian`. The inspected checkout used
`debian/sid`, contained changelog entry `1.9.7+ds-1`, and had tip `845f530c1`
(`Update changelog for 1.9.7+ds-1 release`). The existing upstream checkout at
`temp/libgit2` described itself as `v2.0.0-rc.1-2-g42a89d7cc`. Its development
branch was not used to build these 1.9 packages.

No other Git repository was needed. Neither local checkout is a build input;
the adapter obtains Debian's source descriptor and archives through APT.
`temp/diffofdiffs` and the other pre-existing temporary directory were unrelated
to this package's build. The current Docker context excludes `temp/` and
`build/`.

If a fresh reference checkout is needed, keep it under ignored `build/`:

```bash
mkdir -p build/libgit2-reference
git clone https://salsa.debian.org/debian/libgit2.git build/libgit2-reference/debian
```

Early direct host curl requests for GitHub release metadata and Debian's pool
listing failed with DNS resolution errors. Their failed logs remain. Later
source selection and downloads succeeded through APT inside Docker. The cloned
repositories therefore did not remove the network requirement for current
indexes, source downloads, or image dependencies. The subsequent download
requests were not requests to clone another Git repository.

## Implementation map

All adapter paths below are relative to `packages/rebuild/libgit2-1.9/`.

| File | Responsibility |
| --- | --- |
| [config](../packages/rebuild/libgit2-1.9/config) | Declare stream identity and the five binary output names |
| [sources.list](../packages/rebuild/libgit2-1.9/sources.list) | Select Debian sid source indexes |
| [query](../packages/rebuild/libgit2-1.9/query) | Refresh isolated APT lists, inspect versions, download the chosen source, and prepare targets |
| [source-metadata.py](../packages/rebuild/libgit2-1.9/source-metadata.py) | Validate metadata, compare Debian versions, verify the descriptor, and write workspace metadata |
| [prepare-source.py](../packages/rebuild/libgit2-1.9/prepare-source.py) | Adapt the known debhelper 14 control file to Trixie's compat 13 |
| [build](../packages/rebuild/libgit2-1.9/build) | Extract, adapt, compile, validate, stage, and rebuild all declared packages |
| [install-build-dependencies](../packages/rebuild/libgit2-1.9/install-build-dependencies) | Install architecture-specific development dependencies in Docker image layers |
| [helper-inputs](../packages/rebuild/libgit2-1.9/helper-inputs) | Include shared packaging/control helpers in the recipe checksum |

The root [Dockerfile](../Dockerfile) installs libgit2 dependencies in
`rebuild-tools`, after the terminal and screensaver installers and before
copying publisher files into the final `rebuild` image. It exports
`LIBGIT2_BUILD_ARCH=$TARGET_ARCH`. Dependency declaration changes invalidate
the corresponding image layers; adapter edits can reuse dependency layers.
See [Docker cache details](docker-build-cache.md).

There is no new central registry, revision counter, or checksum sidecar.
Directory discovery selects the adapter and its parent assigns repository
membership. The existing publisher handles revisions, locking, complete-output
validation, storage, signing, publication, and retaining previous versions.

## Release selection, integrity, and versioning

The source configuration contains
`deb-src https://deb.debian.org/debian sid main`. Query uses workspace-local APT
lists and disables other source-list parts for its source query. It writes
`apt-cache showsrc --only-source libgit2` output to `WORKSPACE/sources`.

Selection and download proceed as follows:

1. Read `Package: libgit2` source paragraphs. Reject duplicate fields or a missing
   Version field, and validate version syntax with `dpkg --validate-version`.
2. Accept the fixed pattern `1\.9\.\d+\+ds-\d+(?:\+\w+)?` and choose the greatest
   matching version with `dpkg --compare-versions`.
3. Download exactly `libgit2=SOURCE_VERSION` using `apt-get source --download-only`.
4. Require exactly one `libgit2_*.dsc` in `WORKSPACE/source`, with exactly the
   selected Version and `Source: libgit2`.
5. Emit a `SOURCE_VERSION+local` target for each requested architecture.

The pattern excludes prereleases, other minor series, and 2.x. It is narrower
than every legal Debian version spelling: epochs, numbered `+ds` repacks, and
dotted Debian revisions do not currently match. A future source naming change
needs a deliberate selector update and tests. There is no automatic alternative
source-root or archive-layout search.

If no matching 1.9 release remains in sid, query returns an empty target set
without removing stored packages. Network/APT errors fail the query instead of
being interpreted as an absent release. Descriptor mismatches fail explicitly.
There is no `stale-after-days` file or release-date activity monitoring for this
adapter, and no automatic stream retirement or migration to 2.x.

APT authenticates repository indexes and checks source downloads against their
indexed hashes. The original `dpkg-source` logs also warn that the descriptor's
inline signature could not be independently verified with an available signer
key. The download used the authenticated APT index chain; this work does not
claim separate verification of the maintainer's individual descriptor signature.

The verified version mapping was:

```text
Debian source:       1.9.7+ds-1
Query target:        1.9.7+ds-1+local
Published-form .deb: 1.9.7+ds-1+local-1
```

The final `-1` is the publisher revision. Production allocation derives it from
stored packages and embedded metadata. Current targets rebuild when recipes
change, complete existing revisions after partial success, and preserve older
packages. A fixed `-1` in a disposable manual verification helper does not replace
that production revision allocation. All five packages share a version.

## Debian recipe adaptation and package validation

Build validates `amd64` or `arm64`, selects `x86_64-linux-gnu` or
`aarch64-linux-gnu`, and rejects a mismatch with `LIBGIT2_BUILD_ARCH` before
compiling. It also checks that the requested binary version belongs to the
source version selected in the shared workspace.

`dpkg-source -x` applies Debian's existing patches. For the verified source the
series contains `disable-online-tests.patch` and
`disable-flaky-stat-tests.patch`. No local libgit2 C implementation patch was
added. Debian's rules, symbols, licensing, and package integration remain the
packaging foundation.

The compatibility adjustment is specific: Debian's current control file uses
`debhelper-compat (= 14)` while the Trixie environment uses compat 13.
`prepare-source.py` requires exactly that declaration, changes it to 13, and
requires the known five binary package paragraphs. Compat 14 supplies dependency
substitutions automatically. The adaptation restores `${misc:Depends}` in every
binary package and `${shlibs:Depends}` in the two runtime libraries, retaining
the development packages' exact runtime-version dependencies.

Changed compat versions, unknown or duplicate package names, missing packages,
or newly explicit dependency substitutions fail for review. This avoids
silently applying the same transformation to an incompatible future recipe.

`dch` records the publisher version for Trixie with the configured global
`MAINTAINER`. Build uses:

```text
DEB_BUILD_OPTIONS="nocheck parallel=2 noautodbgsym"
DEB_BUILD_PROFILES="cross nocheck"
dpkg-buildpackage --build=binary --host-arch ARCHITECTURE -us -uc
```

`nocheck` disables the upstream suite for native and cross builds alike.
`parallel=2` bounds compilation jobs. `noautodbgsym` suppresses extra debug
packages, preserving the declared output set. Debian's rules build normal
static/shared and experimental static/shared configurations. The verified
options select OpenSSL HTTPS, SSH, GSSAPI, PCRE2, llhttp, and the system CA bundle
at `/etc/ssl/certs/ca-certificates.crt`; CLI creation and NTLMCLIENT are disabled.
Debian enables its reproducibility and hardening options, but independent
byte-for-byte reproducibility was not established by this work.

Each resulting .deb is checked for the expected Package, Version, and
Architecture, then raw-extracted with its Debian metadata. Fixed required paths
are checked before final packaging:

| Package | Required path relative to its root |
| --- | --- |
| `libgit2-1.9` | `usr/lib/MULTIARCH/libgit2.so.1.9` |
| `libgit2-dev` | `usr/include/git2.h` |
| `libgit2-experimental1.9` | `usr/lib/MULTIARCH/libgit2-experimental.so.1.9` |
| `libgit2-experimental-dev` | `usr/include/git2-experimental.h` |
| `libgit2-fixtures` | `usr/share/doc/libgit2-fixtures/examples` |

Installed-Size is recalculated in KiB from the final staged tree excluding
`DEBIAN/`. The shared control helper rewrites Version, Maintainer, Installed-Size,
`X-Build-Inputs-SHA256`, and `X-Publisher-Stream`, retaining other fields.
Final archives use gzip compression and root ownership inside the archive;
host output files remain owned by the invoking user. The framework validates
the complete declared set before storing any files.

## Build and runtime dependencies

The image installer declares build-essential, the arm64 cross toolchain,
debhelper, devscripts, CMake, and pkgconf. Target-architecture development
dependencies are libkrb5-dev, libllhttp-dev, libpcre2-dev, libssh2-1-dev,
libssl-dev, and zlib1g-dev. They come from the Trixie image's binary sources.
The sid source query does not enable sid binary dependencies in the image.

The saved normal and experimental runtime packages have the following Depends
on both architectures:

```text
libc6 (>= 2.38)
libgssapi-krb5-2 (>= 1.17)
libllhttp9.2 (>= 7.3.0+dfsg1+~cs24.12.11)
libpcre2-8-0 (>= 10.22)
libssh2-1t64 (>= 1.7.0)
libssl3t64 (>= 3.0.0)
zlib1g (>= 1:1.1.4)
```

These are measured dependencies for the historical builds, not a permanent
replacement for `dpkg-shlibdeps`. Both development variants also depend on
libllhttp-dev, libpcre2-dev, libssh2-1-dev, libssl-dev, and zlib1g-dev, plus their
own matching runtime at exactly `1.9.7+ds-1+local-1`.

Debian deliberately separates normal and experimental libraries. The
experimental variant enables the SHA-256 API and uses a separate library
filename and symbol-version map. Its development package supplies compatibility
links for normal header and linker/pkg-config paths, so the two development
packages conflict. Choose one development variant. The two runtime libraries
have separate filenames.

Other streams can request this provider through the optional private
`build-dependencies` contract, for example `libgit2-1.9 libgit2-dev >= 1.9.1`.
That framework feature was added after this original packaging work. See
[private build dependencies](build-dependencies.md) for selection and the host
worker path. It installs requested packages and their APT dependencies without
installing both conflicting development variants. Check an actual consumer's
feature or bug-fix requirement before raising its dependency version floor.

## Retained packages, sources, and cleanup

Paths in this section are relative to the project root and are ignored local
data, not served production storage:

```text
build/libgit2-1.9/
  amd64/output/                       five final .deb files
  arm64/output/                       five final .deb files
  amd64/source/                       descriptor and source archives
  arm64/source/                       descriptor and source archives
  amd64/Packages                      unsigned inspection index
  arm64/Packages                      unsigned inspection index
  logs/                               named checks and failure evidence
```

Filenames are `PACKAGE_1.9.7+ds-1+local-1_ARCH.deb`, with `all` for fixtures.
For example, the native development archive is
`build/libgit2-1.9/amd64/output/libgit2-dev_1.9.7+ds-1+local-1_amd64.deb`.
Each architecture directory also retains `.buildinfo`, `.changes`, source
selection files, and APT query data. Downloaded source files include:

```text
libgit2_1.9.7+ds-1.dsc
libgit2_1.9.7+ds.orig.tar.xz
libgit2_1.9.7+ds-1.debian.tar.xz
```

The `.buildinfo` and `.changes` describe the initial Debian build before the
publisher rewrites control metadata and recompresses the final archives. Their
original package hashes are not manifests for the rewritten files in `output/`.

Measured Installed-Size values, also checked in generated Packages indexes:

| Package | amd64 KiB | arm64 KiB |
| --- | ---: | ---: |
| `libgit2-1.9` | 1376 | 1464 |
| `libgit2-dev` | 4020 | 4300 |
| `libgit2-experimental1.9` | 1384 | 1464 |
| `libgit2-experimental-dev` | 3708 | 3988 |
| `libgit2-fixtures` | 54064 | 54064 |

After successful verification, temporary source/build trees (`build-amd64` and
`build-arm64`), staging trees, and redundant pre-rewrite .deb files were removed.
Final packages, useful source downloads, build records, and failure logs remain.
No stored repository packages or signing keys were removed.

Ignored helpers `run-build.sh`, `build-amd64.sh`, and `build-arm64.sh` record the
original manual commands. They source operator configuration for MAINTAINER and
run Docker with the host UID/GID. They are investigation helpers rather than
maintained publisher entry points. `check-artifacts.py` is pinned to 1.9.7 and
requires the staged trees that have since been removed. It cannot simply be
rerun against the cleaned directories: re-extract packages into a fresh temporary
tree for new inspection, or consult the completed inspection logs.

## Completed verification and evidence

All evidence paths below are relative to the project root. The per-build logs
are under `build/libgit2-1.9/logs/` unless a fuller path is shown.

| Check | Recorded result | Evidence |
| --- | --- | --- |
| Adapter tests | 9 passed | `build/test-run-tYSO0J/regression.log`; coordinator `offline-expanded.log` |
| Framework tests | 65 passed | `build/test-run-KV4p2R/regression.log`; coordinator `framework.log` |
| amd64 images | Initial toolchain build and final adapter refresh passed | `image-amd64.log`, `image-amd64-final.log` |
| arm64 toolchain image | Passed on the amd64 host | `image-arm64.log` |
| Real source compilation | All five outputs for each architecture | `build-amd64.log`, `build-arm64.log` |
| amd64 artifact inspection | Metadata, sizes/index, exact dev dependencies, ELF machine/SONAME and ownership passed | `artifacts-amd64-retry.log` |
| arm64 artifact inspection | Same checks, verifying AArch64 | `artifacts-arm64.log` |
| Native installation/smoke | Both variants installed, linked and ran | `build/libgit2-install-Bb0GNP/install.log`; coordinator `install-test.log` |
| Syntax and whitespace | Passed | `syntax-final.log`, `install-syntax.log`, `diff-check-final.log` |
| Local documentation links | Passed in original work | `doc-links.log` |
| Temporary-data cleanup | Completed; architecture outputs shared one recipe checksum | `cleanup.log` |

The 74-test total is historical: 9 adapter tests plus 65 framework tests. It
does not mean the full repository suite ran or that today's framework suite
still has exactly 65 tests. The signing test was not run for this adapter-only
change. Tests did not use production data or keys.

[test_source.py](../tests/libgit2-1.9/test_source.py) covers latest matching
selection, invalid source metadata, descriptor consistency, compat/dependency
adaptation, sizes/indexes, repeat-update reuse and completion of the second
architecture, no matching release, a wrong toolchain architecture, absent
upstream size, and missing-library failure without storing partial output.
Those offline tests stub upstream compilation; the separate Docker builds
provide the real compilation evidence.

[test-install.sh](../tests/libgit2-1.9/test-install.sh) runs as the host user,
copies exactly one amd64 archive for each of the four architecture-specific
packages, and builds a Trixie test image. Root package installation occurs only
in its image layers. It installs normal runtime/development packages first,
then replaces the development package with the experimental variant. It does
not install the fixtures package.

For each variant, [smoke.c](../tests/libgit2-1.9/smoke.c) includes `git2.h`, links
with `pkg-config --cflags --libs libgit2`, initializes the library, reports its
version, checks major/minor 1.9, creates a bare repository, and releases the
library. Both runs printed `libgit2 1.9.7` and exited successfully. This does not
establish network transport/authentication behavior, full upstream-suite
correctness, static linking, CMake consumer integration, or arm64 runtime
correctness.

### Resolved failures and nonfatal warnings

The first offline run failed because the parent of the per-package staging
directory was not created before `dpkg-deb --raw-extract`. Build now explicitly
creates `WORKSPACE/staged-ARCHITECTURE`. Failure evidence remains in
`build/test-run-ZxYFGP/regression.log` and coordinator `offline.log`. The first
retry passed seven tests; the expanded final suite passed nine.

The initial amd64 artifact-inspection helper used `stat()` for ownership and
followed a development linker symlink into a runtime file provided by a different
package. That target can correctly be absent inside an isolated development
staging tree. The helper was corrected to use `lstat()` for link ownership;
the package payload did not change for this issue. Keep `artifacts-amd64.log`
as failure evidence and use `artifacts-amd64-retry.log` for the completed result.

Other original warnings included a non-root APT cleanup hook being unable to
remove a root-owned cache glob, missing optional distro-info metadata for dch,
the descriptor signature warning discussed above, an initial arm64 compiler
system-type warning, and arm64 libc loader diversion warnings from
`dpkg-shlibdeps`. Both builds completed. Actual cross compilation used
`aarch64-linux-gnu-gcc`; final ELF checks verified AArch64 and dependencies were
inspected. Those observations do not replace arm64 runtime testing.

### Maintainer correction: wait, then inspect logs

The maintainer explicitly corrected the original monitoring workflow. Redirect
stdout and stderr to named files, wait until the command exits or its bounded
timeout finishes, then inspect the saved log. Do not monitor build progress
with Docker status queries, repeated log tails, `docker logs -f`, or real-time
output streaming. Learn completion from the launched command's exit status.
Preserve failed logs and use new names for retries.

Earlier Docker-status snapshots under the saved log directory are historical
artifacts, not examples to follow. The assistant acknowledged that those queries
and reads before process exit did not follow the repository instructions.

## Repeating checks and making fresh local builds

Run maintained checks from the project root, retaining the outer logs and the
runner's own detailed logs:

```bash
mkdir -p build/libgit2-checks
timeout --kill-after=30s 10m bash tests/run.sh libgit2-1.9 \
    > build/libgit2-checks/adapter.log 2>&1
timeout --kill-after=30s 10m bash tests/run.sh --framework \
    > build/libgit2-checks/framework.log 2>&1
```

Wait for completion before reading those files. Reuse successful saved packages
for the maintained installation test while they remain useful:

```bash
timeout --kill-after=30s 20m bash tests/libgit2-1.9/test-install.sh \
    build/libgit2-1.9/amd64/output \
    > build/libgit2-checks/install.log 2>&1
```

The coordinator requires the host user, Docker, and Debian network access. It
retains a `build/libgit2-install-XXXXXX` context and `install.log`. It neither
publishes packages nor uses repository signing keys.

For a fresh source-build check, the following runs one target in a new workspace
without replacing saved outputs. Run from the project root as the host user
with Docker access. Change `ARCHITECTURE=amd64` to `arm64` for the second run on
the amd64 host. `TARGET_ARCH` selects dependencies and compiler; it does not
request a native arm64 Docker image or require target execution through emulation.

```bash
(
    set -Eeuo pipefail
    source .env
    export MAINTAINER

    ARCHITECTURE=amd64
    mkdir -p build
    WORKSPACE=$(mktemp -d "$PWD/build/libgit2-manual-$ARCHITECTURE-XXXXXX")
    IMAGE="private-apt-libgit2-$ARCHITECTURE:local"

    timeout --kill-after=30s 30m docker build --target rebuild \
        --build-arg "TARGET_ARCH=$ARCHITECTURE" -t "$IMAGE" . \
        > "$WORKSPACE/image.log" 2>&1

    timeout --kill-after=30s 30m docker run --rm --init \
        --user "$(id -u):$(id -g)" --volume "$WORKSPACE:/workspace" \
        --env MAINTAINER --env WORKSPACE=/workspace \
        --env "ARCHES=$ARCHITECTURE" --env PUBLISHER_STREAM=libgit2-1.9 \
        --env ADAPTER_DIR=/opt/apt-publisher/packages/rebuild/libgit2-1.9 \
        --entrypoint /bin/bash "$IMAGE" -Eeuo pipefail -c '
            export BUILD_INPUTS_SHA256
            BUILD_INPUTS_SHA256=$(python3 "$FRAMEWORK_DIR/lib/checksum.py")
            bash "$ADAPTER_DIR/query"
            SOURCE_VERSION=$(cat "$WORKSPACE/source-version")
            : "${SOURCE_VERSION:?No eligible libgit2 1.9 source is available}"
            mkdir -p "$WORKSPACE/output"
            bash "$ADAPTER_DIR/build" "$SOURCE_VERSION+local-1" \
                "$ARCHES" "$WORKSPACE/output"
        ' > "$WORKSPACE/build.log" 2>&1

    printf 'Completed local verification workspace: %s\n' "$WORKSPACE"
)
```

The fixed final `-1` is only for a fresh disposable verification workspace.
Use the normal publisher revision allocator for repository updates. Do not use
this example to replace stored artifacts. New queries select whatever eligible
source Debian currently offers. Reproducing exactly 1.9.7 needs the retained
verified source archives and an appropriate toolchain; sid may no longer offer
that exact version. These reproduction examples were reviewed as documentation,
not executed again during the handoff.

## Deployment and remaining work

Signed publication remains the operational step from the original work, after
checking current configuration and the intended signing key. The local validation
images were tagged `private-apt-libgit2-amd64:local`,
`private-apt-libgit2-arm64:local`, and
`private-apt-libgit2-install-test:local`. These tags do not themselves update
Compose service images or publish an APT repository.

For the ordinary Compose path, supply all required existing repository and
signing settings, then rebuild and recreate the rebuild services:

```bash
mkdir -p build/libgit2-deployment
timeout --kill-after=30s 30m docker compose build rebuild-amd64 rebuild-arm64 \
    > build/libgit2-deployment/images.log 2>&1
docker compose up -d --force-recreate rebuild-amd64 rebuild-arm64 \
    > build/libgit2-deployment/start.log 2>&1
```

These are operator deployment commands, not actions performed by this handoff.
Compose also validates required settings for the other configured services.
The README owns complete setup, public-key transfer, storage, and client source
configuration. Keep existing data and signing identities; rebuilding adapter
code alone does not require rerunning setup.

If consumers use the newer private build-dependency feature, follow
[the host launcher instructions](build-dependencies.md#running-isolated-builds)
instead of running competing ordinary rebuild services. Both paths retain the
repository lock. This handoff does not establish that either path has been
deployed on the production host.

Normal storage places packages under
`REBUILD_REPO_DIR/pool/main/libgit2-1.9/`. The publisher signs and publishes
indexes after processing its streams. The saved local `Packages` files are
unsigned inspection outputs, not a substitute for signed publication.

After publication, with the rebuild repository and its trusted public key
configured on the client:

```bash
sudo apt update
sudo apt install libgit2-1.9
# Development against the normal library:
sudo apt install libgit2-dev
# Or select experimental development support instead:
sudo apt install libgit2-experimental-dev
```

Remaining limits are arm64 runtime execution, broader upstream and network
transport/authentication testing, consumers beyond the smoke program, and live
signed publication. Before further changes, inspect the current working tree,
adapter, and stored artifacts. The saved evidence and this handoff replace the
deleted chat; they do not justify rebuilding successful outputs without a new
reason.
