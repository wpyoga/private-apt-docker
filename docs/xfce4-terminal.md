# Patched xfce4-terminal

The adapter follows the newest xfce4-terminal source in Debian Trixie,
trixie-updates and trixie-security. APT verifies repository metadata and source
checksums. Each architecture starts with a fresh `dpkg-source` extraction, including
Debian's existing patches, then applies the local series without patch fuzz.
There is no persistent upstream Git checkout. Only xfce4-terminal is compiled;
its build dependencies are installed from Debian binary packages.

The [rebuild lock incident handoff](rebuild-lock-incident.md) records why amd64
skipped its cycle while arm64 failed to apply the original Shift+Enter patch,
the blocking-lock fix and tests, and the limits of that investigation.

Before building either architecture, the adapter adds `--enable-maintainer-mode`
to Debian's existing `dh_auto_configure -- --with-utempter` command in
`debian/rules`. It fails if the expected command changes so the new packaging
can be reviewed. This packaging adjustment is separate from the quilt series.

The screensaver adapter needed a separate D-Bus directory lookup correction for
arm64 cross-builds. The inspected terminal 1.1.4 source uses dependency macros
that honor `$PKG_CONFIG` and has no equivalent activation-service lookup. See
[the screensaver cross-build investigation](xfce4-screensaver.md#why-xfce4-terminal-was-unaffected)
for the source comparison and verification limits.

## Configure override: implementation and handoff

This section records the configure change requested in the original development
conversation so that maintaining it does not depend on that conversation.
The implementation and tests were reviewed again on 2026-11-13.

### Requested behavior and Debian's existing rule

The requested effective rule is:

```makefile
override_dh_auto_configure:
	dh_auto_configure -- --with-utempter --enable-maintainer-mode
```

The command starts with a literal tab because `debian/rules` is a Makefile.
The `--` separates debhelper options from arguments passed to upstream's
configure script. The requested change explicitly enables maintainer mode while
preserving utempter support. It does not add a second override target.

The cached Debian `xfce4-terminal_1.1.4-1.debian.tar.xz` was inspected during
implementation. Its `debian/rules` already contained:

```makefile
override_dh_auto_configure:
	dh_auto_configure -- --with-utempter
```

That file also contained Debian's linker and hardening settings, installation
hook, and changelog hook. The adapter changes only the configure command and
preserves the rest of the file. Maintainer mode was explicitly requested; this
work did not establish a separate diagnosis of which generated files require it,
or verify its effects through a new full compilation.

### Files and build order

| File | Role in this change |
| --- | --- |
| [Build hook](../packages/rebuild/xfce4-terminal/build) | Validates and edits the extracted `debian/rules` before compilation |
| [Dependency installer](../packages/rebuild/xfce4-terminal/install-build-dependencies) | Already installs `libutempter-dev` for the target architecture; no dependency change was needed |
| [Offline tests](../tests/xfce4-terminal/test_source.py) | Exercises the effective Makefile command on both architecture paths and rejection of a changed command |
| [Debian rules fixture](../tests/xfce4-terminal/fixtures/rules) | Records the inspected Debian 1.1.4-1 rules as the test input |

The build hook performs these steps for each architecture:

1. Check that the requested architecture matches the toolchain image, and extract
   the downloaded Debian source into `WORKSPACE/build-ARCHITECTURE`.
2. Import and apply the adapter's quilt patch series with zero fuzz.
3. Require the exact tab-indented command
   `dh_auto_configure -- --with-utempter` in the extracted `debian/rules`.
   Replace that whole line with the requested command using `sed`.
4. For arm64, make the existing `xfce4-dev-tools` dependency native to the builder
   and select `aarch64-linux-gnu-gcc`.
5. Set the local changelog version and existing build options, then invoke
   `dpkg-buildpackage --build=binary --host-arch ARCHITECTURE -us -uc`.
6. Validate the binary package's name, version, architecture and required paths,
   recalculate `Installed-Size`, and add publisher metadata through the normal
   package helpers.

There is no checked-in package `debian/rules` to edit directly: it arrives in
each downloaded Debian source package. The persistent change belongs to the
adapter's build hook. It is kept outside the quilt series because it changes
Debian packaging rather than upstream application source. Both amd64 and arm64
pass through the same configure adjustment before their build command.

### Failure behavior and future Debian updates

The guard uses `grep -Fxq` against the complete command line, including its
leading tab. Changed options, indentation or trailing whitespace can therefore
cause this error:

```text
xfce4-terminal SOURCE_VERSION: unexpected dh_auto_configure command in debian/rules
```

The build exits before `dpkg-buildpackage` runs. Existing published packages
remain available. This strict check intentionally makes an upstream packaging
change visible for review; it does not search for another command or silently
append an alternative override. The check validates the command line, rather
than parsing the complete Makefile structure.

If this error appears, inspect the newly downloaded Debian source and its
`debian/rules`. Decide how the requested option should combine with Debian's
new recipe, then update the guard, replacement, fixture and regression tests
together. If Debian starts supplying maintainer mode itself, review and remove
or revise the local adjustment rather than weakening the guard without checking
the effective rule. Each normal build starts from a fresh source extraction;
the adjustment is not intended to run twice on an already edited tree.

Changing the build hook changes this adapter's recipe checksum. The existing
stored-package revision mechanism allocates the next local revision for the
current queried source version, or resumes a matching incomplete revision.
There is no manual revision counter to update and no request to rebuild
historical source versions. Documentation lives here, outside `packages/`, so
documentation-only maintenance does not change the adapter checksum.

### Regression coverage and verification record

The original implementation passed all six xfce4-terminal offline tests,
`bash -n packages/rebuild/xfce4-terminal/build`, and `git diff --check`.
The configure-related tests cover:

- amd64: execute `make -f debian/rules override_dh_auto_configure` and check that
  `dh_auto_configure` receives `--`, `--with-utempter`, and
  `--enable-maintainer-mode` in that order. The same test builds a fixture Debian
  package, replaces a stale `Installed-Size`, and checks its published index value.
- arm64: execute the effective Makefile override and check the same arguments,
  then require an arm64 output package from the fixture build.
- changed Debian recipe: replace the fixture's `--with-utempter` with
  `--without-utempter` and require failure before configuration or package output.

The other three tests cover source version selection for both architectures,
a missing source descriptor, and a descriptor without a version.

These are orchestration tests: source extraction, quilt, changelog updates,
`dh_auto_configure`, and the compiler build command are stubbed. GNU Make and
Debian binary package/index tools run for real. The arm64 test does not compile
or execute an arm64 terminal. The fixture keeps the tested rule explicit and
does not automatically follow future Debian source updates.

The original local evidence, if still present, is in:

- `build/xfce-maintainer-tests.log` and `build/test-run-rVgEQm/regression.log`;
- `build/xfce-maintainer-syntax.log`;
- `build/xfce-maintainer-diff-check.log`.

Those ignored logs are optional evidence, not required build inputs. To rerun
the relevant checks from the project root, run each command to completion and
then inspect its named log:

```sh
mkdir -p build
timeout 30m bash tests/run.sh xfce4-terminal > build/xfce-maintainer-tests.log 2>&1
bash -n packages/rebuild/xfce4-terminal/build > build/xfce-maintainer-syntax.log 2>&1
git diff --check > build/xfce-maintainer-diff-check.log 2>&1
```

The test runner writes the detailed regression log into a `build/test-run-*`
directory and reports its path in the outer log. A successful later command
does not establish that an earlier command passed: check each exit status and
its log. Signing code was unchanged, so the signing integration test was not
part of this package-specific verification.

### Deployment still required for the configure change

No container image build, service recreation, publication, or desktop runtime
check was performed as part of implementing this configure override. The older
native/cross compilation results described below predate this change and do not
validate maintainer mode. The documentation handoff itself does not deploy it.

Adapters are copied into container images. On the intended deployment, after
reviewing its settings, rebuild and recreate both rebuild services:

```sh
mkdir -p build
timeout 30m docker compose build rebuild-amd64 rebuild-arm64 > build/xfce-maintainer-images.log 2>&1
timeout 5m docker compose up -d --force-recreate rebuild-amd64 rebuild-arm64 > build/xfce-maintainer-services.log 2>&1
```

Run the second command only after the image build succeeds. Recreating these
services starts their update cycles for all configured rebuild streams. They
use the configured repository data and signing identity; the shared lock
serializes their cycles. Inspect completed build logs for the configure command,
check the resulting package versions and metadata, and verify the installed
terminal interactively on the laptop. Preserve failure logs for review. Local
experiments must use isolated repository data and signing keys as described in
[local testing](../README.md#local-testing).

## Public patches

See [Debian patches and the local patch stack](#debian-patches-and-the-local-patch-stack)
for their locations, application order, inspection commands, and the verified
absence of a Debian quilt series in source version 1.1.4-1.

Commit patches under `packages/rebuild/xfce4-terminal/patches/` and list their filenames,
one per line in application order, in `patches/series`. Blank lines and lines
starting with `#` are ignored. The series currently contains
`000-shift-enter.patch` and `001-title-bar-tabs.patch`.
Do not commit secrets. Adapter file changes allocate a new package revision;
unrelated adapters retain their own recipe checksums.

Versions retain the full Debian source version and append `+local-N`, for example
`1.1.4-1+local-1`. Patch changes increment N through the existing stored-package
revision mechanism. New Debian source versions start a fresh revision history.
Failures identify the package/version/architecture in logs, retain old published
packages, and retry next cycle. Other streams continue. Logs are the alert channel.

## Debian patches and the local patch stack

This section preserves the patch-handling explanation and investigation from
the development conversation. The adapter, tests, and cached source archive
were inspected on 2026-11-13. The source-version-specific finding below is about
the cached Debian 1.1.4-1 source, not a claim about every future Trixie update.

### What was found, and a correction to the earlier explanation

The adapter preserves any patches supplied by Debian and applies the local
series afterward. However, **the inspected Debian xfce4-terminal 1.1.4-1 source
contains no `debian/patches/` directory or Debian quilt series**. Its
`debian/source/format` is still `3.0 (quilt)`: that format permits a package
without upstream source patches.

Consequently, seeing only `000-shift-enter.patch` and
`001-title-bar-tabs.patch` in that version's extracted `debian/patches/` is
expected. Those files were placed there by our build hook. Their presence does
not mean Debian's patch files were overwritten or purged. The earlier chat
answer described the general combined-stack behavior but incorrectly implied
that this particular Debian version already had a patch series.

Debian can carry extensive changes, but the amount varies by package and source
version. Debian packaging also includes build rules, dependency declarations,
installation instructions, wrappers, and other files under `debian/`; those
are present even when there is no `debian/patches/` directory. In the inspected
archive, examples include `debian/rules`, `debian/control`,
`debian/alternatives`, and `debian/xfce4-terminal.wrapper`.

### Where the original source and patches live

The [query hook](../packages/rebuild/xfce4-terminal/query) downloads the Debian
source selected by APT from the adapter's
[Trixie source repositories](../packages/rebuild/xfce4-terminal/sources.list).
It uses `apt-get source --download-only`, rather than cloning the Xfce upstream
repository or starting from an installed binary package.

For the inspected version, the source package consists of:

| File | Contents |
| --- | --- |
| `xfce4-terminal_1.1.4-1.dsc` | Source identity, Debian version, archive filenames, and checksums |
| `xfce4-terminal_1.1.4.orig.tar.bz2` | Original upstream source archive |
| `xfce4-terminal_1.1.4-1.debian.tar.xz` | Debian packaging directory; would also contain Debian quilt patches if this version supplied any |

The descriptor records the packaging archive's SHA256 as
`585abe7b06443181dcbe270bb56d8aca3977f18d8e5b1d186f01b3f4d0681b12`.
The cached archive was checked against that value during this documentation
update. Archive checksums identify the inspected bytes; they are not patch
revision counters.

The locations used by the adapter are:

| Location | Purpose |
| --- | --- |
| `$WORKSPACE/source/` | Downloaded `.dsc`, original source, and Debian packaging archives |
| `$WORKSPACE/build-amd64/` or `$WORKSPACE/build-arm64/` | Fresh extracted source used for that architecture's build |
| `debian/patches/` inside that extracted tree | Debian's patch files, if any, plus local patches imported during the build |
| `debian/patches/series` inside that extracted tree | Combined application order after local imports |
| `.pc/` inside that extracted tree | Quilt bookkeeping and backups of files changed by applied patches |
| `packages/rebuild/xfce4-terminal/patches/` in this checkout | Maintained local patch files, independent of the temporary extraction |
| `packages/rebuild/xfce4-terminal/patches/series` in this checkout | Local patch order read by the build hook |

The local series currently lists `000-shift-enter.patch` followed by
`001-title-bar-tabs.patch`. That order comes from `series`, not a directory
listing or filename sorting. The adapter accepts one filename per line, with
blank lines and lines beginning with `#` ignored; do not add quilt options or
inline comments to this adapter's local series.

For the usual `3.0 (quilt)` source format, Debian's patches are carried under
`debian/patches/` in the packaging archive. Older source formats can store
changes differently, so inspect the descriptor and `debian/source/format`
before assuming this layout for another package. The installed binary `.deb`
normally contains compiled results, resources, and package metadata; it is not
where to look for the source patch queue. See the
[Debian dpkg-source manual](https://manpages.debian.org/trixie/dpkg-dev/dpkg-source.1.en.html).

### How the build preserves the Debian baseline

The [build hook](../packages/rebuild/xfce4-terminal/build) performs this sequence:

1. Extract the downloaded `.dsc` with `dpkg-source -x` into a fresh architecture
   directory. For a `3.0 (quilt)` source, extraction applies Debian's declared
   patches, if present. The downloaded source archives remain unchanged.
2. Set `QUILT_PATCHES=debian/patches` in the extracted tree.
3. Read each local filename from the adapter's `patches/series`. Reject absolute
   names, names containing `..`, and missing patch files.
4. Run `quilt import` on that local file. This copies it into the extracted
   tree's patch directory and records it after the currently applied patch.
5. Run `quilt push --fuzz=0`. Repeat import and push for the next local patch.
   With Debian's patches already applied, this places the local series on top
   of Debian's source baseline.
6. Apply the separate packaging adjustments described elsewhere in this file:
   the maintainer-mode configure option, the arm64 native tool dependency, and
   the local changelog version. Then build the binary package.

The hook does not remove Debian's patch directory, replace its series with our
local series, or call `quilt import -f`. A patch filename collision therefore
fails rather than authorizing replacement. A patch that cannot apply also
fails the build. Zero fuzz rejects application that requires dropping context
lines; it does not prohibit a line-number offset or prove that an applicable
patch is semantically correct. Local patches still need review when Debian or
upstream changes the surrounding code. The
[Debian quilt manual](https://manpages.debian.org/trixie/quilt/quilt.1.en.html)
documents import, push, series, and applied-patch bookkeeping.

Preserving Debian's patch files does not guarantee every effect of those
patches remains unchanged: a later local patch can deliberately change the same
code. The intended baseline is Debian's extracted source plus the reviewed
local changes. This build does not globally strip Debian modifications.

### Inspecting the original archive without changing a build tree

Run these commands from the project root to reproduce the cached-source
inspection, if that cache is still present. They list or read archive members;
they do not import, apply, or remove patches. Each command writes a named log
for inspection after it completes.

```sh
mkdir -p build/logs
sha256sum build/xfce-live-amd64/source/xfce4-terminal_1.1.4-1.debian.tar.xz > build/logs/terminal-debian-sha256.log 2>&1
tar -tf build/xfce-live-amd64/source/xfce4-terminal_1.1.4-1.debian.tar.xz > build/logs/terminal-debian-members.log 2>&1
tar -xOf build/xfce-live-amd64/source/xfce4-terminal_1.1.4-1.debian.tar.xz debian/source/format > build/logs/terminal-debian-format.log 2>&1
```

Compare the SHA256 log with the descriptor's `Checksums-Sha256` entry. The member
listing for the inspected archive has no `debian/patches/` entries; the format
log contains `3.0 (quilt)`. The historical cache paths are examples, not required
runtime locations. If they are absent, use the corresponding archives from a
retained workspace. For a different source version, inspect that version's own
descriptor and packaging archive instead of reusing this version's conclusion.

To inspect a retained extracted tree, set `SOURCE_DIR` to its actual path and
run the following in Bash. Replace the example path first. A publisher workspace
is often inside a container, so run the inspection where those files exist.

```bash
SOURCE_DIR=/absolute/path/to/xfce4-terminal/build-amd64
mkdir -p build/logs
(
    set -Eeuo pipefail
    cd "$SOURCE_DIR"
    export QUILT_PATCHES=debian/patches
    cat debian/source/format
    if [[ -f debian/patches/series ]]; then
        cat debian/patches/series
        quilt series
        quilt applied
    else
        echo 'This extracted tree has no debian/patches/series'
    fi
) > build/logs/terminal-extracted-patches.log 2>&1
```

The combined series alone does not label each patch's origin. Compare it with
the original Debian archive and the checkout's local series. A freshly extracted
tree before local imports shows the Debian baseline; an in-progress failed tree
may contain only part of the local series. Quilt state and the build log identify
how far the build got. An empty stack can make a quilt query return nonzero;
inspect its message rather than treating that alone as evidence of lost patches.

### Persistence, maintenance, and verification limits

Edit maintained local patches in the checkout, not only their copies in
`build-amd64/debian/patches/`. A build-tree-only edit is temporary and will not
be included in the next fresh extraction. Commit intended patch changes and
their local series entries together. If a future Debian patch collides with a
local filename or makes a local patch obsolete, inspect both changes and update
the local recipe deliberately; do not force an import to hide the conflict.

Normal publisher workspaces are temporary directories created by `update.sh`,
with stream data under `streams/xfce4-terminal/`. Successful cycles remove their
workspace. Failed cycles log and retain their workspace; a later failure for
the same builder identity replaces the earlier failure evidence. Container
replacement can also lose temporary files. Keep useful diagnostic copies under
ignored `build/`, and rely on the committed recipe for lasting local changes.
Stored repository packages are separate and are not removed by this cleanup.

This documentation update inspected the real cached Debian packaging archive,
its descriptor, the actual query/build hooks, and the offline tests. It did not
run a new compilation, deploy services, or verify desktop behavior. The current
offline adapter tests stub `dpkg-source` and `quilt`; they do not independently
prove that a real Debian patch queue survives import. The archive finding above
is direct evidence for 1.1.4-1, while the explanation of a nonempty Debian queue
comes from the hook's commands and the Debian tool documentation.

## Headless build server

No desktop is required. The initial build image targets an amd64 Docker host,
building amd64 natively and arm64 with Debian cross-development packages.
Separate images are required because the two Xfce development dependency sets
pull in conflicting architecture-specific xfconf packages.
Rootless Docker can run the deployment; configure its normal host prerequisites
first. No Docker socket is mounted inside the publisher.

Use the same checkout, `.env`, and Compose project as the repack publisher.
Set `REPACK_REPO_DIR` and `REBUILD_REPO_DIR` to different absolute output paths;
keep both architectures in `REPO_ARCHITECTURES`. `REPACK_GNUPG_DIR` and `REBUILD_GNUPG_DIR` hold independent keys. Run setup once to prepare both outputs and the signing key.

```sh
docker compose up -d --build
```

Compose builds the repack publisher and both toolchain images from the root
Dockerfile. Its `tools` stage installs shared tools. The `rebuild-tools` stage
installs architecture-specific dependencies before copying framework and adapter
files into the final `rebuild` target. Patch and script edits therefore reuse the
dependency layers; changing `install-build-dependencies` reruns installation.
Services are `codex-repo-updater`, `rebuild-amd64`,
and `rebuild-arm64`. The latter two use the same rebuild output and lock, with
one architecture per instance. When the lock is busy, the other instance waits
and runs its cycle after the lock is released, even if the previous cycle failed.
Each instance waits the configured interval after its own cycle finishes.
Repacks use their separate output and lock.

Adapters are copied into images; rebuild and recreate services after changes.
Compilation runs with the configured host UID/GID. Package dependency installation
occurs only in image layers. No per-package repository setting is needed: parent
directories select adapter membership. For a standalone toolchain build, use
`docker build --target rebuild --build-arg TARGET_ARCH=amd64 .` (or `arm64`).
The default target remains the repack publisher used by setup.

If Debian adds build dependencies, update the adapter's
`install-build-dependencies` script and rebuild the image; failed dependency
checks must not be bypassed. Docker cannot detect new upstream dependencies from
unchanged local inputs. To refresh Debian packages even when the declarations
have not changed, use `docker compose build --pull --no-cache`, then recreate the
services with `docker compose up -d`.

The environment follows Trixie but is not bit-for-bit reproducible: image tags
and dependency versions are not pinned. Native amd64 and cross-compiled arm64 builds of Debian source 1.1.4-1
were validated in the toolchain containers. Both output ELF architectures and
Installed-Size values in package indexes were checked. Desktop runtime behavior
and rootless-daemon deployment remain unverified.

## Laptop

Serve this deployment's repository using the existing web-server instructions.
Add its APT entry with the rebuild repository Signed-By key, then prefer its package:

```text
Package: xfce4-terminal
Pin: release o=rebuild
Pin-Priority: 990
```

The Origin must match your chosen REPO_NAME. Check `apt-cache policy
xfce4-terminal` before `sudo apt install xfce4-terminal`, especially if you set
APT::Default-Release. The preference keeps the last successful local build
selected while newer Debian source is being rebuilt. Quit existing terminal
processes before testing the new executable. Interactive testing happens on the
laptop; the build server does not need a graphical session.

Rootless Docker itself is not validated by the offline suite. Its UID mapping
can differ from the system daemon: verify bind-mounted files retain the intended
host ownership before using real repository storage. The Compose UID/GID settings
are designed for the existing system-daemon deployment and must not be assumed to
map identically under a rootless daemon.

The arm64 build marks Debian's existing `xfce4-dev-tools (>= 4.18.1)` build
dependency as `:native`, since it executes on the amd64 builder. The adapter
checks that declaration before changing it and fails if Debian changes its
layout. This packaging adjustment is separate from the local
patch series. Upstream tests are disabled for these cross-builds; desktop runtime
verification remains a laptop check.

Signing configuration uses separate `REPACK_GNUPG_DIR` and `REBUILD_GNUPG_DIR`
and separate `REPACK_GPG_KEY` and `REBUILD_GPG_KEY` fingerprints in the one .env.
Setup generates or selects keys independently, exports `repack-pubkey.asc` and
`rebuild-pubkey.asc`, and never copies or synchronizes keyrings. Both rebuild
containers mount only the rebuild keyring; repack mounts only its own.
Existing deployments can keep their current paths when the web root excludes
both keyrings. To adopt the shared `/srv/apt` web root, follow the
[storage migration instructions](../README.md#moving-existing-storage) before serving it.
Keep existing signing fingerprints when moving keyrings.
Remove obsolete REPO_DATA_DIR and GPG_KEY settings after configuring these fields.
Never serve either signing directory over HTTP.
