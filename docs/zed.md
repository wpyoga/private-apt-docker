# Zed packaging and validation notes

## Handoff status and scope

This document preserves the Zed investigation, decisions, implementation, and
verification from the original chat so that maintaining this adapter does not
require that conversation. The handoff was reconciled with the checkout on
2026-11-13. Historical observations below concern **Zed v1.25.3**; they are not a
claim about the latest upstream release or current production deployment.

The adapter was implemented and the user committed it. Current locations are:

| Item | Current location |
| --- | --- |
| Stable repack adapter | `packages/repack/zed/` |
| Stream and binary package | `zed` |
| Offline adapter tests | `tests/zed/test_zed.py` |
| Maintained investigation and handoff | `docs/zed.md` |
| Shared helper declarations | `packages/repack/zed/helper-inputs` |

The initial adapter was `packages/zed/`, and its tests were `tests/test_zed.py`.
The user moved the original notes into `packages/zed/zed.md` after committing the
adapter. Later documentation and repository-group refactors placed them at the
current paths above. **Use the actual checkout paths, not those in old chat
commands.** The current notes are outside `packages/` and therefore do not
themselves affect the adapter recipe checksum.

Relevant Git history, available locally:

- `6d0ff50` — initial Zed package adapter.
- `40745dc` — shared adapter helpers; Zed's query and build now use them.
- `61fc6ab` — package documentation refactor.
- `c1d5691` — repository split placing Zed in the repack group.

The implementation and historical container installation checks are complete.
The user intended to install the package on a laptop and test the desktop.
**This conversation contains no report of that laptop test succeeding or
failing.** ARM execution, GPU rendering, and practical X11/Wayland compatibility
must therefore remain unconfirmed until new results are recorded here.

The original session did not publish a production repository, deploy a new
publisher container, install Zed on the host/laptop, or commit changes on the
user's behalf. Later deployment state must be established independently.

## Decisions and alternatives considered

The original request was to find an easy Debian installation and then integrate
Zed with this private APT publisher. At the time of investigation, the official
Linux distribution provided an installation script and binary tarballs; no
official APT repository or official `.deb` was found. This is historical context,
not a fresh upstream packaging survey.

The user chose **stable only**, **Debian 13 Trixie**, and support for the existing
amd64/arm64 framework selection. Preview/nightly streams and source compilation
were not requested. This adapter creates a Debian package from official binaries;
it is neither byte-preserving `.deb` redistribution nor a source rebuild.

The proposed package name was initially `zed-editor`, to distinguish unrelated
programs named zed. The user questioned that choice. The implemented name is
**`zed`**, and the public command is also `zed`. Debian's ZFS event daemon is
packaged as `zfs-zed`; the shared program name alone was not evidence that the
editor package must be renamed or conflict with that package. Do not add a broad
`Conflicts: zfs-zed` merely because the daemon is also called zed. Establish
actual file ownership conflicts if one is reported.

The first proposal retained upstream's private libraries for simplicity. The
user explicitly rejected that default: use ordinary Debian libraries wherever
compatible, reserve private libraries for demonstrated incompatibilities, and
check the ABI rather than assuming matching filenames are sufficient. The
implemented package installs **none of the nine bundled shared libraries**.

The user initially preferred avoiding a launcher. After investigating global
configuration and the amount of session integration required to supply one
environment variable, the user explicitly chose the small wrapper. This is the
accepted implementation; do not resume the rejected profile/session integration
approach merely to remove that wrapper.

The closest existing model was Codex: official prebuilt archives, integrity
checks, staging, and generated Debian metadata. Ghostty started from a community
`.deb` whose packaging integration could be preserved, which was unavailable for
Zed. GIMP required AppImage/SquashFS extraction, more library auditing and
multiple outputs. Zed retains dependency auditing but needs only one output
package and no AppImage extraction. These comparisons describe those adapters
at the time of the decision, not a requirement that their later implementations
remain identical.

## Source and package layout

The `zed` stream follows the latest stable release of
[zed-industries/zed](https://github.com/zed-industries/zed/releases/latest).
Official `zed-linux-x86_64.tar.gz` and `zed-linux-aarch64.tar.gz` archives map to
Debian amd64 and arm64. GitHub's asset SHA256 digest is required and verified.
The Debian package is an unofficial repackaging for Debian 13 (Trixie).

The adapter expects one fixed `zed.app/` tree containing the CLI, editor,
desktop entry, two icons, license notices, and nine known bundled libraries.
Links, special files, extra payload files, and changed library requirements fail
the build. Architecture and ELF dependency checks never execute target code.
The existing publisher selects Debian revisions and publishes one `zed` package
per architecture; no framework changes are needed.

The current query uses the shared GitHub helper to fetch
`https://api.github.com/repos/zed-industries/zed/releases/latest`. It rejects
drafts, prereleases, malformed asset lists, duplicate selected assets, missing or
invalid SHA256 digests, and non-HTTPS or whitespace-containing asset URLs. The
adapter separately requires a `vMAJOR.MINOR.PATCH` tag and strips the initial `v`
for the upstream version. Exact asset names select the two architectures.

Query records the release timestamp in `WORKSPACE/release-date`, writes
newline-terminated `VERSION<TAB>ARCH` rows to `WORKSPACE/targets.tsv`, and stores
selected download metadata in `WORKSPACE/assets.json`. The latter is an adapter
convention, not a new framework API. Each architecture entry has these fields:

```json
{
  "amd64": {
    "version": "1.25.3",
    "name": "zed-linux-x86_64.tar.gz",
    "url": "https://github.com/zed-industries/zed/releases/download/v1.25.3/zed-linux-x86_64.tar.gz",
    "sha256": "35f9115acd8b4c3bea6ed20f7c9b6ec8f1d2c2dd5a1cc438d552167b5ed4b342"
  }
}
```

Missing architecture assets produce warnings and no target for that
architecture. Existing stored packages remain available, and discovery can fill
the missing architecture on a later cycle. A malformed release or failed
download is an error, not an empty successful result.

`build VERSION ARCH OUTPUT_DIR` receives the publisher-assigned Debian version,
such as `1.25.3-1`. It requires the exported framework/adapter/workspace,
publisher-stream, checksum, and maintainer context. It checks that the selected
asset's version and name agree with its arguments, verifies the archive hash,
validates the archive before extraction, and inspects its ELF files afterward.
It emits exactly `zed_VERSION_ARCH.deb` into the supplied output directory.

The archive policy is intentionally strict: one `zed.app/` root, exactly the
known payload files, and ordinary directories/regular files only. Duplicate
paths, traversal, links, special files, missing required files, or extra payload
files require a maintainer review. There is no alternate-root search or implicit
support for a new upstream layout. Unexpected empty directories are not a
separate exact-directory whitelist.

The retained executables are `/usr/lib/zed/bin/zed` and
`/usr/lib/zed/libexec/zed-editor`. Their relative paths preserve the CLI's editor
discovery. The upstream private-library RPATH is removed with patchelf. No
bundled shared libraries are installed. Desktop files and icons use standard
`/usr/share` locations; upstream license notices are in `/usr/share/doc/zed/`.

The files installed for desktop integration are
`/usr/share/applications/dev.zed.Zed.desktop` and the `zed.png` icons under
`/usr/share/icons/hicolor/{512x512,1024x1024}/apps/`. The validator requires the
upstream desktop entry's `TryExec=zed`, `Exec=zed %U`, `Exec=zed --new %U`, and
`Icon=zed` lines. It preserves file/URL arguments and both desktop actions.
There are no custom maintainer scripts or settings migration steps.

The shared `render_control` helper calculates `Installed-Size` in KiB from the
final staged tree excluding `DEBIAN/`, escapes template values, and writes the
assigned version, architecture, configured `MAINTAINER`, input checksum, and
stream metadata. `build_deb` uses root ownership in the archive and gzip
compression. It does not require building as root. `helper-inputs` declares
`adapter/package.sh` and `adapter/github.sh`, so changes to those shared helpers
participate in the recipe checksum. The framework retains responsibility for
revisions, incomplete-build resumption, storage, indexing, and signing.

## Debian libraries and the libXdmcp compatibility question

The inspected v1.25.3 archives bundle these ordinary shared libraries:

| Upstream library | Debian package |
| --- | --- |
| `libX11-xcb.so.1` | `libx11-xcb1` |
| `libXau.so.6` | `libxau6` |
| `libXdmcp.so.6` | `libxdmcp6` |
| `libxcb.so.1` | `libxcb1` |
| `libxcb-xkb.so.1` | `libxcb-xkb1` |
| `libxkbcommon.so.0` | `libxkbcommon0` |
| `libxkbcommon-x11.so.0` | `libxkbcommon-x11-0` |
| `libstdc++.so.6` | `libstdc++6` |
| `libbsd.so.0` | `libbsd0` |

Only libraries directly required by retained executables contribute to the
generated `Depends`. Debian packages supply their own transitive dependencies.
GLib, ALSA, glibc, and GCC support libraries also come from Debian. Vulkan,
Wayland, font discovery, certificates, and URL opening have explicit runtime
dependencies because ELF `DT_NEEDED` does not describe every runtime load.
Desktop portal packages and a Vulkan driver are recommended; a desktop-specific
portal backend and a working Vulkan-capable GPU remain client requirements.

**Important compatibility note:** in both official architectures, the bundled
chain is `Zed -> libxcb -> libXdmcp -> libbsd`. Debian 13's `libXdmcp.so.6` does
not have a `DT_NEEDED` entry for `libbsd.so.0`. Consequently, `libbsd0` is neither
a direct Zed dependency nor part of this replacement X11 dependency chain.
This is a difference between builds of libXdmcp, not evidence that libbsd is a
Zed-specific library or that it should be bundled independently.

`libbsd0` supplies BSD compatibility functions on Linux; it is not unique to
Zed. In the inspected bundle it was pulled in by upstream's build of libXdmcp,
not directly by the editor. ELF `DT_NEEDED` inspection on **both** architectures
showed:

```text
Upstream libXdmcp.so.6:
    libbsd.so.0
    libc.so.6
    (also ld-linux-aarch64.so.1 on arm64)

Debian 13 libXdmcp.so.6:
    libc.so.6
    (also ld-linux-aarch64.so.1 on arm64)

Debian libxcb.so.1:
    libXau.so.6
    libXdmcp.so.6
    libc.so.6
    (also ld-linux-aarch64.so.1 on arm64)
```

Thus libXdmcp and libXau arrive through Debian's libxcb package dependencies,
while libxcb-xkb arrives through Debian's keyboard-library dependencies.
The observed replacement chain does not require libbsd. This does **not** prove
which upstream build option or implementation accounts for the difference;
that cause was not established. The user's concern about behavioral
compatibility was deliberately kept open for a real desktop test.

The dependency map still recognizes the bundled/transitive SONAMEs, including
`libbsd.so.0`, so changed imports can be inspected. The inspector checks all
known bundled ELF files but adds dependencies only from the retained CLI and
editor. If a future retained executable directly needs libbsd, its map entry
can contribute `libbsd0`; the policy is based on actual imports rather than a
permanent exclusion of that library.

The current generated direct dependencies for the inspected real binaries are
`libasound2t64`, `libc6 (>= 2.41)`, `libgcc-s1 (>= 14)`,
`libglib2.0-0t64 (>= 2.84)`, `libstdc++6 (>= 14)`, `libx11-xcb1`, `libxcb1`,
`libxkbcommon-x11-0`, and `libxkbcommon0`. The build additionally declares
`ca-certificates`, `libfontconfig1`, `libfreetype6`, `libvulkan1`,
`libwayland-client0`, and `xdg-utils`. Recommendations are `git`,
`mesa-vulkan-drivers | vulkan-icd`, `xdg-desktop-portal`, and
`xdg-desktop-portal-backend`.

The version floors express the chosen Trixie baseline; the investigation did
**not** prove that every executable needs those exact minimum package versions.
Likewise, broad upstream Linux/glibc support does not establish that this
Debian-13-specific package supports older Debian releases. Before changing a
floor, investigate actual symbols, required features/fixes, and Debian patches.

Initial v1.25.3 investigation found all strong imported symbols, including
symbol versions, in the Debian runtime on both architectures. The checks used
the Trixie amd64 host and checksum-verified Debian arm64 packages. The amd64
editor also passed `ldd -r` without bundled libraries and the CLI reported the
expected version. These are ABI and loader checks, **not proof of complete X11
or Wayland behavior**. Using Debian's libXdmcp remains subject to the laptop
desktop test below. Do not silently restore upstream libraries if that test
fails: record the failure and establish which library or build option matters.

The adapter's dependency map rejects unknown SONAMEs. It also rejects retained
binaries requiring GLIBC, GLIBCXX, or CXXABI versions newer than the declared
Trixie baseline. It does not reproduce the investigation's full symbol-provider
comparison on every build; new releases still need desktop validation when
upstream library assumptions change.

The production inspection checks little-endian ELF64 headers and machine IDs
62 (amd64) or 183 (arm64), known `DT_NEEDED` SONAMEs, and these symbol-version
ceilings: GLIBC 2.41, GLIBCXX 3.4.33, and CXXABI 1.3.15. Only retained
executables are subject to the symbol ceilings, because upstream libraries are
discarded. This is a targeted compatibility guard, not a complete dynamic-loader
simulation or an audit of every library loaded through `dlopen`.

## Exact historical source and ABI evidence

The inspected upstream release was `v1.25.3`, published 2026-10-23. Its matching
source commit was `8dd255c3eafb5231056fe4e6f601cedd011f1c93`. Both archives
were downloaded from that release and matched these GitHub asset digests:

| Archive | SHA256 |
| --- | --- |
| `zed-linux-x86_64.tar.gz` | `35f9115acd8b4c3bea6ed20f7c9b6ec8f1d2c2dd5a1cc438d552167b5ed4b342` |
| `zed-linux-aarch64.tar.gz` | `776b3a5e39f1218eacabe1e9fa3859b7a6dda2653522d8a3992a9ab0f2184058` |

The user requested a local source checkout rather than fetching source files
individually. A shallow checkout of the matching tag was created at
`build/zed-investigation/source/`. Relevant upstream files were:

- `script/bundle-linux` — bundle construction and choice of private libraries.
- `script/install.sh` — normal per-user installation and desktop integration.
- `crates/cli/src/main.rs` — relative discovery of `libexec/zed-editor`.
- `crates/auto_update/src/auto_update.rs` — updater gating and Linux installation.
- `crates/paths/src/paths.rs` — per-user settings paths.
- `crates/settings/src/settings.rs` and `assets/settings/default.json` — embedded
  defaults and the automatic-update setting.
- `crates/gpui_linux/Cargo.toml` — Linux display/backend dependencies.

The one-off ABI investigation compared strong undefined dynamic symbols from
each executable with Debian library exports, preserving symbol-version names.
It used the Trixie amd64 host and downloaded/extracted arm64 Debian packages;
no ARM executable was run. Its result was:

| Architecture | CLI strong imports | Editor strong imports | Missing imports |
| --- | ---: | ---: | ---: |
| amd64 | 143 | 626 | 0 |
| arm64 | 142 | 620 | 0 |

For the replaced direct libraries, the editor imported 1 symbol from
libX11-xcb, 16 from libxcb, 3 from libxkbcommon-x11, and 26 from libxkbcommon.
It imported 74 versioned/unversioned symbols from libstdc++ on amd64 and 70 on
arm64. Each used symbol was available from the corresponding Debian provider.
The editor's highest GLIBCXX requirement was 3.4.29 on amd64 and 3.4.26 on arm64;
the observed maximum GLIBC requirement across the original binaries and bundle
was 2.30. These measurements are specific to the inspected release.

The arm64 Debian packages included libstdc++6/libgcc-s1 14.2.0-19,
libbsd0 0.12.2-2, libX11-xcb1 2:1.8.12-1, libXau6 1:1.0.11-1,
libxcb1/libxcb-xkb1 1.17.0-2+b1, libXdmcp6 1:1.1.5-1, and
libxkbcommon0/libxkbcommon-x11-0 1.7.0-2. The direct-runtime comparison also
used libc6 2.41-12+deb13u4, libglib2.0-0t64 2.84.4-3~deb13u5, and
libasound2t64 1.2.14-1+deb13u1. Package SHA256 values were checked against the
downloaded Trixie arm64 package index before extracting them.

This established that the used exported interfaces were present. It did not
establish semantic equivalence of every replaced function, exercise GPU/display
drivers, or validate all optional/dynamically loaded integrations. Preserve that
distinction when diagnosing a later desktop failure.

## Updates

`/usr/bin/zed` is a small Bash wrapper. It exports
`ZED_UPDATE_EXPLANATION='Update Zed using APT.'` and execs the real CLI, forwarding
arguments and exit status. Both desktop launch actions use `zed` and therefore
the same wrapper. The variable disables automatic checks and makes manual
update checks display the APT explanation. No shell profile or session-wide
environment files are installed, and no updater machine code is patched.

Zed has no system-wide settings layer in this release. Its
`global_settings.json` is per-user, and `auto_update: false` alone does not
disable the manual update action. The unmodified updater can otherwise install
a second copy under `~/.local`, even when the original binary is under `/usr`.
Running internal executables directly bypasses the wrapper's update policy.

The matching upstream updater first checks a compile-time
`option_env!("ZED_UPDATE_EXPLANATION")`, then the runtime environment variable.
Either prevents automatic polling. The manual update action checks the same
value and displays it with a package-manager explanation instead of starting
an update. The wrapper exports a fixed nonempty message and overrides a
preexisting value before `exec`, which preserves argument boundaries, normal
signal handling, and the CLI's exit status.

The source investigation ruled out these alternatives for the implemented
package:

| Alternative | Finding and reason it was not selected |
| --- | --- |
| `/etc/zed` settings | No such system-wide settings layer was found in the matching source. |
| `global_settings.json` | Still under the user's config directory; not a package-wide policy file. |
| `auto_update: false` | Stops automatic polling but leaves the manual update path available. |
| Edit a shipped default JSON file | Release defaults are embedded/compressed, not loaded from an installed editable defaults file. |
| `environment.d` | Can set a user-service environment, but does not cover every SSH/session/process launch path or already-running processes. |
| Profile snippet plus desktop-entry `env` commands | Adds several integration points and still depends on environment inheritance; user chose one wrapper instead. |
| Set the variable during compilation | Supported upstream, but would require rebuilding Zed solely for this policy. |
| Patch the binary to supply a default | Last resort only; replacing the variable-name string does not change its default, and changing embedded `auto_update` alone would not disable manual updates. No updater machine-code patch was implemented. |

The ordinary upstream Linux installer places a bundle under `~/.local`, and
the updater has a fallback destination there when its running executable does
not end in the expected `zed.app/libexec/zed-editor` bundle suffix. Installing a
root-owned system package is therefore insufficient to guarantee APT-only
updates: it can otherwise create a separate per-user bundle. This observation
motivated disabling both update paths through the wrapper.

User language servers, extensions, agents, and other developer tools downloaded
by Zed are separate from replacing the editor application. The wrapper was not
intended to disable these features or to change telemetry, accounts, credentials,
or collaboration defaults.

## Validation and laptop acceptance

Offline regression tests use small real ELF fixtures for both architectures,
inspect ARM headers without executing them, build real Debian packages, and
check the published `Installed-Size`. They cover release validation, archive
layout and links, dependencies, symbol baseline changes, the updater wrapper,
desktop actions, revision reuse, and later availability of an architecture.
Use the current package selector from the project root:

```bash
mkdir -p build/zed-validation-logs
timeout 300 bash tests/run.sh zed \
    > build/zed-validation-logs/offline.log 2>&1
```

Wait for completion, then inspect the log and command exit status. Preserve a
failure log rather than streaming output for monitoring. The historical
`python3 -m unittest discover -s tests -p test_zed.py -v` command referred to the
old flat tests layout and should no longer be copied for this checkout.
Package-specific work does not require a signing test. Run signing checks when
signing changes or when deliberately running the full suite.

The original 13 Zed regression tests all passed. They covered:

1. Requested-architecture selection and release timestamps.
2. Malformed/unstable release metadata and duplicate selected assets.
3. Missing or invalid digests and invalid URLs.
4. Package payload, ownership/modes, dependencies, stripped RPATH, publisher
   fields, and `Installed-Size` in the package and index.
5. Wrapper argument boundaries, update environment, and exit status.
6. Missing architectures appearing later, repeated updates preserving bytes,
   and recipe changes allocating a new revision.
7. Digest failures storing no package.
8. Unknown library requirements, including in discarded bundled libraries.
9. Wrong ELF architectures.
10. A new symbol baseline beyond Trixie.
11. Missing required files and changed desktop entry integration.
12. Links rejected before extraction.
13. Unexpected archive roots and path traversal.

Local v1.25.3-1 packages were built from the verified official archives for both
architectures. The amd64 package passed APT installation in an isolated Debian
13 container, `ldd -r` against system libraries, unprivileged `zed --version`,
desktop-file validation, and APT removal. Desktop validation emitted only an
upstream category hint. No arm64 execution or GPU/desktop test has been done.
The local test packages use a generic validation maintainer; publisher builds
use the operator's configured `MAINTAINER`.

Historical output filenames were `zed_1.25.3-1_amd64.deb` and
`zed_1.25.3-1_arm64.deb`, approximately 84 MiB and 80 MiB respectively. Their
`Installed-Size` values were 228152 KiB (amd64) and 187916 KiB (arm64).
These were locally built validation artifacts, not evidence of production
publication or of the current recipe checksum/revision.

The disposable installation check reused an existing local Debian 13 publisher
image, installed the amd64 package with APT and recommendations disabled, then
checked system-library relocation, CLI launch, desktop metadata, absence of
bundled `.so` files, and removal of the public/internal CLI paths. It was an
isolated installation, not a clean official `debian:trixie-slim` image. The
first invocation tried `zed --version` as root and Zed correctly refused it.
The corrected check ran the CLI as unprivileged `nobody` and passed. That root
refusal was not an ABI failure and was not bypassed with `ZED_ALLOW_ROOT`.

The wider historical run reported 96 tests, two GIMP-help failures, and seven
GIMP skips because SquashFS tools were unavailable. Other sessions were editing
GIMP/framework files concurrently; those results must not be presented as
current failures or attributed to Zed. The real signing test initially failed
because sandboxed GPG could not start its agent/socket. The user questioned its
relevance, and the signing rerun was dropped because the Zed work did not change
signing. No successful signing-test result is claimed for this work.

Investigation downloads, the matching source checkout, and local validation
outputs belong under ignored `build/zed-investigation/`. Do not use production
repository data or signing keys for these checks. On 2026-11-13,
`build/zed-investigation/` was **absent** from this checkout. The source checkout,
archives, ABI audit script/results, Debian-package index and extracted ARM
libraries, build workspaces, test `.deb` files, and disposable installation
script described above therefore cannot be assumed to remain available. Their
historical paths included:

```text
build/zed-investigation/
  source/                         matching upstream source checkout
  zed-linux-x86_64.tar.gz         official amd64 archive
  zed-linux-aarch64.tar.gz        official arm64 archive
  check-abi.py                    one-off symbol-provider comparison
  abi-report.json                symbol counts and missing-symbol results
  debian-trixie-arm64-Packages.xz Debian package metadata used for verification
  arm64-packages.json             selected package URLs, versions, and hashes
  debian-arm64/                  extracted Debian runtime files
  package-build/                 local query metadata/extraction/staging
  packages/                      the two validation .deb files
  install-test/check.sh           disposable amd64 installation test
```

The handoff document is durable evidence of reported results, not a substitute
for retaining raw logs when reproducing or investigating a new failure. New
documentation-inspection/check logs from this handoff live separately under
`build/zed-handoff-logs/` and contain no new package-runtime test results.

After installation from the private repository, or using
`sudo apt install ./zed_VERSION_amd64.deb` for a local package, test on the laptop:

1. Run `zed --version` and `ldd -r /usr/lib/zed/libexec/zed-editor`.
2. Open Zed from the desktop menu and the terminal; open a file whose name
   contains spaces and exercise the desktop's New Workspace action.
3. Test X11 and Wayland where available. Check keyboard input, clipboard,
   fonts, file dialogs, URL opening, and rendering. For an X11 launch from a
   Wayland session, use `WAYLAND_DISPLAY='' zed --foreground` with XWayland
   available. This is the pending practical libXdmcp compatibility check.
4. Select Check for Updates and confirm that it displays the APT explanation.
   Check that no second application bundle is created under `~/.local/`.
5. Confirm `apt show zed` reports an installed size and that removal leaves
   personal settings intact.

Publisher container rebuilds and production publication are separate deployment
steps. Offline tests do not establish GUI functionality on the target laptop.

## Resuming after this chat is deleted

1. Read this document, the current adapter, its tests, `AGENTS.md`, and the
   relevant framework contract. Check `git status` first: other streams and
   documentation may be under active development.
2. If only notes or links change, perform documentation checks. Do not download
   releases, rebuild packages, or rerun signing solely for a documentation edit.
3. If changing packaging, run `bash tests/run.sh zed` with a named log and bounded
   timeout. Use existing verified artifacts where available. Keep downloads,
   source checkouts, and staging under ignored `build/`; do not scatter them in
   `/tmp` or outside this checkout. The user's explicit preference was one
   easily cleaned investigation directory.
4. For the original issue, obtain the user's laptop result before assuming a
   further packaging fix is needed. Record Zed and Debian versions, architecture,
   session type, GPU/driver, observed behavior, relocation output, and relevant
   Zed log excerpts. Distinguish library-load errors from Vulkan, portal, font,
   credential-service, or session problems.
5. If ABI rechecking is needed, use the source matching the tested binary tag
   and compare actual symbol requirements against the intended Debian providers
   for each architecture. The release hashes above identify the historical
   inputs; do not apply them to a different release. Clone upstream locally
   rather than collecting disconnected source fragments.
6. Preserve the system-library policy. If a reproducible libXdmcp problem is
   found, compare Debian and upstream builds and isolate the cause before
   retaining a private library. Document any exception and the reason it is
   necessary. Do not add libbsd merely because upstream bundled it.
7. Run host coordinators as the host user. Containers writing bind-mounted
   workspaces need the host UID/GID; root installation belongs in disposable
   container layers. Keep failure logs and useful sources/downloads; remove
   superseded staging only when no pending issue needs it. Never treat stored
   repository packages or signing material as temporary cleanup targets.
8. If deployment is requested, follow the current repack service and repository
   instructions in the README. Adapter files are copied into the publisher
   image, so checkout edits alone do not update a running publisher. Use the
   configured operator maintainer and signing identity; do not publish old
   generic-maintainer validation packages as if they were current builds.

The open acceptance items are the laptop desktop test, native arm64 runtime
testing if needed, and any separately requested production deployment. Nothing
in the original conversation authorizes inventing a successful outcome for
those items.
