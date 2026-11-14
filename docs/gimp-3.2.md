# GIMP 3.2 packaging and deferred investigation

The [original conversation handoff](gimp-original-chat-handoff.md) preserves the
initial resource estimates, the decision to repackage extracted AppImage binaries,
plug-in compatibility discussion, approved test plan and commands actually run
before work moved into this repository. It distinguishes that chat's execution
record from later experiments and the maintained adapter.

The [original packaging and test refactor handoff](gimp-packaging-and-test-refactor-handoff.md)
preserves the implementation conversation, package design questions, manual-script
review, historical verification, disk/ownership recovery and test organization.
It distinguishes the original combined application/manual stream from later work.

The [AppImage build-base research](gimp-appimage-build-base.md) records the exact
GIMP 3.2.6 CI base-image inheritance, build-instruction sources, Debian/backports
library-version comparison, and corrections and evidence limits from that chat.

The [startup and dependency handoff](gimp-startup-and-dependencies-handoff.md)
preserves the update-warning diagnosis, Debian customization review, dependency
ownership decisions, personal welcome-screen recipe, historical checks and their
evidence limits. It distinguishes the original combined application/manual build
from the current independent streams.

For the retired investigation's cleanup decision, evidence inventory, current
code entry points and verification commands, see the
[conversation handoff](gimp-3.2-investigation-history.md#conversation-handoff-and-cleanup-decision-2026-11-13).
The old local directory is no longer present as of 2026-11-13; no chat history
or files from that directory are required to use the maintained recipe.

The gimp-3.2 adapter follows the latest stable 3.2.x entry in GIMP's official
gimp_versions.json, even after a newer series appears. It verifies each official
AppImage's SHA256 and extracts SquashFS as data, without running AppRun or FUSE.
It supports amd64/x86_64 and arm64/aarch64 and targets Debian 13.

The eight core binary packages are gimp, gimp-data, libgimp-3.0-0, gir1.2-gimp-3.0,
gimp-bundled-runtime, libgimp-3.0-bin, libgimp-3.0-dev, and libgimp-3.0-doc.
They share the framework-assigned GIMP version and
revision. The 3.0 library/directory names are the GIMP 3 API, not application 3.0.
Only babl/GEGL libraries, modules, and typelibs remain private. External runtime
libraries come from Debian, including libheif and all six codec plugins. GIMP
directly declares all seven HEIF dependencies. Debian's babl/GEGL are preserved.

The recipe validates fixed paths, package metadata, ELF architecture, links and
file types before staging. A known SONAME-to-Debian-package map validates every
staged ELF dependency; new upstream library requirements fail explicitly.
Builds never inspect installed host packages or execute target-architecture code.
Native ELF search paths contain only $ORIGIN and the private runtime directory.
Publisher metadata, conffiles, library-cache activation and Installed-Size are
generated for the final package trees.

## Package and dependency choices

Use Debian's gimp-data-extras without repacking it. Its collection version is
independent of GIMP's version; Debian installs it in the GIMP 3 API data directory.
It is suggested rather than required. Legacy scripts in that collection have
not been individually verified against GIMP 3.2.

libgimp-3.0-bin contains the AppImage's gimptool-3.2 executable and aliases.
The manpage comes from docs/gimptool.1.in in the official GIMP 3.2.6 source tag;
rendering substitutes the selected version and our native installation paths.
The template retains upstream authorship. It is a static 3.2-stream input and
should be reviewed when gimptool changes.

libgimp-3.0-dev contains GIMP headers and linker symlinks, plus matching private
Babl/GEGL headers, linker symlinks, and pkg-config metadata. Debian normally
ships the latter in libbabl-dev and libgegl-dev, but stable's versions are too
old for this GIMP build. Our private headers live under
/usr/include/gimp-3.0/bundled. Distinct gimp-babl-0.1.pc and gimp-gegl-0.4.pc
names prevent collisions with system development packages. GIMP's .pc files
require these private entries; their link flags embed the private runtime path
for newly compiled plug-ins. Other development dependencies come from Debian.
This is a C/C++ SDK; the AppImage does not supply GIR XML or static archives,
so we do not claim the corresponding GIR development virtual packages.

Version relationships follow Debian's approach: matching runtime, typelib,
tool, and development packages use exact (= package-version) dependencies.
External distro packages use minimum versions where a supported floor is known.
The static runtime-dependencies file contains Debian dependency expressions,
expected SONAMEs, and ownership, separated by pipes. "auto" assigns linked
requirements from ELF inspection; a binary package name assigns indirect
requirements.
It consolidates the former three dependency files, including HEIF. Blank SONAME
fields describe dependencies loaded indirectly or required by scripts/resources.
The libheif floor is 1.19.8; libappstream5 uses the tested Trixie floor 1.0.5.
Other unversioned entries are not a claim that every historical version works:
Debian 13 is the supported baseline. A bundled version is not automatically
the oldest compatible version. New linked SONAMEs fail validation; new dynamic
plug-ins or resource requirements also need explicit checks and runtime tests.

The original AppImage includes GEGL's external dependencies. We replace those
copies with distro packages, so our runtime must declare their dependencies.
Debian GIMP 3.0's Depends is a reference, not an authoritative list for this
different build and package split. GIMP 3.0 uses appstream-glib, whereas 3.2
uses AppStream (libappstream.so.5); these are different APIs, not interchangeable
runtime providers. Both concern software/extension metadata.

The AppImage uses AppRun; Debian's gimp command directly selects an ELF executable.
Our small launcher remains necessary for the private layout: RUNPATH does not
set Babl/GEGL module or GI typelib directories and is not inherited across exec.
The launcher supplies those paths to GIMP and child Python/GJS interpreters.
No bundled HEIF plugin path is set; Debian's six plugins are used.

libgimp-3.0-doc contains generated HTML from the matching upstream
gimp-api-docs-VERSION.tar.xz, verified against upstream SHA256SUMS. It has
Architecture: all and is stored once for both binary indexes.

User manuals are published independently by the gimp-help-3.2 adapter; see
[GIMP help packaging and validation notes](gimp-help-3.2.md). The application
only suggests manuals. API documentation remains tied to the matching
application release.

Sources:
https://download.gimp.org/gimp/v3.2/api-docs/,
https://github.com/GNOME/gimp/blob/GIMP_3_2_6/docs/gimptool.1.in.

copyright.in is a rendered licensing/source notice for newly assembled packages.
Ghostty preserves its upstream Debian copyright file; Codex has no equivalent
dedicated generation step. The GIMP notice is not a complete per-file audit.
Imported help packages retain their upstream Debian licensing documentation.

## Previous five-package build verification (2026-10-26)

The official GIMP 3.2.6 AppImages produced all five 3.2.6-1 packages for both
amd64 and arm64 without executing target binaries. The selected payloads contain
259 amd64 and 213 arm64 ELF objects. The real packages passed publisher metadata,
Installed-Size against the final staged trees, and generated index checks; all
ten outputs share one recipe fingerprint. Outputs are under
`build/gimp-adapter-live/output/`, with inspection indexes in its parent.

All 79 offline regression tests and the throwaway-key signing/APT integration
test passed in the publisher image. The final image is tagged locally as
`private-apt-publisher:gimp-3.2`; building it does not start a production update.
Reproducible real-package tests are in `tests/gimp-3.2/test-install.sh` and
`tests/gimp-3.2/`; runtime execution testing is amd64 only.

Clean amd64 APT installation and Debian GIMP test/remove-without-purge/reinstall
both passed. All 259 installed ELF objects resolved. Configuration and the
system babl/GEGL packages/files were preserved. The runtime checks confirmed
private babl 0.1.128 / GEGL 0.4.72 and all six system HEIF plugins. Headless and
Xvfb GUI tests passed GEGL inversion, XCF, PNG, JPEG, TIFF without thumbnails,
WebP, HEIC, AVIF, JPEG XL, XPM, and SVG dimension/pixel checks. See install-3.log
for the final run with mandatory metadata/private-version/plugin checks enabled.

Logs are retained in `build/gimp-adapter-logs/`. The first official build stopped
during arm64 patching after scanning every resource file; the successful second
run selectively extracts owned paths and patches only the validated ELF manifest.
The first metadata checker incorrectly treated Debian field names as case-sensitive;
the corrected checker normalizes them. The first reinstall test omitted Xvfb's
temporary directory; that test setup was corrected. Earlier log files are kept.
The smoke tests explicitly require repack metadata, private babl/GEGL versions,
and all HEIF plugins; they do not skip those checks when Debian slim filters docs.

## Deferred TIFF-thumbnail failure

Recorded 2026-10-26. GIMP 3.2.6 exports a 64x64 TIFF with include-thumbnail=True,
then our Gimp.file_load test reopens it as 256x256 and exits with assertion failure
(batch exit 64). Disabling the thumbnail passes the size/pixel round-trip test.
The failing run also warns about old-style JPEG compression.

The original dedicated reproducer and failure log are no longer present. To
recreate the check, use an isolated profile and the 64x64 image construction,
TIFF export procedure and Gimp.file_load dimension/pixel assertions in
[the codec smoke test](../tests/gimp-3.2/smoke.py), but explicitly enable
include-thumbnail=True. Keep the exported TIFF for independent inspection.
The existing smoke test intentionally sets that option to False and therefore
does not cover this failure.

Earlier investigation notes report the same failure with the preserved original
extracted runtime and libtiff 4.7.0, but do not establish a controlled test of the
untouched AppImage through AppRun. The cause is unresolved: GIMP export/import,
thumbnail selection in the test harness, or shared library behavior remain
possible. Do not attribute it to libtiff or to repackaging without further evidence.
Future investigation should compare the untouched AppImage and inspect the TIFF's
main image/thumbnail directories with an independent reader. This work is deferred
at the user's request and is not a prerequisite for enabling this adapter.

## Other outstanding validation and documentation

- Direct upgrades remain unvalidated. An early nine-package draft failed during
  APT/dpkg for an undiagnosed reason; it was superseded by the tested
  remove-without-purge/reinstall sequence. That historical failure does not
  establish a failure in the current eight-package adapter. Any future upgrade
  test should retain APT/dpkg diagnostics and verify configuration preservation.
- Third-party GIMP 3 plug-ins remain unvalidated. Debian's configured repositories
  did not provide gimp-gmic during the investigation; the gmic CLI is not the GIMP
  plug-in. Testing was deferred rather than obtaining another upstream binary.
- Arm64 packaging/static inspection does not establish arm64 desktop execution
  or codec compatibility; that needs a target-machine runtime test.
- The generated copyright notice records upstream sources and broad licenses,
  but a complete per-file licensing/provenance audit remains outstanding.

### Follow-up evidence needed

These are follow-up directions, not fixes completed by the documentation work.
Keep each test tied to the exact application version, package revision,
architecture and dependency versions it exercises.

| Area | Investigation and completion criteria |
| --- | --- |
| TIFF thumbnails | Recreate the thumbnail-enabled case in an isolated profile, retain the output TIFF and complete logs, and compare the same input/procedure with the untouched matching AppImage. Inspect main-image and thumbnail directories with an independent TIFF reader. Identify whether export, import or test selection explains the 64x64/256x256 discrepancy before assigning a cause. If fixed, add a regression that exercises thumbnails enabled; the existing disabled-thumbnail round trip must still pass. |
| Direct upgrades | If this deferred work is resumed, use a disposable Debian 13 environment with the current output set. Retain APT simulation, installation and dpkg diagnostics; verify configuration preservation, dependency resolution, Debian babl/GEGL coexistence and runtime behavior. The old nine-package failure log is unavailable, so it cannot supply a diagnosis for today's recipe. |
| Third-party plug-ins | Select an actual GIMP 3 plug-in and document its provenance, version, build requirements and installation paths. Test loading and a real operation against the private runtime, including SDK-built plug-ins where appropriate. A successful G'MIC CLI invocation is not GIMP plug-in coverage; a single plug-in does not establish compatibility for all plug-ins. |
| Arm64 runtime | Run native installation, launcher, desktop and codec checks on an arm64 system with isolated profiles. Record the actual platform and results separately from successful cross-architecture package inspection. The existing amd64 coordinator needs deliberate adaptation before use as arm64 evidence. |
| Licensing/provenance | Review shipped GIMP, private babl/GEGL, modules and resources against their corresponding source releases and notices. Record per-file or component coverage, required notices and any gaps; the broad generated copyright/source notice alone does not complete this review. |

For TIFF, preserve both the thumbnail-enabled failure and disabled-thumbnail
control, including dimensions, pixel checks, procedure return status and stderr.
The earlier failure occurred with GIMP 3.2.6; it has not been freshly reproduced
by this handoff, and no claim is made about its status in later 3.2 releases.

The [historical investigation record](gimp-3.2-investigation-history.md) preserves
library-version comparisons, replacement evidence, test results and their limits.
Its host-derived dependency/native test filesystems were never shipped payloads;
the old scripts, logs and extracted trees are no longer available. Portable
packaging and publisher integration have since been implemented, so their old
handoff tasks are not outstanding work. No production publishing or host package
installation is part of adapter development.

## Native package defaults and dependency ownership

APT supplies application updates. The packaged /etc/gimp/3.0/gimprc sets
(check-updates no), and gimp-release sets package.check-update=false so an
existing user preference cannot re-enable the upstream update channel.
Welcome-dialog preferences remain user-owned and are not changed by this recipe.

Debian 3.0's -Djavascript=disabled and -Dlua=false omit the JavaScript/Lua goat
examples. This repack removes those exact example scripts and their extension
plug-in-path entries instead of recompiling. C, Vala and Python examples remain.
The JS interpreter dependency is no longer needed. This does not prevent users
from installing their own JavaScript/Lua plug-ins and interpreters.

Each binary package declares dependencies for its own staged ELF files,
including dynamically loaded modules' DT_NEEDED entries. runtime-dependencies
maps SONAMEs to Debian expressions with owner "auto"; blank SONAME rows specify
reviewed indirect dependencies and their actual binary-package owner. Shared
requirements may appear in multiple binary packages. Unknown external SONAMEs
fail the build. Source review and targeted runtime tests remain necessary for
dlopen, GI typelibs, scripts and codec backends; ELF inspection cannot prove that
all runtime dependencies have been found. gvfs-backends is suggested for remote
file access and is not needed for an APT-managed update check.

MNG remains enabled with Debian's libmng1; no upstream MNG library is retained.
The inspected official 3.2.6 payloads do not contain file-iff (ILBM).
The recipe does not remove format plug-ins or claim to enable absent features.
Compiler options, compiled URLs and upstream source patches are unchanged.


## Download recovery and live publisher checks

The [publisher incident handoff](gimp-publisher-incident.md) records the original
errors, exact fixes, test coverage and results, evidence paths, Debian version
rules, and later mirror-service discussion. Explicit fallback remains implemented;
the recommendation to remove mirror-list parsing has not been applied.

The AppImage and API documentation downloads retry connection errors, then try
up to three distinct HTTPS mirrors advertised by GIMP's download service when
the selected mirror still fails. Every copy must match the selected upstream
SHA256 before becoming a cached download. Failed response headers and the final
endpoint are retained in the build workspace and logs for diagnosis. Connect
and low-speed timeouts prevent an unresponsive mirror from waiting indefinitely.

`bash tests/gimp-3.2/test-publisher.sh` exercises live downloads and both adapters
in the publisher image using explicit 256 MiB memory and 128-process limits,
dropped capabilities, and the host UID/GID. It retains isolated test storage,
logs, container configuration, and cgroup statistics under `build/`, and checks
real package sizes against the signed repository indexes. It uses a throwaway
signing key and does not start or modify the deployed service. See the
[help packaging notes](gimp-help-3.2.md) for options and reuse of completed work.
Current repack Compose allows 512 MiB, so this coordinator uses a stricter memory
limit. The [extraction memory incident](gimp-extraction-memory-incident.md)
documents why the adapter caps both unsquashfs queues and what remains unverified
from that incident.
The coordinator's signing setup predates later socket isolation; consult the
publisher handoff before claiming a new run matches current production exactly.

The offline GIMP suite includes real-curl local connection resets, retry
exhaustion, and checksum checks. Advertised-mirror fixtures cover failover,
corrupt copies, and bounded failure without relying on live mirror availability.
