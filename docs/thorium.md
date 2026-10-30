# Thorium packaging and investigation notes

Status: adapters implemented with static verification, 2026-10-29. No real
Thorium package has been rebuilt, installed, or published in this work. The user
requested static analysis only, with Docker and browser execution deferred.
This document records the behavior, artifact evidence, and outstanding checks.
General notes live outside `packages/` so documentation
changes do not cause package revisions.

## Goal and decisions

Publish Thorium CPU variants with distinct Debian names and desktop launchers.
Support both Alex313031's stable releases and collaborator gz83's releases,
including beta builds. Users choose a source and CPU tier explicitly; an update
must not silently switch either choice.

| Source | amd64 concrete packages | Default package |
| --- | --- | --- |
| Alex313031 | `thorium-browser-sse3`, `thorium-browser-sse4`, `thorium-browser-avx`, `thorium-browser-avx2` | `thorium-browser`, depending on `thorium-browser-avx` |
| gz83 | `thorium-browser-gz83-sse3`, `thorium-browser-gz83-sse4`, `thorium-browser-gz83-avx`, `thorium-browser-gz83-avx2` | `thorium-browser-gz83`, depending on `thorium-browser-gz83-avx` |

On arm64, `thorium-browser-gz83` contains the native browser instead of
depending on an x86 tier. Initially Alex's stream has no arm64 target.
Default packages select AVX on amd64 by explicit user preference; they do not
detect CPU capabilities or select SSE3 automatically. SSE3 and SSE4 are the
non-AVX options. There is no additional unoptimized "vanilla" artifact in the
inspected stable asset list. Exclude i386 and AVX512 from the initial adapters.

All concrete variants can be installed together, across both source families.
Different upstream versions of the same Debian package name are still ordinary
APT upgrades, not separately installable copies.

All variants use Thorium's normal profile directory, unless the user explicitly
requests another directory. Keep normal Chromium instance locking and forwarding
behavior: launching another variant may hand the request to the running browser
rather than start that variant. Never delete locks or force simultaneous access.
Sharing a profile across browser versions does not establish downgrade
compatibility; document this and allow normal `--user-data-dir` overrides.

## Implemented adapter behavior

There are exactly two adapter directories and `RELEASE_STREAM` identities:
`thorium-browser` and `thorium-browser-gz83`. CPU tiers are binary packages
within those streams, not separate release streams. Each amd64 build emits five
packages: the default AVX metapackage and all four concrete tiers. The gz83
config declares a separate arm64 output list containing only its native
`thorium-browser-gz83` package. Alex's common output list is built only for
amd64 because its query omits arm64 targets.

Trusted adapter `settings` selects source and beta policy. `query` fetches all
release pages with curl; `select-release.py` chooses the newest release with
the complete required asset set per architecture. Incomplete newer CPU sets are
skipped with a warning while looking for the latest complete release; tiers are
never combined from different upstream versions. If no complete release exists,
that architecture has no target, preserving stored packages. Network or invalid
metadata/digest failures still fail the query. The workspace `assets.json` maps
each selected architecture to its version and assets keyed by binary package
name. Builds require the inspected upstream control version `VERSION-1`;
an upstream Debian revision change fails explicitly for maintainer review.

The framework allocates one revision for all outputs at a selected upstream
version. The build hook loops over its architecture's declared `BINARY_PACKAGES`
and returns the complete set before the framework validates or stores anything.
A failure in one CPU tier stores none of that invocation's outputs; the other
source stream can still complete. Default metapackages depend on the exact
matching AVX version/revision. Existing artifacts and partial stored output sets
use the framework's normal preservation and resume rules.

`build` uses the existing verified-download and Debian-control helpers.
`stage.py` validates archive paths, types, expected symlinks, required fixed
files, executable ELF machine/class, and root-owned mode-4755 sandbox metadata
before extraction. Unknown external integration files and unsafe links fail.
The known extra arm64 ClearKey resource in Alex's amd64 AVX/AVX2 packages is
explicitly allowed and preserved; arbitrary foreign executables are rejected.
Files are extracted as data, and upstream maintainer scripts are never run.

Concrete packages install the payload under `/opt/PACKAGE_NAME/`, retaining
bundled libraries and resources. Commands are `PACKAGE_NAME`,
`PACKAGE_NAME-shell`, `PACKAGE_NAME-pak`, and `PACKAGE_NAME-chromedriver`.
Browser/shell desktop entries, icons, AppStream identity, documentation, and man
page filenames are package-specific. The redundant upstream browser desktop ID
and legacy GNOME/menu registration are omitted. Unused payload data remains
private; no upstream binaries are recompiled or ELF-patched.

The main launcher preserves quoted CLI arguments and supports leading
`--temp-profile` and `--safe-mode`. Temporary profiles remain available for
manual inspection/removal, matching upstream's lack of automatic cleanup.
`thorium/thorium-flags.conf` under the normal XDG config directory retains
whitespace-separated arguments; the launcher does not expand globs or execute
shell expressions. Its WM class matches the package desktop ID. Default amd64
launchers forward to AVX without adding duplicate desktop entries. No launcher
forces a different profile directory, bypasses locking, or uses `--no-sandbox`.

Replacement maintainer scripts register only their package's alternative
commands at priority 40; they do not use `update-alternatives --set` or change
user MIME preferences. Removal unregisters only the matching variant. Icons are
ordinary files under the hicolor hierarchy. Shared repository/key configuration
and cron jobs are omitted. Device-trust enrollment/group setup from upstream is
not performed; the optional management executable remains private in the payload.

gz83 profiles are installed as `/etc/apparmor.d/PACKAGE_NAME` conffiles, with
matching profile names, executable attachments, and optional local includes.
Installation reloads only that profile when AppArmor ABI 4.0 and the parser
exist; removal unloads it. Alex's packages do not receive an invented AppArmor
profile. Both families retain their original setuid sandbox helper. This
preserves upstream's two different integrations without disabling the sandbox;
whether either sandbox works on a particular desktop remains untested.

All final outputs replace maintainer/version/publisher fields and recalculate
Installed-Size after staging. Upstream dependency fields, embedded license
resources, and available Widevine LICENSE files are retained. The added copyright
note points to embedded credits/terms; it does not claim a completed legal audit
of third-party redistribution conditions.

The hook/helper/template copies are intentionally adapter-local: symlinked
recipes are unsupported, and upstream-specific logic does not belong in `lib/`.
When changing common Thorium behavior, update the identical copies in both
directories, excluding stream-specific `config` and `settings`. Each copy
participates in its own stream's checksum. No framework or Dockerfile change is
needed, and no central registry was introduced.

## Upstream sources

- [Thorium website](https://thorium.rocks/) documents its APT repository and
  `thorium-browser` installation name. The contents of that APT repository have
  not been audited here; the user's report that it omits AVX2 remains unverified.
- [CPU variant guide](https://github.com/Alex313031/thorium/blob/main/docs/ABOUT_RELEASES.md)
  explains instruction-set requirements. Use these requirements rather than
  guessing support from CPU marketing names.
- [Alex releases](https://github.com/Alex313031/thorium/releases) include newer
  beta announcements pointing to gz83. An announcement is not a binary release.
- [Alex M138.0.7204.303 assets](https://github.com/Alex313031/thorium/releases/expanded_assets/M138.0.7204.303)
  contain SSE3, SSE4, AVX, and AVX2 amd64 `.deb` files, plus i386 and other formats.
  The release is dated February 2026, with the inspected amd64 assets uploaded
  February 18. Do not confuse an asset upload date with a browser security update.
- [gz83 releases](https://github.com/gz83/thorium/releases) currently label the
  collaborator builds beta. [M156.0.8078.28 assets](https://github.com/gz83/thorium/releases/expanded_assets/M156.0.8078.28)
  include the four planned x86 tiers, AVX512, and a native arm64 `.deb`.
  All seven Debian packages have now been downloaded, verified, and inspected
  locally alongside all five Debian packages from Alex's stable release.

These versions are observations, not pins for the eventual adapter.

### Complete release inventory

A subsequent GitHub API discovery fetched all 76 Alex releases and all eight
gz83 releases (both fit within one 100-entry page), totaling 613 assets. Raw
responses are retained in `build/thorium-investigation/releases/alex.json` and
`gz83.json`; `all-assets.tsv` records every asset's source, tag, prerelease flag,
publication date, filename, size, digest, and URL. `selected-debs.json` records
the complete Debian asset sets for the two releases selected for inspection.

| Source and release | Debian assets |
| --- | --- |
| Alex M138.0.7204.303 | SSE3, SSE4, AVX, AVX2, i386 |
| gz83 M156.0.8078.28 | SSE3, SSE4, AVX, AVX2, AVX512, i386, arm64 |

These are complete Debian asset inventories for those releases, not an inference
from the two user-supplied examples. Older Alex releases include generic
`_amd64.deb` filenames, a `chromium-browser-stable` artifact, and a beta-specific
filename. Do not use those as automatic substitutes for current named variants.
Other current formats include RPM, ZIP, and AppImage; gz83 also publishes
non-Linux artifacts. Their presence does not make them Debian package targets.

Alex's M144 through M156 announcement releases contain no Debian assets.
Several releases described as beta in both repositories have `prerelease=false`
in the API, including gz83 M156. Selection must use the intended source policy,
actual browser assets, and release descriptions/names rather than relying on
the GitHub prerelease flag alone.

## Local artifacts and evidence

The two user-supplied packages were moved from the project root into ignored
`build/thorium-investigation/downloads/`, preserving their original filenames
and bytes. Both SHA256 values match the upstream stable release asset listing.

| Filename | Bytes | SHA256 |
| --- | --- | --- |
| `thorium-browser_138.0.7204.303_SSE3.deb` | 160052656 | `bacb67c4b8a4e685e505c09d46c7f55cdd5f66ed2e75b970fc3b63d59314563e` |
| `thorium-browser_138.0.7204.303_SSE4.deb` | 159822352 | `34cbc8d3a7982bc461e20cb046d819631fd8aff9b68db6c0b10bfe42df5b025b` |

Retained local evidence:

- `build/thorium-investigation/logs/package-inspection.log`: hashes,
  `dpkg-deb --info`, and complete payload listings for both packages.
- `build/thorium-investigation/control-sse3/` and `control-sse4/`: extracted
  control metadata and maintainer scripts.
- `build/thorium-investigation/logs/launchers-and-update.log`: upstream browser
  wrapper, shell launcher, desktop entry, and cron script for both variants.
  Tar extraction order determines the order of these entries in the log.

Commands ran in bounded batches with stdout/stderr redirected to these logs.
No maintainer script or downloaded executable was run. Payload archives were
streamed to inspect entries and ELF headers; only selected text and control
files were extracted. There is no full staged browser tree yet.
Reuse these verified downloads. Do not commit artifacts or logs. The unrelated
`chrome-lin64.tar.gz` and `gimp-investigation/` remain untouched.

## Can the original packages be published unchanged?

Not for the agreed variant design using this publisher. All 12 inspected packages
declare `Package: thorium-browser`, use the shared `/opt/chromium.org/thorium`
root, and retain unqualified browser launchers and desktop identities. The
initially inspected SSE3 and SSE4 examples both contain:

```text
Package: thorium-browser
Version: 138.0.7204.303-1
Architecture: amd64
Maintainer: Thorium Linux Maintainers <alex313031@gmail.com>
```

The filename's CPU suffix is not part of Debian package identity. Publishing
both unchanged would provide two different byte sequences for the same package,
version, and architecture. Renaming files cannot fix that. They would replace
one another and also share their installed paths and integration.

Important shared paths include:

```text
/opt/chromium.org/thorium/thorium
/opt/chromium.org/thorium/thorium-browser
/opt/chromium.org/thorium/chrome-sandbox
/usr/bin/thorium-browser
/usr/bin/thorium-shell
/usr/bin/pak
/usr/share/applications/thorium-browser.desktop
/usr/share/applications/org.chromium.Thorium.desktop
/usr/share/applications/thorium-shell.desktop
/usr/share/appdata/thorium-browser.appdata.xml
/usr/share/doc/thorium-browser/
/usr/share/man/man1/thorium-browser.1.gz
/usr/share/menu/thorium-browser.menu
/usr/share/gnome-control-center/default-apps/thorium-browser.xml
/etc/cron.daily/thorium-browser
```

`/usr/bin/thorium-browser` and the cron entry are absolute symlinks into the
shared `/opt` tree. Renaming only `Package` would leave file collisions.

The existing publisher also requires embedded `X-Publisher-Stream` and
`X-Build-Inputs-SHA256`, assigned versions, and operator maintainer metadata.
These packages lack the two publisher fields. `lib/store-packages.sh` validates
package identity and those fields before storage. Supporting byte-for-byte
upstream imports would require a deliberate framework design change; do not
bypass validation or manually copy packages into production storage.

The user prefers original `.deb` files whenever they meet the requirements.
Preserve that preference: use upstream binaries and resources without rebuilding
or patching them unless inspection demonstrates a need. Here package metadata,
installation paths, launchers, and integration must change for coexistence.

### Alex M138 integration requiring review

The upstream `postinst` registers shared icon names and browser alternatives,
updates desktop MIME caches and legacy desktop configuration, optionally sets
up device trust management, and creates `/etc/default/thorium-browser` with
repository flags disabled. It then launches the cron script asynchronously.

The cron script contains signing-key installation and repository configuration
logic; `REPOCONFIG` is empty in the inspected scripts, but its main path calls
`install_key`. Do not infer that disabled repository flags mean no side effects.
The upstream `postrm` removes the shared defaults file when nonempty and removes
`thorium-browser.gpg` from APT's trusted key directory. `prerm` unregisters shared
icons and browser alternatives. Preserving these scripts across renamed variants
would let installation/removal of one affect another.

The wrapper sets `CHROME_DESKTOP=thorium-browser.desktop`, derives its payload
location from itself, reads `thorium/thorium-flags.conf`, supports temporary
profiles and safe mode, and executes the adjacent browser binary. Its
`CHROME_VERSION_EXTRA` distinguishes SSE3 from SSE4. Desktop actions include the
shared `thorium-shell` launcher, which itself contains an absolute `/opt` path.
Review these behaviors explicitly when replacing or adapting integration.

Both packages carry a root-owned setuid `chrome-sandbox` (mode 4755). Preserve
the supported sandbox setup and test normal operation; do not solve launch
failures with `--no-sandbox`.

Upstream Installed-Size is 765652 KiB for SSE3 and 764915 KiB for SSE4. These
values have not been independently measured against a full extracted tree.
Recalculate each final staged package excluding `DEBIAN/`, as required for every
adapter, and verify the published index value.

## Full Debian artifact comparison

All 12 archives are now retained under `build/thorium-investigation/downloads/`.
Ten additional downloads were fetched using the GitHub API URLs, checked against
both the API SHA256 digest and byte size, and atomically renamed from `.part`
only after verification. The two original downloads were reverified too. Total
archive storage is 2,451,913,272 bytes. No archive was recompressed or modified.

Versions embedded in control metadata are `138.0.7204.303-1` for all five Alex
packages and `156.0.8078.28-1` for all seven gz83 packages. Every archive still
uses the Debian name `thorium-browser`, including AVX2, AVX512, and arm64. The
x86 CPU tier is not encoded in package identity. Two source versions can be
selected as upgrades/downgrades but cannot coexist under that common name.

The following Installed-Size values are upstream declarations, not recalculated
sizes. Byte sizes and hashes were independently verified against downloaded data.

| Source | Variant | Architecture | Archive bytes | Upstream Installed-Size (KiB) | SHA256 |
| --- | --- | --- | --- | --- | --- |
| alex | AVX | amd64 | 161382052 | 770977 | `9bfad87fd5119720a1bc47af3b3e3efcbd92910032aa949d97bdc5191e2edb60` |
| alex | AVX2 | amd64 | 160437412 | 766941 | `df055a5c8ab0b0437f1265f6992de0d59ac49eb89caa1458e7b958d969847a98` |
| alex | i386 | i386 | 172781256 | 723976 | `349cea55b919bbcaafa94cdb3324322233b52009ac6b7e39066d8389f88a7ae1` |
| alex | SSE3 | amd64 | 160052656 | 765652 | `bacb67c4b8a4e685e505c09d46c7f55cdd5f66ed2e75b970fc3b63d59314563e` |
| alex | SSE4 | amd64 | 159822352 | 764915 | `34cbc8d3a7982bc461e20cb046d819631fd8aff9b68db6c0b10bfe42df5b025b` |
| gz83 | arm64 | arm64 | 195033988 | 674845 | `1fa1a1d73b6a3da2b81b6afce5273733910600d36c0fc04c7600306733dfe863` |
| gz83 | AVX | amd64 | 242916820 | 701395 | `bfb6f38ae10543b601e295f5fee35fc847bd10a871cf5416eb98b708c8b681d2` |
| gz83 | AVX2 | amd64 | 241226788 | 696257 | `15496ebae54d15a946e1cad9ecc174f50008cc355e35be58ff339ec23bf00846` |
| gz83 | AVX512 | amd64 | 240736868 | 694034 | `f8a8228d4a33cd7f6ba7c1e40872e9c0ff0203c937ae12e7a91db02b3b4b6027` |
| gz83 | i386 | i386 | 232296108 | 684134 | `b7c0fbd59b64a50353d1fc037ca98f9f66066c2a69e61bdeba939df2fca8004d` |
| gz83 | SSE3 | amd64 | 242427288 | 697945 | `f712a8e5475c4baeec1f84ac2a8efd3f03f4fe2c5bed75e4454761ad54cdb77e` |
| gz83 | SSE4 | amd64 | 242799684 | 699122 | `b8df0438bb53ae9a807389e9b17a94e92e309a6ad41ef9c5c45b2d8a8c80200a` |

### Payload and integration differences

- Every main browser, sandbox, content-shell, and management-service executable
  has the ELF machine/class expected by its declared architecture. All inspected
  sandbox files have mode 4755. This does not validate the instruction-set tier
  or prove runtime compatibility.
- A scan of every regular payload file's ELF header found additional foreign
  binaries: Alex AVX and AVX2 include an AArch64 ClearKey library under
  `ClearKeyCdm/_platform_specific/linux_arm64/`. Their SSE3/SSE4 counterparts
  omit that path. These are real differences between the supplied examples and
  the other CPU tiers, not a reason to silently search for alternate layouts.
- Alex i386 also includes x86-64 ClearKey/Widevine libraries and an x86-64
  `/usr/bin/pak`; gz83 i386 includes an x86-64 private `pak`. Record these upstream
  inconsistencies rather than claiming every included binary matches the package
  architecture. i386 remains outside the publisher's supported architectures.
- gz83 M156 has no upstream repository cron script or `/etc/cron.daily` link,
  and its maintainer scripts contain no old repository/key provisioning routines.
  The initial Alex-specific observations must not be applied to gz83.
- All seven gz83 packages have byte-identical `postinst`, `prerm`, and `postrm`
  scripts. They still manipulate shared icons, browser alternatives, and `/opt`
  paths, so they cannot be preserved unchanged in coinstallable renamed packages.
- gz83 adds `apparmor.d/thorium-browser` beneath its payload. `postinst` copies
  it to `/etc/apparmor.d/thorium-browser` and reloads it when AppArmor ABI 4.0
  and the parser are available. Its attachment names the fixed upstream browser
  path and allows user namespaces. Repackaging must give the profile a distinct
  name, local include, destination, and attachment for each variant, with matching
  installation/removal behavior. Do not discard sandbox integration merely
  because the main binary can be relocated.
- gz83 adds gender-specific locale resources, moves the real `pak` executable
  under `/opt`, and omits several older files, including the old standalone
  `libEGL.so`, `libGLESv2.so`, `libffmpeg.so`, legacy menu file, and bundled xdg
  helpers. Keep fixed expectations for each source rather than assuming identical
  payload sets.
- Dependencies are identical within each inspected source release. gz83 raises
  four declared minimums: libc6 2.17 to 2.25, libcairo2 1.6.0 to 1.14.0, libcups2
  1.6.0 to 1.7.0, and libglib2.0-0 2.39.4 to 2.49.3. Resolving these names and
  alternatives on Trixie, and checking actual ELF linkage, remain implementation
  validation tasks; control fields alone do not establish compatibility.

### Reproduction and evidence

`build/thorium-investigation/download-packages.py` selects all Debian assets
from the retained two release records, reuses verified downloads, and fetches
missing ones with bounded curl attempts. Each archive has its own `.download.log`
under `logs/`; `download-batch.log` records successful completion of the full set.
The first sandboxed release-discovery attempt failed DNS resolution; its failure
log was retained, and the network-enabled retry succeeded.

`build/thorium-investigation/inspect-packages.py` streams each package archive
without executing target binaries or scripts. Its results are under
`inspection/ASSET_NAME_WITHOUT_DEB/`: `control/` contains Debian metadata and
scripts, `payload.json` records all entry paths/types/modes/sizes/link targets,
and `text/` contains selected launchers, desktop/application metadata, cron, and
AppArmor text. `inspection/summary.json` records metadata, all discovered ELF
machine/class values, and script/text hashes for all 12 packages.
`logs/inspection-all-elf.log` records the completed comprehensive scan; the earlier
`inspection-batch.log` records the initial main-executable scan.

These local investigation scripts and logs are retained under ignored `build/`;
they are not production adapters or required project dependencies. Streaming
inspection avoids redundant full payload staging trees. Preserve downloaded
sources and evidence for the implementation work. No APT installation, browser
launch, dynamic-link resolution, package rebuild, signing, or publication has
been performed.

## XZ decompression memory requirements

The publisher's Compose memory limit is 512 MiB. Inspection of the upstream XZ
block headers found a 256 MiB LZMA2 dictionary in all Alex M138 Debian payloads
and an 8 MiB dictionary in all gz83 M156 payloads. The previous 256 MiB container
limit could not accommodate Alex's dictionary plus the decoder and other
processes. gz83 can also incur substantial multithreaded decoder buffers.

The initial `dpkg-deb --threads-max=1` change was insufficient. dpkg still
initializes liblzma's multithreaded decoder, with memory limits derived separately
from the requested worker count. A single worker is not the same as selecting
liblzma's streaming decoder. See the
[dpkg decoder implementation](https://raw.githubusercontent.com/guillemj/dpkg/1.22.21/lib/dpkg/compress.c)
and [liblzma decoder API](https://raw.githubusercontent.com/tukaani-project/xz/v5.8.1/src/liblzma/api/lzma/container.h).
The inspected Alex SSE3 payload's first block has 160,034,194 compressed bytes
and 783,994,880 uncompressed bytes (about 748 MiB); retaining such a block already
exceeds the container's memory limit, before the dictionary is counted.

Both adapters now use the same adapter-local `payload-tar` reader for validation
and extraction. It requires exactly the inspected Debian archive members:
`debian-binary`, `control.tar.xz`, and `data.tar.xz`, in order. It streams the
compressed payload with `ar p` into `xz --decompress --stdout --threads=1
--memlimit-decompress=384MiB`, ignoring `XZ_DEFAULTS` and `XZ_OPT` so inherited
options cannot change the decoder policy. XZ's one-thread CLI mode uses the
streaming decoder. The 384 MiB decoder limit leaves space within the 512 MiB
container for the Python validator, archive reader, tar, and publisher processes.
It is a decoder limit, not a guarantee about total container memory usage.

After validation, dpkg extracts only the small control archive. GNU tar extracts
the streamed payload without applying upstream ownership, while preserving
permissions including the setuid sandbox mode. No target binaries or upstream
maintainer scripts are executed. `pipefail` propagates archive-reader,
decompressor, and extraction failures. Validation drains remaining decoder output
before checking the reader's exit status so tar padding cannot leave a writer
blocked and compressed-stream checksum errors are still reported.

Single-threaded decoding cannot shrink the upstream dictionary requirement.
XZ's decompression memory limit rejects streams that need more memory rather
than reducing the encoded dictionary; see the
[XZ manual](https://tukaani.org/xz/man/xz.1.html). No source archive is recompressed
or altered. Generated packages still use the publisher's existing gzip
compression. The 512 MiB budget has not been verified by a deployed memory
benchmark. A killed decoder is consistent with OOM; confirming the incident still
requires cgroup or kernel OOM evidence.

Payload parser errors include the archive path and payload-reader exit status,
while preserving the original ar/XZ stderr. The previous dpkg-based error message
is superseded. An unsupported archive layout fails explicitly; the reader does
not search for another compression format or payload root. The existing
`binutils` and `xz-utils` image dependencies provide ar and xz, so the Dockerfile
and publisher framework do not change.

Apply both changes by rebuilding and recreating the publisher container, for
example `docker compose up -d --build --force-recreate`. A restart alone does
not replace adapter code or apply the changed container memory limit. Deployment
has not been performed as part of this change. Stored packages and repository
keys are unaffected; normal complete-output and retry rules remain in force.

## Verification status and remaining checks

Static validation passed for all nine supported downloaded payloads: Alex SSE3,
SSE4, AVX, AVX2; gz83 SSE3, SSE4, AVX, AVX2, arm64. The validator reads archive
metadata and ELF headers without installing packages or executing target binaries.
The completed log is
`build/thorium-implementation/logs/upstream-static-validation.log`.

Offline regression fixtures have been added under the two streams' matching test
directory, with shared test-only support in `tests/lib/thorium_support.py`. They
cover publication and Installed-Size/index agreement, missing/stale size metadata,
repeat updates, missing assets, retention, pagination and announcements, beta
policy, duplicate assets, malformed digests, corrupted downloads, wrong
architectures, private paths, sandbox modes, desktop commands, and AppArmor names.
Consolidated-stream cases cover complete five-package amd64 output sets, shared
stream metadata/revisions, no partial storage on a late-tier failure, complete-set
release selection, and resuming a missing tier without overwriting stored files.

Before the static-only instruction and two-stream consolidation, the first test attempt failed discovery
because modules shared a filename. Unique per-stream module names fixed discovery.
A second run executed 80 cases and exposed a replacement-order bug in desktop
shell actions and uninitialized fixture state in three negative tests. Those
issues were corrected; AppArmor replacements received the same ordering review.
Further source review corrected absolute shell-icon paths and localized launcher
names, and added gzip manpage rewriting and strict executable checks. The final
expanded regression suite has not been rerun under the static-only constraint;
the earlier failed-run evidence is retained in
`build/thorium-implementation/logs/offline-first.log`, `offline-second.log`, and
the regression-log paths they name. Do not describe that run as passing.

Final static checks cover Python parsing, shell syntax for hooks and
shell templates, identical common adapter inputs, declared identities, executable
hook modes, local documentation links, and `git diff --check`. Their named logs
live under `build/thorium-implementation/logs/`. The current two-stream checks
are recorded in `two-stream-static-checks.log`, including the five amd64 outputs
per stream, the single gz83 arm64 output, and removal of CPU-tier adapter/test
directories. Earlier ten-stream logs describe the superseded layout.

The consolidated implementation has received static checks only. When
package-building verification is authorized again, run
`bash tests/run.sh thorium-browser thorium-browser-gz83`. No signing test is necessary unless
signing changes or the full suite is intentionally selected. Reuse the verified
upstream downloads when checking real builds. Full dependency/SONAME resolution,
Trixie APT dependency installation, relocation, browser startup, profile locking,
AppArmor load/unload, desktop integration, and simultaneous package installation
remain unverified. In particular, checking ELF class and machine does not prove
that AVX/AVX2 instructions match the selected CPU or that all shared libraries
will resolve after relocation.

Docker builds, package installation, browser execution, container image rebuild,
signing, and live publication are deferred at the user's request. Do not use
production packages, profiles, or keys for the eventual verification.
