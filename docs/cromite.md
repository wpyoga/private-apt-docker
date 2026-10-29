# Cromite packaging and verification

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
