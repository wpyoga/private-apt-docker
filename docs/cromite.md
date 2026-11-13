# Cromite packaging and verification

## Handoff status and agreed scope

This document preserves the Cromite planning, implementation, static verification,
and subsequent profile-directory discussion from the October–November 2026 chat.
It was reconciled with the checkout on 2026-11-13. The maintained implementation
is in `packages/repack/cromite/`; early work used `packages/cromite/` before the
repository was organized into groups. Tests remain in `tests/cromite/`.
Cromite belongs to the repack repository, not rebuild or byte-preserving
redistribution. Its stream ID and sole binary package name are both `cromite`.

The user chose official amd64 binaries only, keeping bundled runtime libraries,
and explicitly requested removal of `.pak.info` files. Source-building Chromium
or adding Linux arm64 support was not selected. After a Docker permission request,
the user requested a static implementation only. Do not treat the original plan's
container installation or browser smoke test as completed or still authorized
work to execute automatically.

The adapter, offline tests, and static package build were completed. The later
proposal to change profile/cache directories was discussed but never implemented
or approved as a change. The current launcher still preserves upstream defaults.
No Cromite deployment, live publication, or client installation was performed by
this chat; the user's later directory observations do not establish how their
local installation was obtained.

For resuming work, read this document, the current adapter and tests, and inspect
the working tree before editing. Other browser and repository work has proceeded
independently. General notes belong here, outside checksum-bearing adapter files.

## Source and release policy

The `cromite` stream repackages official Linux binaries from
[uazo/cromite](https://github.com/uazo/cromite), not community builds or a local
Chromium source build. Clients install it with `sudo apt install cromite` after
an operator rebuilds the publisher image and publishes an update cycle.
This project is not an official Cromite APT repository.

Query follows GitHub's latest stable release, rejecting drafts and prereleases.
Tags must be `vMAJOR.MINOR.BUILD.PATCH-COMMIT`, with a full lowercase 40-character
commit hash. The exact asset is `chrome-lin64.tar.gz`; its GitHub SHA256 digest is
required and checked before extraction. Duplicate assets, bad metadata, download
errors and checksum mismatches fail the stream rather than producing empty results.

The upstream version is `MAJOR.MINOR.BUILD.PATCH+YYYYMMDDhhmmss.gitCOMMIT`, using
GitHub's publication time normalized to UTC. The framework appends its numeric
Debian revision. This distinguishes upstream rebuilds of the same Chromium
version and orders them by publication time. The commit hash breaks ties but
is not itself chronological. A release timestamp change changes package identity.
Normal publisher checksum, revision reuse, incomplete-build resumption and
artifact retention rules apply without new counters or sidecars.

Only amd64 Linux is available upstream. An arm64 request warns and produces no
target; Android arm64 APKs are never substituted. An arm64 build invocation fails.
Supporting a future Linux arm64 artifact requires an explicit adapter update.

## Payload and integration

The archive must have the fixed `chrome-lin/` root, browser, sandbox and crashpad
executables, resources, ICU data, snapshot, icon, development wrapper, six shared
libraries, and `locales/en-US.pak`. Other locale `.pak` and `.pak.info` files are
accepted. Unknown payload files, duplicate paths, traversal, absolute paths,
links and special files fail validation before extraction.

The package installs its private payload in `/usr/lib/cromite`. It preserves
runtime `.pak` files and all six libraries. Every `.pak.info` file is omitted:
these are resource-build annotations rather than runtime locale payloads.
No other locale files are trimmed and no binary stripping is performed.

The upstream development wrapper is replaced with `/usr/bin/cromite`, which
sets the private library path and desktop identity, then forwards arguments
unchanged. It does not generate desktop entries, create compatibility links,
run `ldd`, change defaults, migrate profiles, or install an updater. Cromite's
native profile-path behavior remains in effect; callers may explicitly choose
`--user-data-dir`. The package supplies `cromite.desktop` with web/HTML MIME
associations and a 48-pixel icon. Users choose their default browser themselves.
Updates come through APT; the package adds no independent update service.

## Profile and cache directories: corrected finding

The user observed Cromite using `~/.config/chromium` and `~/.cache/chromium`.
That is the relevant behavior for their build. An earlier chat answer claiming
that Cromite defaults to `~/.config/cromite` was incorrect: it relied on a
[dictionary discussion](https://github.com/uazo/cromite/discussions/1756)
mentioning that path, which does not prove the binary's default. Do not carry
that answer forward as a packaging assumption. Upstream also has an issue about
[renaming Chromium's config directory](https://github.com/uazo/cromite/issues/1578).
An issue's closed status alone does not prove a particular release changed it.

The checked-in launcher sets only `CHROME_WRAPPER`, `CHROME_DESKTOP`, and the
private `LD_LIBRARY_PATH`, then executes `/usr/lib/cromite/chrome` with the
original arguments. Neither the executable name, Debian package name, installed
directory, nor `CHROME_DESKTOP=cromite.desktop` renames the browser's profile.
The launcher supplies no profile/cache flags or environment defaults.

Chromium's Linux default chooses its product basename in
`chrome/common/chrome_paths_linux.cc`. An unmodified Chromium product basename
is `chromium`. Normal locations therefore include:

| Browser/build | User data root | Corresponding cache root |
| --- | --- | --- |
| User-observed Cromite build, without overrides | `~/.config/chromium` | `~/.cache/chromium` |
| Thorium with its upstream product-path change | `~/.config/thorium` | `~/.cache/thorium` |
| Proposed Cromite launcher policy, not implemented | `~/.config/cromite` | `~/.cache/cromite` |

These are roots; profiles such as `Default` have subdirectories beneath them.
The usual `~/.config` base can be overridden by `CHROME_CONFIG_HOME`, otherwise
`XDG_CONFIG_HOME`. Chromium also accepts `CHROME_USER_DATA_DIR` for the complete
user data root; explicit `--user-data-dir` takes precedence over that variable.
Cache location is derived from the profile: a profile beneath the normal XDG
config tree maps to the matching relative path beneath the XDG cache tree.
Outside that tree, Chromium may keep caches alongside the profile instead.
An explicit `--disk-cache-dir` selects the disk-cache path; it is not a universal
override for every kind of cached or generated profile data. See
[Chromium's user data documentation](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/user_data_dir.md).

In particular, the observed Cromite profile can overlap a regular Chromium
installation. It does not normally overlap Thorium's separate `thorium` root.
Explicit flags, environment variables, or filesystem links can change that.
Open `chrome://version` and read **Profile Path** to identify the actual active
profile; its parent is the user data root. No browser was launched to perform
that check during the static investigation.

### How Thorium implements separate directories

Thorium changes the default in source. In
[`chrome/common/chrome_paths_linux.cc`](https://github.com/Alex313031/thorium/blob/main/src/chrome/common/chrome_paths_linux.cc),
`GetDefaultUserDataDirectory()` assigns `data_dir_basename = "thorium"` in the
non-Google-branded branch. `GetUserCacheDirectory()` retains the normal mapping
from the config tree into the cache tree, giving the matching `thorium` cache
name. This source change requires compiling the browser, and applies even when
the executable is launched directly rather than through the package wrapper.
The linked source is a moving branch, not a proof of every historical artifact.

Our `packages/repack/thorium-browser/launcher.in` preserves that normal compiled
default. It reads `thorium/thorium-flags.conf`, but does not normally inject a
user-data directory. Its explicit `--temp-profile` convenience option is an
exception: it supplies a temporary user-data directory and cache directory.
The CPU/source variants intentionally share Thorium's normal profile; see
[Thorium notes](thorium.md) for their independent packaging decisions.

### Options discussed for Cromite, not implemented

| Layer | Mechanism | Consequence |
| --- | --- | --- |
| Source | Change the product basename to `cromite` and rebuild | Gives the binary its own default even for direct execution; requires a Chromium source-build workflow |
| Launcher | Supply profile/cache arguments, or a user-data environment default | Works with official prebuilt binaries, but only when using that launcher |
| Debian package | Ship the changed launcher | Delivers the policy through terminal and desktop integration; package metadata alone cannot change compiled defaults |

For this repack, the practical proposal was to default the launcher to
`--user-data-dir="${XDG_CONFIG_HOME:-$HOME/.config}/cromite"` and, if desired,
`--disk-cache-dir="${XDG_CACHE_HOME:-$HOME/.cache}/cromite"`. These expressions
describe a proposal, not the current executable or a finalized precedence policy.
When the profile is in the normal XDG config tree, the cache mapping can already
produce the corresponding `cromite` cache location without a second flag.

A future change must deliberately preserve explicit user arguments and intended
environment overrides. Decide whether changing a user-supplied profile should
also change the cache default, respect both `--option=value` and split argument
forms, preserve spaces and argument boundaries, and test terminal and desktop
launches through the same wrapper. Avoid changing global XDG variables for this
purpose: they affect other applications, and CHROME_CONFIG_HOME changes a base
directory rather than the compiled product basename.

Changing defaults starts a different profile; it does not migrate existing
bookmarks, cookies, passwords, extensions, or settings. Profile migration and
compatibility with Chromium data have not been validated or authorized. Do not
automatically move/delete `chromium` directories or bypass instance locks. A
profile policy change belongs in a new reviewed adapter revision, accompanied
by documentation and behavior tests. No such revision was made in this chat.

## Sandbox and permissions

Files have ordinary read/execute permissions; setuid, setgid and sticky bits are
cleared. The package relies on Chromium's unprivileged user-namespace sandbox.
It never adds `--no-sandbox`, grants the bundled helper setuid privileges, or
changes host namespace/AppArmor settings. Restricted environments may need
operator configuration. Debian 13 is the target; Ubuntu is not validated.

## Libraries and licensing

All ELF files are inspected without executing them. ELF64 little-endian amd64
is required. External SONAMEs map to explicit Debian dependencies in the adapter;
new imports fail for maintainer review. GLIBC, GLIBCXX and CXXABI requirements
must fit Debian 13's symbol ceilings. The map is independent of host libraries.

The Qt5/Qt6 shims remain bundled but their Qt dependencies are optional suggestions.
Qt widget packages pull their matching core and GUI libraries. Font libraries,
certificates and xdg tools are dependencies; GTK, fonts and Vulkan support are
recommended. VA-API and PulseAudio are suggestions. These runtime-loaded features
need desktop validation beyond ELF inspection. Private Vulkan/EGL/GLES components
remain upstream versions; this is not a system-library substitution experiment.

The package records its selected tag and corresponding source/patch location,
GPL terms, the system GPL-3 text location, and Chromium's `chrome://credits`
notices. No separate licensing files are present in the inspected Linux archive.
The browser's embedded notices remain intact. Binary redistribution must retain
applicable upstream and third-party license obligations.

`Installed-Size` is calculated in KiB after staging and metadata removal, excluding
`DEBIAN/`. Publisher metadata and global `MAINTAINER` are rendered with the shared
helpers. No Dockerfile or framework changes are required.

## Implementation map and build data flow

All production paths below are relative to `packages/repack/cromite/`:

| File | Responsibility |
| --- | --- |
| `config` | Declare `RELEASE_STREAM=cromite` and `BINARY_PACKAGES=cromite` |
| `query` | Fetch/validate stable release metadata, select the exact asset, write targets and shared workspace metadata |
| `release.py` | Validate tag and timezone-aware publication time; construct the upstream Debian version |
| `build` | Verify/reuse the archive, validate/extract, stage the package, remove metadata, render controls and build the `.deb` |
| `inspect-bundle.py` | Validate archive layout/types and ELF architecture, executable modes, imports and symbol ceilings |
| `runtime-dependencies` | Map external SONAMEs to reviewed Debian package dependencies |
| `launcher.in`, `desktop.in` | CLI and desktop integration |
| `control.in`, `copyright.in` | Package metadata and upstream/source/license references |
| `helper-inputs` | Fingerprint `lib/adapter/github.sh` and `lib/adapter/package.sh` as recipe inputs |

The framework calls `query` without arguments. The workspace receives
`release.json` (GitHub metadata), `version` (derived upstream version),
`release-date` (publication timestamp), `assets.json` (selected download), and
`targets.tsv` (at most one `VERSION<TAB>amd64` row). The asset record under
`amd64` has `version`, `name`, `url`, and `sha256` fields. These are adapter-owned
workspace conventions, not additions to the public hook contract.

The framework assigns the Debian revision and calls
`build VERSION ARCH OUTPUT_DIR` with exported context as described in the
[hook contract](../README.md#query-and-build-hooks). Build checks that the asset
version matches VERSION without its final revision and that the architecture and
asset filename match the selected policy. The verified archive is cached as
`WORKSPACE/chrome-lin64.tar.gz`; reuse requires its digest still to match.
Extraction and staging use fresh temporary directories under WORKSPACE. On
success they are removed after writing exactly one
`cromite_VERSION_amd64.deb` to OUTPUT_DIR. No upstream target code or maintainer
script runs during packaging.

The exact required root files are `chrome`, `chrome_sandbox`,
`chrome_crashpad_handler`, `chrome-wrapper`, `chrome_100_percent.pak`,
`chrome_200_percent.pak`, `resources.pak`, `icudtl.dat`, `snapshot_blob.bin`,
`product_logo_48.png`, the six listed libraries, and `locales/en-US.pak`.
Other accepted payload files are locale `.pak`/`.pak.info` names matching the
adapter's pattern. A layout change requires maintainer review, not fallback
root discovery.

The ELF symbol ceilings are GLIBC 2.41, GLIBCXX 3.4.33 and CXXABI 1.3.15.
The current dependency map declares libc6 >= 2.41 and libstdc++6 >= 14; these
are the implementation's target-baseline choices, not evidence that every
inspected upstream executable needs those exact minimums. Review actual symbol
and feature requirements before changing dependency floors. Qt shim imports are
validated but excluded from mandatory Depends because the shims are optional.
Static import checks do not discover every runtime-loaded library or feature.

## Investigation evidence

The supplied archive matched release
[`v153.0.8010.37-11507ac1061b5ea227806f5e84db5a57df6ccf6a`](https://github.com/uazo/cromite/releases/tag/v153.0.8010.37-11507ac1061b5ea227806f5e84db5a57df6ccf6a).
Its SHA256 is
`6fe67a4a75a3a5013cc470a3061606c44dc148531c42d8c56317ef0c7f8340cf`.
The downloaded archive and inspection logs are kept under ignored
`build/cromite-investigation/`. The original root-level download was moved there.

Measured uncompressed file bytes, before packaging:

| Component | Bytes | Approximate MiB |
| --- | ---: | ---: |
| Entire payload | 1,037,614,701 | 989.5 |
| Browser executable | 861,903,136 | 822.0 |
| Six separate shared libraries | 7,979,072 | 7.6 |
| Removed locale `.pak.info` files | 69,538,370 | 66.3 |

Libraries are SwiftShader (6,320,176 bytes), Vulkan (905,856), EGL and GLES
(334,952 each), and Qt5/Qt6 shims (39,456 and 43,680). They total about 0.8% of
the payload. The agreed policy preserves these components rather than replacing
them for small size savings. Dependencies compiled into the browser cannot be
replaced by repackaging; that would require a different source-build workflow.

The inspected upstream ELF files pass the adapter's amd64 and Debian 13 symbol
checks. This establishes static compatibility constraints, not browser behavior.

The source archive was 289,105,885 bytes (about 276 MiB). This is compressed
archive size, not the installed size or the amount occupied by libraries alone.
The generated inspection package contains 968,074,345 payload file bytes; its
278,118,500-byte Debian archive and 946240 KiB Installed-Size measure different
things. Installed-Size estimates disk allocation for the staged tree and is not
simply the sum of file lengths divided by 1024.

### Retained local evidence

These files were confirmed present on 2026-11-13 beneath ignored
`build/cromite-investigation/`. They are useful local evidence, not checked-in
fixtures or a prerequisite for ordinary offline tests:

| File | Meaning |
| --- | --- |
| `chrome-lin64.tar.gz` | Original user-supplied archive, moved from the project root; SHA256 recorded above |
| `archive.log`, `elf.log` | Archive listing/digest, measured file sizes and dynamic ELF imports |
| `baseline.log` | Symbol/export investigation and the original Docker socket access failure |
| `validation.log`, `final-static-validation.log` | Successful dependency/static inspections |
| `real-build.log`, `real-package-check.log` | Cached-archive build and streamed `.deb` payload/index validation |
| `assets.json`, `release.json` | Manually prepared inputs for the local inspection build; not a successful live query |
| `output/cromite_153.0.8010.37+localinspection.git11507ac1061b5ea227806f5e84db5a57df6ccf6a-1_amd64.deb` | Local inspection package, with dummy maintainer and the version shown |
| `tests.log`, `debug.log`, `debug-query.log` | Initial failure/debugging evidence |
| `tests-fixed.log`, `tests-final.log` | Test coordinator results after fixing the implementation |
| `shell-check.log`, `diff-check.log`, `extract.log` | Successful checks/extraction, with empty logs where commands were silent |
| `download.log` | Failed live API request: DNS resolution for api.github.com was unavailable |

The cached `release.json` contains only the tag. It lacks `published_at`, stable
release flags and assets, so it cannot be passed to the production query/version
parser as a complete GitHub response. `assets.json` uses a deliberately separate
`+localinspection` version. The test fixture's `2026-09-15T11:51:00Z` timestamp
is fixture input, not verified exact publication metadata from the live API.
Do not substitute those local files for release discovery or publish the local
package as if it were a normal operator build. Its dummy maintainer is
`Static Inspection <test@localhost>`.

The first offline failure was a missing `jq --null-input` while constructing
`assets.json`: query wrote targets but no asset JSON. This was corrected in the
adapter and the package/index integration test passed afterward. The historical
failed regression log is `build/test-run-K5gim9/regression.log`; the successful
final run is `build/test-run-FyhG8m/regression.log`. This history explains the
retained failure logs; it is not an outstanding bug report.

Successful build staging trees and the redundant first extraction were removed.
Keep the useful archive, package and logs while needed; never apply temporary
cleanup to stored production packages or signing keys. Future cleanup may remove
ignored local evidence, so the measurements and conclusions are recorded here.

## Verification and limits

Run `bash tests/run.sh cromite` from the project root. Offline fixtures use real
Debian package/index tools and fake downloads. Coverage includes stable selection,
missing arm64/assets, invalid metadata and checksums, unsafe archive entries,
required files, ELF architecture and unknown libraries, launcher arguments,
retained libraries/locales, omitted metadata, permissions, published Installed-Size,
repeat updates and recipe revisions. Signing changes are outside this adapter.

A static real-archive build can use the cached verified artifact without launching
Cromite. Local investigation packages use a `+localinspection` version and a dummy
maintainer; they are not production query results or publication artifacts.

Per the requested static-only implementation, no Docker installation, browser
launch, sandbox runtime, GPU, audio, codec, Qt or interactive desktop checks are
performed. Network release discovery also needs a live check in a network-enabled
environment. Publisher deployment and live publication remain separate steps.

Completed static verification for this implementation:

- All 12 Cromite offline tests passed (`build/test-run-FyhG8m/regression.log`).
- Bash syntax checks and `git diff --check` passed.
- A real cached-archive build produced a 278,118,500-byte local inspection `.deb`
  under `build/cromite-investigation/output/`, with `Installed-Size: 946240` KiB.
- Its streamed payload inspection confirmed expected libraries/resources,
  metadata removal, ordinary permissions and published index Installed-Size.
  Logs are `real-build.log`, `real-package-check.log`, and
  `final-static-validation.log` in the investigation directory.
- The local inspection artifact predates the final executable-permission
  validation addition; offline tests and final static archive/tree validation
  cover that addition. It remains an investigation artifact, not a release.
- The redundant initial extraction was removed after inspection. The verified
  download, local package, measurement logs and failure evidence are retained.

### Commands for a future session

Run these from the project root, redirecting output to named logs and inspecting
them after completion or the bounded timeout, as required by AGENTS.md:

```bash
mkdir -p build/cromite-handoff-checks
timeout 180 bash tests/run.sh cromite \
    > build/cromite-handoff-checks/tests.log 2>&1
bash -n packages/repack/cromite/query packages/repack/cromite/build \
    packages/repack/cromite/launcher.in \
    > build/cromite-handoff-checks/bash-n.log 2>&1
git diff --check > build/cromite-handoff-checks/diff-check.log 2>&1
```

These commands are instructions for future checks, not a claim of a new test
run during the documentation handoff. For documentation-only changes, factual
and link checks plus `git diff --check` suffice. The 12-test result above is the
original static implementation result. Framework evolution since then should
be evaluated against a fresh selected test run when code changes require one.

To inspect the cached package without running browser code:

```bash
dpkg-deb --field \
    build/cromite-investigation/output/cromite_153.0.8010.37+localinspection.git11507ac1061b5ea227806f5e84db5a57df6ccf6a-1_amd64.deb \
    > build/cromite-handoff-checks/control.log 2>&1
```

Do not run the cached incomplete metadata through the query hook. To repeat a
real-source build, use a fresh complete upstream response and the documented
hook context, or intentionally prepare clearly labeled local-only inputs in a
new ignored workspace. Reuse the verified archive when its SHA256 matches.
Do not copy operator settings, repository data, or signing keys into fixtures.

### Remaining work and decisions

- Profile/cache separation is an optional future change. It needs a chosen
  override policy, launcher tests and a new adapter revision; migration is a
  separate decision. Current source and package paths do not imply isolation
  from a regular Chromium profile.
- Live release discovery was not verified by the static build. A network-enabled
  query should confirm current upstream tag, timestamp, digest and layout rather
  than assume the inspected September artifact is still latest.
- Debian dependency resolution, actual browser launch, sandbox behavior, GPU,
  audio, codecs, Qt integration and desktop behavior remain unverified here.
  The user explicitly limited this implementation to static work.
- Building/recreating the publisher image, live publication, signing tests and
  installation on a client were not performed as part of this chat. Follow the
  current README if deployment is separately requested; do not infer deployment
  state from the existence of an adapter or an inspection `.deb`.
- This handoff changes documentation only. It deliberately leaves the current
  launcher behavior, user profile data and production repositories untouched.
