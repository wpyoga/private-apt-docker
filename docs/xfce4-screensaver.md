# Patched xfce4-screensaver

This is the implementation and operational handoff for the screensaver work,
updated on 2026-11-13. It preserves the decisions, failure investigation, test
results and follow-up work from the original conversation. It describes the
checked-in implementation; production verification is identified separately.

## Purpose and current status

The maintainer requested a new `xfce4-screensaver` source-rebuild stream and chose
to supply the application patch manually. The adapter was added under
`packages/rebuild/xfce4-screensaver/`, using the existing terminal adapter as the
source-build example. No central registry entry was needed.

The maintainer subsequently reported that amd64 worked, while arm64 failed the
final package-layout check because its D-Bus activation service was missing.
The adapter now corrects the upstream pkg-config lookup responsible for that
cross-build difference. Offline regression tests passed after the correction.
The conversation contains no confirmation of a successful real arm64 build after
that fix, or of desktop locking/resume behavior after it. Do not treat the offline
test result as that confirmation.

The originally empty local patch series now contains
[`000-resume-screen-shift.patch`](../packages/rebuild/xfce4-screensaver/patches/000-resume-screen-shift.patch).
The maintainer supplied the application patch; the adapter implementation and
cross-build correction are separate packaging work.

## Source selection and package identity

| Setting | Value |
| --- | --- |
| Adapter directory | `packages/rebuild/xfce4-screensaver/` |
| Release stream | `xfce4-screensaver` |
| Binary package | `xfce4-screensaver` |
| Build architectures | amd64 and arm64 |
| Source suites | trixie, trixie-updates, trixie-security |
| Initially inspected Debian source | `4.18.4-1` |
| Query target for that source | `4.18.4-1+local` |
| Example first published version | `4.18.4-1+local-1` |
| Repository group / Compose Origin | rebuild / `rebuild` |

The source is Debian's packaging of Xfce Screensaver, rather than an upstream Git
checkout or a downloaded binary. The adapter's [sources.list](../packages/rebuild/xfce4-screensaver/sources.list)
contains only the three Trixie source suites. APT selects the current source
candidate from those suites and verifies signed repository metadata and source
checksums. Packaging edits rebuild that current target, not historical releases.

The [query hook](../packages/rebuild/xfce4-screensaver/query) uses workspace-local
APT lists, downloads the source, then runs
[source-metadata.py](../packages/rebuild/xfce4-screensaver/source-metadata.py).
The metadata helper requires exactly one `xfce4-screensaver_*.dsc`, exactly one
Version field and a Debian-valid version. It writes `source-version`,
`source-descriptor` and `targets.tsv` in the workspace. Targets contain the full
Debian source version followed by `+local`, one row per requested architecture.
The framework supplies the final numeric publisher revision.

Revision history comes from stored packages and their embedded stream/checksum
fields. Patch or adapter edits allocate a new revision when a prior artifact has
different inputs. Unchanged inputs reuse their revision and complete missing
architectures. A failed attempt with no stored artifact does not reserve a new
revision. Keep existing packages; no revision counter or sidecar is needed.
See [revision rules](../ARCHITECTURE.md#checksums-and-revision-history).

## Implementation map and build sequence

| File | Responsibility |
| --- | --- |
| [config](../packages/rebuild/xfce4-screensaver/config) | Declare stream and binary package name |
| [query](../packages/rebuild/xfce4-screensaver/query) | Refresh isolated source indexes and download Debian source |
| [source-metadata.py](../packages/rebuild/xfce4-screensaver/source-metadata.py) | Validate source descriptor/version and write targets |
| [build](../packages/rebuild/xfce4-screensaver/build) | Extract, patch, compile, validate and stamp the output |
| [configure-rules.in](../packages/rebuild/xfce4-screensaver/configure-rules.in) | Add the maintainer-mode configure override |
| [install-build-dependencies](../packages/rebuild/xfce4-screensaver/install-build-dependencies) | Install target development libraries in the toolchain image |
| [helper-inputs](../packages/rebuild/xfce4-screensaver/helper-inputs) | Include package helpers in the recipe checksum |
| [patches/series](../packages/rebuild/xfce4-screensaver/patches/series) | Order the maintainer's local patches |
| [tests](../tests/xfce4-screensaver/test_screensaver.py) | Offline regression coverage |

For each requested architecture, the build hook:

1. Requires the exported framework, adapter and workspace paths, maintainer and
   `XFCE_BUILD_ARCH`. The requested architecture must match the toolchain image.
2. Extracts the downloaded Debian source into `WORKSPACE/build-ARCH` with
   `dpkg-source -x`, including Debian's source patches.
3. Imports and applies the local quilt series with `--fuzz=0`. Absolute patch
   names, names containing `..`, and missing files are rejected.
4. Validates the expected upstream D-Bus directory lookup and replaces its plain
   `pkg-config` invocation with `$PKG_CONFIG` in `configure.ac`.
5. Appends the configure override from `configure-rules.in`. It requires Debian
   rules without an existing `dh_auto_configure` command so a changed recipe gets
   reviewed. `--enable-maintainer-mode` permits regeneration of affected files.
6. For arm64, marks the expected `xfce4-dev-tools` build dependency `:native` and
   exports `CC=aarch64-linux-gnu-gcc`. That development tool executes on the amd64
   builder; the linked development libraries belong to the arm64 target.
7. Updates the Debian changelog to the assigned version and builds binaries with
   `dpkg-buildpackage --build=binary --host-arch ARCH -us -uc`.
   `DEB_BUILD_OPTIONS` is `nocheck parallel=2 noautodbgsym` and
   `DEB_BUILD_PROFILES` is `cross nocheck`. Upstream tests are disabled.
8. Validates Package, Version and Architecture, extracts the built `.deb` into
   `WORKSPACE/staged-ARCH`, and checks the fixed required payload below.
9. Calculates Installed-Size in KiB from the final staged tree excluding
   `DEBIAN/`. The control helper rewrites Version, Maintainer, Installed-Size,
   `X-Build-Inputs-SHA256` and `X-Publisher-Stream`, preserving other Debian fields.
10. Emits `xfce4-screensaver_VERSION_ARCH.deb` through the shared package helper.
    The framework validates the output before storage and publication.

Required files, relative to the package root:

```text
usr/bin/xfce4-screensaver
usr/bin/xfce4-screensaver-command
usr/bin/xfce4-screensaver-preferences
usr/libexec/xfce4-screensaver-dialog
usr/share/applications/xfce4-screensaver-preferences.desktop
usr/share/dbus-1/services/org.xfce.ScreenSaver.service
etc/pam.d/xfce4-screensaver
etc/xdg/autostart/xfce4-screensaver.desktop
```

The adapter retains Debian dependencies, PAM configuration, autostart, D-Bus
integration and other packaged resources. The checks establish that named files
exist; they do not test authentication, permissions throughout the payload, or
runtime service activation.

## Local resume patch

Put application patches under `packages/rebuild/xfce4-screensaver/patches/` and
list filenames in `patches/series`, one per line in application order. Blank lines
and lines beginning with `#` are ignored. Keep the patch file and its series entry
together. Each architecture starts with a fresh source extraction.

The current series has one entry: `000-resume-screen-shift.patch`. Reading the
patch shows these intended changes:

- Add a dedicated `request-password-prompt` listener signal and monitor callback
  for the logind wake/resume path, instead of emitting a notification with empty
  fields. The callback requests the unlock prompt when locking is enabled.
- Normalize empty notification fields to NULL. Requesting the password prompt
  can still proceed without creating an empty information bar.
- Create the information icon and labels only when their corresponding fields
  have content, avoiding empty UI elements in the lock window.

These are source-level intentions. The original conversation did not establish
that the patch fixes every resume/display-shift case or verify its behavior with
real authentication. The cross-build fix does not alter this application patch.

Adapter files, including patches and comments, are recipe checksum inputs.
General handoff documentation stays in `docs/` so documenting the work does not
trigger package revisions.

## arm64 failure and cross-build correction

The maintainer reported this exact failure for the initial recipe:

```text
xfce4-screensaver 4.18.4-1+local-1 (arm64): missing usr/share/dbus-1/services/org.xfce.ScreenSaver.service
```

This message comes after `dpkg-buildpackage` and extraction of its result.
Compilation had progressed to a `.deb`; the adapter rejected its incomplete
integration layout before returning a publishable output.

In the inspected [upstream configure.ac](https://sources.debian.org/src/xfce4-screensaver/4.18.4-1/configure.ac/#L255),
`DBUS_SESSION_SERVICE_DIR` is obtained by running plain `pkg-config` for the
`session_bus_services_dir` variable in `dbus-1`, then replacing `/usr/share` with
`${datarootdir}`. The call bypasses the selected `$PKG_CONFIG` tool. Ordinary
library checks elsewhere can therefore succeed while this directory lookup fails.

The amd64 image builds natively. The arm64 image also runs on the amd64 server,
but uses cross-compilers and arm64 development packages. A native pkg-config
lookup can lack the builder's D-Bus development metadata even though the target's
metadata is installed. The empty lookup is the source-based explanation for the
reported missing installation path; the conversation did not capture the failed
container's config.log to independently prove that exact environment state.

The implemented correction substitutes `$PKG_CONFIG` for that plain command,
allowing debhelper's target-aware selection to be used. It applies before
configure regeneration on both architecture paths and has a guard for the
expected source expression. The guard intentionally fails if upstream changes
or fixes that expression; review and remove/adapt the correction at that point.
The final required-service check remains in place.

This is a packaging correction in the build hook, separate from the
maintainer-supplied quilt series. Neither weakening the payload check nor adding
the builder's development libraries is needed to bypass the symptom.

### Why xfce4-terminal was unaffected

The cached `xfce4-terminal` 1.1.4 source was inspected during the investigation.
Its `configure.ac` uses `XDT_CHECK_PACKAGE` for dependencies; the accompanying
macros in `aclocal.m4` invoke `$PKG_CONFIG` for compiler/linker flags. It has no
matching `DBUS_SESSION_SERVICE_DIR` lookup or equivalent D-Bus activation service
to install. Using D-Bus in application code does not require this same configure
expression.

Both adapters need the build-time `xfce4-dev-tools:native` adjustment for arm64,
but only the screensaver needed this D-Bus lookup correction. The general rule
for other source builds is to check that dependency metadata is selected for the
target architecture and that build tools execute on the builder. It does not
justify applying this source substitution to every package. Repack and
byte-preserving redistribution adapters do not run upstream configure scripts;
their validation obligations are different.

See [terminal deployment and verification](xfce4-terminal.md). The cached source
used for comparison was
`build/xfce-live-amd64/xfce4-terminal_1.1.4.orig.tar.bz2`; that ignored cache may
not survive cleanup, so the findings are recorded here.

## Toolchains and deployment

The root [Dockerfile](../Dockerfile) installs the terminal dependency script first,
then the screensaver script in the `rebuild-tools` stage. The latter relies on
the former for the shared compiler, debhelper, quilt and Xfce build tools.
The screensaver script adds gettext and target development packages for
D-Bus GLib, Garcon GTK3, GLib, GTK3, PAM, systemd, Wnck, X11, libxfce4ui,
libxfce4util, xfconf, Xklavier and Xss. The scripts are the exact package list.
Subsequent additions to the shared image do not change the screensaver's source
selection policy.

Separate amd64 and arm64 images avoid conflicting architecture-specific Xfce
packages. Dependency declarations enter image layers before application scripts
and patches, so ordinary patch edits can reuse those layers. Adapters are copied
into images; restarting an old image does not load a changed checkout.

For the ordinary Compose deployment, run from the project root after changing
patches or packaging:

```sh
mkdir -p build/xfce4-screensaver
timeout --kill-after=30s 30m docker compose up -d --build --force-recreate \
    rebuild-amd64 rebuild-arm64 \
    > build/xfce4-screensaver/deploy.log 2>&1
```

To retry only arm64 with the corrected recipe, select just `rebuild-arm64` in
that command. Each service runs its configured rebuild group, not only the
screensaver. Both services share the rebuild repository and signing identity;
the kernel lock serializes their cycles. They wait CHECK_INTERVAL after a complete
cycle. Old packages remain available if this stream fails; other streams continue.

The repository now also supports a host build launcher for adapters requiring
private build dependencies. This screensaver has no `build-dependencies` file
and keeps its direct build path. If the deployment already uses host launchers,
follow [build worker deployment](build-dependencies.md#running-isolated-builds)
rather than starting duplicate Compose coordinators.

Use the existing rebuild output and keyring settings in `.env`. The pkg-config
fix requires no new key, repository migration, revision reset or cleanup.
Compilation runs with the configured publisher UID/GID; root dependency
installation is confined to container image layers. Never use production data or
keys for fixture tests. Rootless Docker ownership mapping remains a separate
verification concern.

After successful publication, clients using the rebuild repository can prefer
this package with an APT preference:

```text
Package: xfce4-screensaver
Pin: release o=rebuild
Pin-Priority: 990
```

Check `apt-cache policy xfce4-screensaver`, then install or upgrade with
`sudo apt install xfce4-screensaver`. The Origin must match the actual rebuild
repository metadata. Follow the [client setup](../README.md#debian-client) for
trusted keys and repository URLs. Desktop checks belong on the target machine.

## Verification and evidence

The original addition passed 16 combined screensaver/terminal adapter tests and
65 framework tests. After the pkg-config correction, the package-specific run
passed 13 tests. Shell syntax and `git diff --check` passed for the implementation.
These are historical results, not a claim that all tests were rerun during this
documentation update or that later unrelated changes have been verified.

Useful retained logs from that work, if the ignored build directory remains:

| Evidence | Path |
| --- | --- |
| Initial combined adapter run, 16 tests | `build/test-run-ar9tC1/regression.log` |
| Initial framework run, 65 tests | `build/test-run-rAac7o/regression.log` |
| Final pkg-config regression run, 13 tests | `build/test-run-52Hsk0/regression.log` |
| Final run coordinator output | `build/xfce4-screensaver/cross-pkg-config-final-tests.log` |
| Shell syntax result | `build/xfce4-screensaver/cross-pkg-config-syntax.log` |
| Diff whitespace result | `build/xfce4-screensaver/cross-pkg-config-diff.log` |
| Inspected Debian packaging archive | `build/xfce4-screensaver/debian.tar.xz` |

The [regression tests](../tests/xfce4-screensaver/test_screensaver.py) cover source
version preservation/order, missing descriptors/versions, requested architecture
selection through the query hook, both build paths, maintainer mode, the native
build-tool adjustment, quilt ordering without fuzz, missing patches, changed
configure rules, missing PAM configuration, package/index Installed-Size and
publisher stream metadata.

The cross-build regression makes plain pkg-config fail while a selected target
tool returns the service directory. It executes the upstream shell lookup fragment
from [dbus-lookup.ac](../tests/xfce4-screensaver/fixtures/dbus-lookup.ac) after the
adapter's correction. The fixture creates the service at the resulting directory
and the test inspects the resulting real `.deb`. Additional tests require a
changed lookup to fail early and a missing service file still to be rejected.

The original tests supplied the service file unconditionally, which hid the
lookup bug. The improved fixture derives its location from the executed lookup.
It still stubs source extraction, quilt, configure coordination and compilation;
it does not execute full Autoconf regeneration, compile upstream C, apply the
actual application patch with real quilt, or test a graphical session. Real
Debian package tools build and inspect the fixture output and its package index.

To rerun the adapter tests, with bounded execution and named logs:

```sh
mkdir -p build/xfce4-screensaver
timeout --kill-after=30s 10m bash tests/run.sh xfce4-screensaver \
    > build/xfce4-screensaver/regression.log 2>&1
```

Wait for completion, then read that log; the runner identifies its detailed
regression log. The signing test is unnecessary for this adapter correction
because signing code did not change. A full suite is a separate intentional run.

## Remaining validation and troubleshooting

The next operational check is a real arm64 build using the corrected image.
Confirm the service file exists in the final package, then check the published
arm64 index and client selection. Real desktop testing should cover ordinary
locking, suspend/resume with locking enabled, the password prompt without an
empty notification, populated notifications, and behavior with locking disabled.
Record exact package versions and outcomes when those checks are performed.

For another failure, save a bounded log snapshot and copy the retained workspace
before recreating the container or allowing a subsequent failure to replace it:

```sh
docker compose logs --no-color --tail 1000 rebuild-arm64 \
    > build/xfce4-screensaver/arm64-failure.log 2>&1
# Replace the example workspace with the path printed by the failed cycle.
docker compose cp rebuild-arm64:/tmp/apt-publisher-EXAMPLE \
    build/xfce4-screensaver/failed-cycle
```

Under `streams/xfce4-screensaver/`, inspect `build-arm64/config.log`, the generated
`data/Makefile` and its `DBUS_SESSION_SERVICE_DIR`, `staged-arm64/`, the raw built
`.deb` and `output-arm64/` where present. A failure before a step may leave its
later paths absent. Verify the loaded recipe includes `$PKG_CONFIG` and check
which tool/configuration was selected during configure. An empty native lookup
alone is not a reason to weaken final payload validation.

For a produced artifact, these read-only checks show its contents and metadata:

```sh
dpkg-deb --contents /path/to/xfce4-screensaver_VERSION_arm64.deb
dpkg-deb --field /path/to/xfce4-screensaver_VERSION_arm64.deb \
    Package Version Architecture Installed-Size X-Publisher-Stream X-Build-Inputs-SHA256
```

If the source lookup, Debian configure rules or native-tool dependency guard
fails, inspect the new Debian source and review the corresponding adjustment.
If a local patch fails, update it against the new source rather than allowing
patch fuzz. If build dependencies change upstream, update the toolchain script
and rebuild its image. Preserve failed logs and useful verified downloads; do
not delete stored repository packages or signing keys to force a retry.
