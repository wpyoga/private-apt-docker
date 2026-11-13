# USBImager implementation and verification handoff

This document preserves the USBImager conversation's engineering decisions and
evidence so the conversation can be deleted. The implementation and original
verification were completed on October 28, 2026. The current source paths and
retained evidence were inspected for this documentation on November 13, 2026.
The latter inspection is documentation verification, not a new upstream release
check, package build, deployment, or runtime test.

Use [USBImager packaging](usbimager.md) for the concise adapter description,
[local Debian tools](local-tools.md) for host tool setup, the
[README](../README.md) for the current hook and deployment contracts, and
[ARCHITECTURE.md](../ARCHITECTURE.md) for publisher design. Later repository-wide
changes take precedence over historical commands and paths recorded below.

## Requirements and decisions

The requested source was [USBImager's official website](https://bztsrc.gitlab.io/usbimager/),
backed by [bztsrc/usbimager on GitLab](https://gitlab.com/bztsrc/usbimager).
The goal was to add an adapter for official precompiled binaries, with the
publisher's normal verification, revision, and repository behavior.

The operator chose these identities and interfaces explicitly:

| Concept | Decision |
| --- | --- |
| Persistent stream ID | `usbimager` |
| Adapter directory name | `usbimager`; currently `packages/repack/usbimager/` |
| amd64 binary package | `usbimager-gtk` |
| arm64 binary package | `usbimager-x11` |
| Application command | `/usr/bin/usbimager` on either architecture |
| Interface features | Full read/write interface, including backups; not write-only |
| arm64 status | Compatibility exercise; no current arm64 consumer |
| Source compilation | Not required for either architecture |

GTK and X11 are different upstream interface builds. In this context, X11 means
the minimal interface built directly against X11, without GTK. Upstream's
published artifacts inspected during the work included an amd64 GTK Debian
package, an x86_64 GTK ZIP, and aarch64 X11 ZIPs. No official prebuilt arm64 GTK
package was found in that listing or checksum manifest. The Raspberry Pi GTK
`.deb` was `armhf`, which is 32-bit ARM and does not satisfy an arm64 target.
This finding concerns published artifacts, not whether the GTK source can be
compiled for arm64. No arm64 GTK source build was attempted.

Using the same Debian name on both architectures would have been technically
possible. The operator deliberately requested distinct names for the different
configurations. The original proposal to use X11 everywhere was superseded by
GTK on amd64 and the best available upstream build, X11, on arm64. The arm64
choice uses the `_uf` variant with embedded Unifont to avoid reliance on external
X11 Unicode fonts; it retains the complete interface.

Both packages provide the virtual name `usbimager`. They declare conflicts with
the upstream `usbimager` package and with each other because their executable,
desktop entry, icons, and manual occupy the same paths. They are alternatives,
not packages designed for simultaneous installation.

## Why the official Debian package is repacked

The official amd64 archive inspected during the work declared:

```text
Package: usbimager
Version: 1.0.10
Architecture: amd64
Maintainer: bzt
Depends: udisks2
Installed-Size: 404
```

The application binary and existing integration files can be preserved. The
archive still needs repacking to implement the requested `usbimager-gtk` name,
publisher-assigned version/revision, configured maintainer, embedded recipe
checksum and stream, recalculated size, and dependency/conflict/provision fields.
The original size is not trusted after staging changes.

The arm64 input is a ZIP rather than a Debian archive, so it needs new Debian
control metadata around the staged payload. Both variants therefore belong to
the current **repack** repository. The later byte-preserving **redistribute**
mode does not describe this adapter: it cannot preserve the original amd64
archive bytes while also renaming its package and rewriting metadata, and the
arm64 input has no Debian control archive to preserve.

## Framework support for different names by architecture

The original framework required every declared binary package for every queried
architecture. The following data-only declaration was added to express the
requested difference:

```text
RELEASE_STREAM=usbimager
BINARY_PACKAGES_AMD64=usbimager-gtk
BINARY_PACKAGES_ARM64=usbimager-x11
```

Existing adapters can continue to declare one common `BINARY_PACKAGES` list.
The common and architecture-specific forms cannot be mixed. Both architecture
lists must be nonempty even for a cycle that selects only one architecture.
Each list must contain valid distinct Debian names. A name can occur in both
lists, including a shared `Architecture: all` output.

The current responsibilities are:

| Component | Architecture-specific behavior |
| --- | --- |
| `lib/config.sh` | Validate the list form and build a deduplicated union of names |
| `update.sh` | Export the union and separate architecture lists for each stream |
| `lib/resolve-builds.py` | Scan the union for revision history; check completion using the target architecture's list |
| `lib/update-package.sh` | Pass the selected list as `BINARY_PACKAGES` to build and output storage validation |
| `lib/store-packages.sh` | Require exactly the selected output set and validate metadata before storing any file |

Query receives the union as `BINARY_PACKAGES`. Build receives its architecture's
selected list. `BINARY_PACKAGES_AMD64` and `BINARY_PACKAGES_ARM64` expose the
configured lists; they are empty for a common-list adapter. See the current
README for the complete environment contract.

All outputs for the same upstream version share the publisher-selected revision.
Scanning the union is important even when only amd64 is requested: an existing
arm64 variant can determine the revision. A matching stream/recipe checksum
reuses its revision and fills missing outputs or architectures. Existing matching
artifacts retain their original bytes. Shared `all` outputs are stored once.
No revision counter, reservation file, or checksum sidecar was introduced for
this repack stream. General stream isolation, sequential processing, locking,
retention, publication, and inactivity rules remain framework responsibilities.

## Current adapter implementation

The implementation began at `packages/usbimager/`. Subsequent repository work
moved it to `packages/repack/usbimager/` and replaced adapter-local packaging
mechanics with shared helpers. The stream identity remains `usbimager`.
Relevant commits visible during the handoff inspection are `dcef81a` (original
adapter), `40745dc` (shared packaging helpers), and `c1d5691` (repository split).
Use Git history and current files to review those changes; the old build artifacts
do not establish verification of every subsequent refactor.

| Current file | Responsibility |
| --- | --- |
| `config` | Stream identity and architecture-specific names |
| `query` | Download the official SHA256 manifest |
| `select-assets.py` | Parse the manifest, choose the latest numbered release, write target/asset files |
| `build` | Validate the selection, verify input bytes, stage each variant, prepare metadata and build `.deb` output |
| `validate.py` | Debian/ZIP path and type checks, fixed payload checks, static ELF and desktop checks |
| `control.in` | arm64 control template |
| `copyright` | Upstream application copyright/license notice |
| `font-license` | Embedded Unifont notice and OFL 1.1 text |
| `helper-inputs` | Declare `adapter/package.sh` and `adapter/rewrite-control.py` as recipe inputs |

The current helpers are `lib/adapter/package.sh` and
`lib/adapter/rewrite-control.py`. The original adapter-local
`rewrite-control.py` no longer exists. Declaring the shared helpers ensures their
changes affect this stream's recipe checksum. Developer documentation stays in
`docs/` so editing it does not itself trigger package revisions.

### Query and version selection

The query fetches
`https://gitlab.com/bztsrc/usbimager/-/raw/binaries/sha256checksums.txt`.
The selector validates checksum rows and rejects duplicate names. Stable numbered
versions use three numeric components; numeric comparison puts 1.0.10 after
1.0.9. It first chooses the newest such version represented in the manifest,
then looks for that version's requested architecture assets:

```text
amd64: usbimager_VERSION-amd64.deb
arm64: usbimager_VERSION_uf-aarch64-linux-x11.zip
```

`WORKSPACE/assets.json` records version, artifact name, URL, and SHA256 keyed by
architecture. `WORKSPACE/targets.tsv` contains newline-terminated
`VERSION<TAB>ARCH` rows for available requested architectures. Missing current
artifacts do not select older versions; the framework warns and retains stored
packages. Network errors or malformed manifests fail the stream. The adapter has
no `stale-after-days` setting and does not supply release-date monitoring data.

Hashes are supplied by the same upstream over HTTPS; no independent signature
was added. If a manifest changes before its corresponding download, verification
fails and the normal next cycle retries. The currently used shared download
helper uses `refresh`, verifies a `.part` file, then moves verified bytes into
place. The normal build hook therefore downloads again rather than accepting
an arbitrary preexisting workspace file.

The manifest's hashes are download integrity data, not recipe-change inputs.
Upstream has replaced artifacts under an unchanged release version. Such a
replacement alone does not rebuild an already-complete version. A reviewed
recipe change is needed to trigger a new packaging revision of current targets;
stored packages must never be overwritten to force an update.

### Staging and validation

amd64 import requires upstream name `usbimager`, the selected upstream version,
and architecture `amd64`. Both Debian data and control archives are inspected
for unsafe paths, links, and special entries before raw extraction. Upstream
control fields and any maintainer scripts are retained except fields explicitly
rewritten; no upstream script is executed during repackaging. Preserved scripts
could run later during client installation.

The arm64 ZIP is validated before extraction. Its complete regular-file set is:

```text
bin/usbimager
share/applications/usbimager.desktop
share/man/man8/usbimager.8.gz
share/icons/hicolor/16x16/apps/usbimager.png
share/icons/hicolor/32x32/apps/usbimager.png
share/icons/hicolor/64x64/apps/usbimager.png
share/icons/hicolor/128x128/apps/usbimager.png
```

Those paths are staged under `/usr`. Unexpected files/directories, duplicate ZIP
names, absolute/traversing paths, backslash paths, links, and special file types
fail. The amd64 payload must contain the same required application/resources
under `/usr`, but is not subject to the ZIP's exact file-set restriction.
Staged trees reject links and special files before payload reads or chmods.

ELF checks use `readelf` as data inspection. They require ELF64 and the correct
machine (`Advanced Micro Devices X86-64` or `AArch64`), reject unrecognized linked
SONAMEs and RPATH/RUNPATH entries, and reject GLIBC symbol versions above the
Debian 13 baseline of 2.41. These checks do not execute an amd64 or arm64 target.
The allowlist restricts linked names; it is not a full runtime dependency solver
or a check that every allowed GUI library is present in each fixture.

Desktop validation requires `Type=Application`,
`Exec=/usr/bin/usbimager`, and `Icon=usbimager`. The upstream launch command and
integration files are retained. Directories become mode 0755, regular `/usr`
files become 0644, and the main executable becomes 0755. Package construction
normalizes archive ownership to root. No device permissions or privileged
execution bits are granted.

Application notices are installed under `/usr/share/doc/PACKAGE/`; the original
Debian copyright notice is also copied there if supplied in its control archive.
The arm64 package additionally installs the embedded font notice and license.
The inspected upstream font header contained GNU Unifont 15.0.01 metadata naming
Roman Czyborra, Paul Hardy, Qianqian Fang, Andrew Miller, Johnnie Weaver, David
Corbett, Nils Moskopp, Rebecca Bettencourt, and others. Its metadata offers OFL
1.1 or GPLv2+ with the GNU Font Embedding Exception; the package uses OFL 1.1.
The source header and OFL text were retained with the investigation downloads.

### Dependencies, control metadata, and permissions

The inspected amd64 executable directly needs `libgtk-3.so.0`,
`libgio-2.0.so.0`, `libgobject-2.0.so.0`, `libglib-2.0.so.0`,
`libudisks2.so.0`, and `libc.so.6`. The current Debian dependency declaration is:

```text
udisks2, libgtk-3-0t64, libglib2.0-0t64, libudisks2-0, libc6 (>= 2.41)
```

The inspected arm64 executable directly needs `libX11.so.6` and `libc.so.6`.
Its current declaration is `libc6 (>= 2.41), libx11-6`.
The original inspection found GLIBC requirements up to 2.28 in both official
binaries. The declared 2.41 floor reflects the implementation's Debian 13 target;
it was not established as an upstream feature requirement or the binary's minimum
GLIBC requirement. No older-Debian compatibility study or Debian-patch analysis
was performed. Revisit the floor using actual symbol/feature requirements if
older clients become a goal; do not treat it as proof that upstream needs 2.41.

The importer rewrites Package, Version, Depends, Conflicts, Provides, Section,
Installed-Size, Maintainer, X-Build-Inputs-SHA256, and X-Publisher-Stream.
The arm64 template supplies those fields and Architecture, Homepage, Priority,
and Description. The configured maintainer is escaped by shared rendering
helpers. `Installed-Size` is calculated in KiB from the final staged tree,
excluding `DEBIAN/`, including when upstream omits it or supplies a stale value.
`dpkg-deb --build` does not calculate it automatically.

GTK uses udisks2 for disk access. The X11 interface directly accesses devices and
requires suitable device permissions or an explicitly privileged launch. The
adapter does not add users to `disk`, install permission-changing rules, or
introduce a privileged wrapper. The arm64 interface also needs an X11 display
or XWayland. Actual authorization prompts and desktop behavior were not tested.

## Original verification and retained evidence

The following results belong to the October 28 implementation, before later
shared-helper and repository-layout changes. They are not assertions that the
current full suite has the same count or that the current recipe generates the
same bytes. No production repository or signing keys were used for these checks.

| Check | Original result | Retained evidence |
| --- | --- | --- |
| USBImager offline regression | 10 tests passed | `build/test-run-QWBDMS/regression.log` |
| Framework regression after new cases | 51 tests passed | `build/test-run-Liwsb5/regression.log` |
| Adapter test coordinator | Passed | `build/usbimager/logs/adapter-tests.log` |
| Framework test coordinator | Passed | `build/usbimager/logs/framework-tests.log` |
| Builds using verified official cached artifacts | Both architectures passed | `build/usbimager/logs/live-build.log` |
| Bash syntax, Python compile, whitespace checks | Passed | `build/usbimager/logs/static-checks-final.log` |
| Source/ELF inspection | arm64 details retained | `build/usbimager/logs/upstream-inspection.log` |
| Initial framework attempt without local dpkg-dev | Failed: missing `dpkg-scanpackages` | `build/test-run-lLOgV9/regression.log` |

The original ten adapter tests cover both output names, publisher fields,
maintainer escaping, dependencies, root ownership, executable mode, license
files, positive package/index Installed-Size, repeat-update byte preservation,
missing-arm64 completion, stale and missing upstream size metadata, bad hashes,
required layout, wrong ELF machine, unknown libraries, wrong package identity,
numeric version ordering, requested architecture selection, no old-release
fallback, malformed/duplicate manifests, and ZIP links/traversal/extra files.
They use offline synthetic fixtures, real Debian tools, and ELF headers derived
from `/bin/true`; they do not test the actual GUI.

The five framework tests in `tests/test_architecture_packages.py` cover variant
outputs/resumption at one revision, revision history from an unselected
architecture, a shared `all` package, wrong variant output rejection, and invalid
or mixed configuration. Current USBImager tests are at
`tests/usbimager/test_usbimager.py` and copy the adapter from its current repack
path. Neither the original selected runs nor this documentation update ran the
real signing test, built a publisher image, deployed services, installed the
package on a client, launched the GUI, or wrote a USB device.

### Verified upstream artifacts and original outputs

The original selected upstream release was **1.0.10**. Its verified input hashes
were:

```text
da9b1f01a8ee341df1943d73140b4b8bcc23a3b734861a1a8891600f9933bbd3  usbimager_1.0.10-amd64.deb
e1c76897cbf11720c2a5525388811eab64b7e5c9ec86fea0a4908e6391abd19b  usbimager_1.0.10_uf-aarch64-linux-x11.zip
```

Both names resolve beneath
`https://gitlab.com/bztsrc/usbimager/-/raw/binaries/`. The retained arm64 download
is named `build/usbimager/downloads/arm64.zip`; its canonical upstream name is
also present as a symlink in that ignored cache. That convenience symlink is not
an adapter recipe symlink or a packaged payload link.

The original successful outputs still existed at the handoff inspection:

| Local artifact under `build/usbimager/live/output/` | Archive bytes | Installed-Size KiB |
| --- | --- | --- |
| `amd64/usbimager-gtk_1.0.10-1_amd64.deb` | 177090 | 424 |
| `arm64/usbimager-x11_1.0.10-1_arm64.deb` | 730068 | 1192 |

They used the test maintainer `Local Verification <test@localhost>` and embedded
recipe checksum
`43b6ef4a56699f9558285b9c8b3a1eacf6ada4d4a3a118547cb6f7fbe0e4298d`.
Those are historical verification artifacts, not ready-to-publish operator builds
or the current recipe's expected checksum. The generated unsigned index is
`build/usbimager/live/Packages`; selection records are `assets.json`,
`targets.tsv`, and `sha256checksums.txt` in the same workspace.

## Local tools and repeatable checks

The operator explicitly preferred tools local to this checkout over system-wide
installation or repeated Docker requests. The full setup, dependency list,
download/extraction commands, activation, versions, and evidence are in
[local Debian tools](local-tools.md). The retained setup provides dpkg-dev,
libdpkg-perl, binutils and its missing libraries, and make under ignored
`build/tools/root/`. Host Perl and runtime libraries remain prerequisites.
`apt-ftparchive` was already installed natively. No compiler, GTK development
packages, or target execution is needed for USBImager repacking.

From the project root, run only the appropriate checks with environment changes
confined to a subshell:

```bash
mkdir -p build/usbimager/logs
(
    export FRAMEWORK_DIR="$PWD"
    source build/tools/env.sh
    timeout 5m bash tests/run.sh usbimager
) > build/usbimager/logs/adapter-current.log 2>&1
```

For framework changes, use the same form with `bash tests/run.sh --framework`
and a separate log such as `framework-current.log`. Documentation-only work needs
link/factual/whitespace checks rather than package builds or signing tests.
Preserve original logs separately from new runs, wait for completion or a bounded
timeout, and inspect the logs afterward. Tests run as the host user and use
isolated temporary repositories and fixtures.

For future recipe changes, check shell syntax and whitespace with:

```bash
(
    bash -n update.sh lib/config.sh lib/update-package.sh \
        packages/repack/usbimager/query packages/repack/usbimager/build
    git diff --check
) > build/usbimager/logs/static-current.log 2>&1
```

### Reusing official downloads for a direct verification build

The ignored `build/usbimager/cache-bin/curl` is a verification-only downloader
stub: it copies the basename of each requested URL from
`USBIMAGER_DOWNLOAD_CACHE` to curl's requested output path. It does not fetch
network data or provide freshness guarantees. The real build's SHA256 check
still runs on those bytes. Keep the stub scoped to the verification subprocess;
never use it for ordinary publisher updates or production downloads.

The retained `build/usbimager/live-build.sh` and `build/usbimager/checks.sh` were
written before the repository move and helper extraction. They still reference
the old `packages/usbimager/` location and, in the latter script, the deleted
adapter-local `rewrite-control.py`. They are historical evidence, not current
entry points. Prefer the tracked regression runner. To repeat a direct cached
build, adapt this example to a fresh workspace and a still-correct cached manifest:

```bash
(
    set -Eeuo pipefail
    export FRAMEWORK_DIR="$PWD"
    source build/tools/env.sh
    export ADAPTER_DIR="$FRAMEWORK_DIR/packages/repack/usbimager"
    export WORKSPACE
    WORKSPACE=$(mktemp -d "$FRAMEWORK_DIR/build/usbimager/reverify-XXXXXX")
    export ARCHES='amd64 arm64'
    export MAINTAINER='Local Verification <test@localhost>'
    export PUBLISHER_STREAM=usbimager
    export USBIMAGER_DOWNLOAD_CACHE="$FRAMEWORK_DIR/build/usbimager/downloads"
    export PATH="$FRAMEWORK_DIR/build/usbimager/cache-bin:$PATH"
    export BUILD_INPUTS_SHA256
    BUILD_INPUTS_SHA256=$(python3 "$FRAMEWORK_DIR/lib/checksum.py")

    printf 'Verification workspace: %s\n' "$WORKSPACE"
    "$ADAPTER_DIR/query"
    while IFS=$'\t' read -r VERSION ARCHITECTURE; do
        mkdir -p "$WORKSPACE/output/$ARCHITECTURE"
        "$ADAPTER_DIR/build" "$VERSION-1" "$ARCHITECTURE" \
            "$WORKSPACE/output/$ARCHITECTURE"
    done < "$WORKSPACE/targets.tsv"
    dpkg-scanpackages --multiversion "$WORKSPACE/output" /dev/null \
        > "$WORKSPACE/Packages"
) > build/usbimager/logs/cached-reverification.log 2>&1
```

This example deliberately bypasses revision resolution/storage/signing and uses
a local `-1` verification revision. It must not be used to assign a production
revision or write into a served pool. The original build verifies cached October
artifacts; it does not establish which release upstream publishes today.
If the ignored cache stub is absent, use the normal query/build with network
access or recreate the stub explicitly; do not silently treat a network run as
a cached run. Both hooks require supplied context and an existing workspace;
build also requires an existing empty output directory.

## Remaining work and maintenance limits

The packaging implementation is complete for the original request. A future
maintainer does not need to repeat planning or invent package identities.
Remaining validation is operational and must be described accurately:

1. Check current upstream metadata when preparing a real update; historical
   hashes and version 1.0.10 are evidence, not a pinned current release policy.
2. After recipe/framework changes, run relevant adapter/framework tests with
   available dependencies. Historical passing logs do not replace current checks.
3. If deployment is requested, use the current README's repack image/service,
   storage, and key configuration. This session established no deployment state.
4. Validate installation, desktop launch, udisks2 authorization, and actual
   imaging/backup/verification on an appropriate amd64 client and expendable
   device if runtime validation is requested. None was performed here.
5. Keep arm64 support statically inspectable and covered by packaging tests;
   runtime validation remains outstanding until there is a consumer or target
   environment. Do not claim a GTK arm64 build exists based on the armhf `.deb`.

The work originally left unrelated `gimp-investigation/` data alone. The November
documentation inspection found other sessions' staged and unstaged documentation
changes; they are not USBImager implementation work and must not be reset or
folded into this handoff. No operator secrets, production package data, or signing
keys are included in this document.

Useful downloads, successful verification packages, selection files, and logs
are retained under `build/usbimager/`. Redundant extraction/staging trees and
duplicate temporary inspection binaries were removed after the original
verification. All of `build/` is ignored and may be absent on another checkout;
this document and tracked source/tests preserve the decisions independently.

## Documentation verification on November 13, 2026

The handoff update changed only this document, `docs/usbimager.md`, and
`docs/local-tools.md`. Local Markdown link targets and the syntax of their Bash
examples were checked. Both cached upstream SHA256 values, both original output
archive sizes, and the retained 10-test and 51-test passing logs were confirmed
against files still present on disk. Documentation whitespace checks passed.
The check output is `build/usbimager/logs/documentation-handoff-checks.log`.

No upstream network refresh, package rebuild, regression rerun, signing test,
container build, deployment, GUI launch, or USB operation was performed for this
documentation-only update. Other sessions' preexisting working-tree changes were
left in place. The original chat is not required to interpret these documents.
