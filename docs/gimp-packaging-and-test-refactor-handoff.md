# GIMP packaging and test refactor conversation handoff

Recorded 2026-11-13 to preserve the substantive decisions, implementation,
verification, failures and follow-up work from the original packaging conversation.
The chat can be deleted without losing the decisions recorded here. This is a
handoff, not a transcript or a claim that historical tests were rerun today.

## Read this first

The checkout has evolved since this conversation. Current application code is
under [packages/repack/gimp-3.2](../packages/repack/gimp-3.2/config), and manuals
are now an independent [gimp-help-3.2 stream](gimp-help-3.2.md). This conversation
originally implemented a combined application/manual stream. Do not restore that
old arrangement based on the historical account below.

The user originally moved gimp-3.2.md into the package directory. It now lives
at [docs/gimp-3.2.md](gimp-3.2.md). General documentation outside adapters avoids
unnecessary packaging revisions because adapter documentation is a recipe input.
No relocation of that file is required by this handoff.

| Subject | Detailed record or current implementation |
| --- | --- |
| Current application package design and limitations | [GIMP packaging notes](gimp-3.2.md) |
| Full historical library inventory, identified versions and replacement evidence | [Investigation history](gimp-3.2-investigation-history.md) |
| Current manual import and version policy | [Help packaging notes](gimp-help-3.2.md) |
| Later decision superseding this conversation's combined stream | [Help split handoff](gimp-help-split-handoff.md) |
| Later startup defaults and dependency ownership changes | [Startup and dependency handoff](gimp-startup-and-dependencies-handoff.md) |
| Later download, publication and version incidents | [Publisher incident](gimp-publisher-incident.md) |
| Later extraction resource limits | [Extraction memory incident](gimp-extraction-memory-incident.md) |
| AppImage build environment and version provenance | [AppImage build-base research](gimp-appimage-build-base.md) |
| Test commands and operator contract | [README](../README.md#local-testing) |
| Framework rationale | [Architecture](../ARCHITECTURE.md) |
| Final Vim tangent | [Vim and final newlines](vim-final-newlines.md) |

## Scope and working agreements

The original objective was to turn the official GIMP 3.2 AppImage into native
Debian packages for the private repository, replacing external bundled libraries
with compatible Debian providers while keeping the newer private babl/GEGL.
The work then expanded to tools, headers, API documentation, user manuals and
package-specific test organization.

The user asked for action and tests after planning, then deferred the unresolved
TIFF issue and asked to finish packaging. Usage limits interrupted work; later
requests to resume continued the same objective. No production publication or
deployment was performed as part of the original implementation.

The following working agreements should survive deletion of the chat. Most are
also recorded in [AGENTS.md](../AGENTS.md):

- Run commands in batches with both output streams redirected to named logs.
  Wait for completion or a bounded timeout before reading them. Do not ingest
  real-time output merely to monitor progress. Tell the user where logs are.
- Preserve failure evidence. A failed check must remain distinguishable from
  a later passing retry; record harness mistakes as well as product failures.
- Reuse verified downloads and successful builds. Remove superseded temporary
  extractions, staging trees and redundant artifacts when no pending issue needs
  them. Keep useful source downloads. This does not authorize deleting stored
  repository packages, signing material or production state.
- Run host-side coordinators as the host user. Containers writing bind-mounted
  workspaces use the host UID/GID. Root package installation belongs in container
  image layers.
- Package-specific checks concern that package. Run real signing tests when
  signing code changes or when intentionally running the full suite.
- Write source changes directly in reviewable files; the user specifically
  rejected using Python to write the code. This does not prohibit Python where
  the repository already uses it for metadata, fixtures or bookkeeping.
- Continue authorized reversible work without repeated confirmation. A sandbox
  approval requirement still applies when execution actually requires it.
- Preserve user staging and unrelated changes. Never stage, reset or discard
  them as part of cleanup or documentation work.

## External library investigation and final selection

The user asked for the bundled external versions, rather than a broad historical
version investigation. Version identification used embedded release strings,
static inspection of getters/constants, package metadata, build IDs and verified
Debian package provenance. Some libraries do not expose an independently usable
source-release number. A SONAME, ABI number or pkg-config version need not be
the upstream release number.

The final experimental selection removed every external runtime family and kept
only private babl/GEGL, their modules and typelibs. The historical report counted
250 external SONAME families represented by 280 files/links: 235 exact upstream
release matches and 15 explicitly reviewed compatible families. The broader
inventory had a different scope; do not combine those counts.

The user accepted consistent releases within the OpenSSL pair and Mesa family;
there was no need to independently establish a release string in every component.
The saved findings include:

| Component | Bundled release | Historical Debian provider | Decision |
| --- | --- | --- | --- |
| OpenSSL crypto/SSL | 3.5.6, SSL inferred from the pair | 3.5.7-1~deb13u3 | Replace together after compatibility review |
| Mesa EGL/GLX/Gallium | 25.0.7, frontend releases inferred | 25.0.7-2+deb13u1 | Replace the complete family |
| libuuid | util-linux 2.41 | 2.41.5-0+deb13u1 | Replace after interface review |
| libpoppler | 25.03.0 | 25.03.0-5+deb13u4 | Replace |
| libjbig2dec | 0.20 | 0.20-1+deb13u1 | Replace |
| libheif | 1.19.8 | 1.23.6-2~deb13u1 | Replace with all six distro plugins |
| libXpm | Release remained unknown | 1:3.5.17-1+deb13u1 | Replace after symbol and runtime checks |
| babl | 0.1.128 | Stable then provided 0.1.114 | Keep private |
| GEGL | 0.4.72 | Stable then provided 0.4.62 | Keep private |

These are dated observations, not current archive queries or universal version
floors. The complete comparison and evidence are preserved in the investigation
history rather than duplicated here.

OpenSSL and libuuid were not retained merely because patch versions differed.
They were ultimately removed following ABI/interface review and tests. Matching
major/minor numbers alone would not have established compatibility. Likewise,
the user's Debian security/backports compatibility argument supported reviewing
the distro replacement; it did not eliminate the need to examine actual imports,
providers, plugin families and runtime behavior.

For libXpm, similar readelf dynamic sections were useful supporting evidence,
but matching VERNEED/VERNEEDNUM/VERSYM addresses or counts does not compare their
contents or prove ABI compatibility. Changes to GNU_HASH/STRTAB addresses and
STRSZ can result from ELF path editing. FINI offsets are code-layout details.
The later review reported all 34 exported entries retained and successful XPM
runtime checks. Its exact bundled release was never established.

Mesa's private Gallium filename differed between the bundle and distro despite
the same upstream release. Replacing just its backend would have left a broken
frontend/backend combination. OpenSSL and HEIF were also handled as families.

The user installed libheif-plugin-j2kdec and libheif-plugin-j2kenc after the first
check. The final checks reported all six system HEIF plugins present and usable:
aomenc, dav1d, j2kdec, j2kenc, libde265 and x265. The final installed libheif
version was 1.23.6, superseding an earlier 1.23.4 observation. Plugin source
release strings were not independently identified in the bundled files.

Seeing libexiv2, libgexiv2, libgjs, libinih, libinireader or libmozjs in an old
dependency-root did not show that they were still shipped. That directory was a
host-derived dependency/test filesystem, distinct from the selected package
payload. Inspect the final staging trees or .deb contents to establish what is
shipped. Later work also removed the JavaScript goat example and its interpreter
requirement; consult the current startup/dependency notes for that decision.

Symlinks to system libraries were suggested as a possible test workaround when
search paths failed. The production design uses native paths, declared APT
dependencies, ELF patching and a launcher. It does not depend on reproducing an
old dependency-root or generating host-specific links during packaging.

## Native package design and questions resolved

The final core application family has eight binary packages:

| Package | Purpose |
| --- | --- |
| gimp | Application, format plugins and integration |
| gimp-data | Architecture-independent application resources |
| libgimp-3.0-0 | GIMP 3 API runtime libraries |
| gir1.2-gimp-3.0 | GIMP introspection typelibs |
| gimp-bundled-runtime | Matching private babl/GEGL libraries, modules and typelibs |
| libgimp-3.0-bin | gimptool, command aliases and manpage |
| libgimp-3.0-dev | GIMP SDK plus matching private babl/GEGL development files |
| libgimp-3.0-doc | Matching generated HTML API reference |

The 3.0 in API names and directories does not mean the application is version
3.0. GIMP 3.2 continues that API naming. Debian-style package relationships were
preferred: exact version dependencies between matching runtime, tools, typelibs
and SDK; reviewed minimums or Debian-baseline requirements for external packages.
Debian's own dev package pins matching runtime packages, so mixing a distro dev
package with an independently versioned replacement runtime is not a general
solution.

Use the distro gimp-data-extras package. Its collection version 1:2.0.4-0.2 is
independent of GIMP's application version. It is suggested, not repackaged.
Individual legacy scripts were not all tested.

The application build selects official stable 3.2.x metadata and verifies the
AppImage SHA256. SquashFS is extracted as data without executing AppRun, FUSE or
target binaries. The fixed layout and ELF architecture are validated. Host
patchelf edits amd64 and arm64 ELF files; a cross compiler is unnecessary for
this binary editing. Static arm64 inspection is separate from arm64 execution.

"Native layout" means installing GIMP-owned files into ordinary Debian paths
rather than preserving an AppDir tree. The private runtime sits below
/usr/lib/MULTIARCH/gimp/bundled. Existing distro babl/GEGL remain installed and
unchanged. Upstream's newer versions were required by the inspected build:
GIMP needed GEGL >= 0.4.66 and bundled GEGL needed babl >= 0.1.116.

The SDK contains corresponding private babl/GEGL development files, normally
provided by libbabl-dev/libgegl-dev. Headers live below
/usr/include/gimp-3.0/bundled; distinct gimp-babl-0.1.pc and gimp-gegl-0.4.pc names
avoid colliding with distro pkg-config entries. GIMP's entries reference them
and supply private include/link/runtime paths. The AppImage does not supply
GIR XML or static archives, so those development artifacts are not promised.

One actual packaging failure was an ownership collision involving
libgegl-npd-0.4.so. It is a real unversioned runtime library, not an ordinary
development linker symlink. The correction copies only actual linker symlinks
into the development package and leaves that runtime file with its owner.

The gimptool manpage template came from docs/gimptool.1.in in GIMP's official
GIMP_3_2_6 source tag. Generated API HTML comes from the matching upstream
gimp-api-docs-VERSION.tar.xz and SHA256SUMS. Those are distinct from user manuals.

The static runtime-dependencies map replaced runtime-libraries.tsv,
runtime-extra-dependencies and heif-dependencies. Its pipe-separated rows name
a Debian expression, expected SONAMEs and dependency ownership. HEIF's library
and six plugins are embedded there, not maintained in a separate file. The map
both translates external SONAMEs into Debian dependencies and makes new linked
requirements fail visibly. It is not a dynamic comparison with the build host.
Current ownership includes auto assignment from each staged package's ELF files;
later improvements are described in the startup/dependency handoff.

Do not blindly copy Debian GIMP 3.0 Depends. The AppImage originally includes
GEGL's external dependencies, but dropping those copies requires declaring their
distro providers. It also contains different build choices: GIMP 3.0 used
appstream-glib/libappstream-glib8, while this 3.2 build uses AppStream and
libappstream.so.5/libappstream5. They are different APIs concerning application
metadata, not interchangeable alternatives for the same linked library.

copyright.in renders a licensing/source notice for newly assembled packages.
Other adapters can preserve upstream Debian copyright instead; absence of that
template elsewhere does not imply GIMP needs no notice. The generated notice is
not a complete per-file licensing audit.

The official AppImage has AppRun. Debian normally invokes its GIMP ELF directly.
Our launcher remains necessary even after embedding RUNPATH: the private layout
also needs Babl/GEGL module directories and GI typelib discovery. Moreover,
RUNPATH is attached to individual ELF objects; launching a child system Python
or GJS process does not transfer the parent's RUNPATH into that executable.
The launcher's LD_LIBRARY_PATH, BABL_PATH, GEGL_PATH and GI_TYPELIB_PATH reach
those child processes. It sets no private HEIF plugin path.

Debian-based provenance does not make the AppImage identical to Debian's GIMP
package. Application release, private library versions, build options, resource
selection, patches, launch environment and package metadata can differ. The
current recipe repacks upstream binaries; it does not reproduce every Debian
source patch by virtue of sharing a Debian base.

## Manuals and the obsolete post-install scripts

During this conversation the user explicitly required one gimp-3.2 adapter with
multiple input artifacts, rather than a separate manual build stream. It built
eight core packages plus 32 language packages and gimp-help-common: 41 outputs
per architecture, with Architecture: all packages shared by the framework.
Manual inputs were pinned to Debian sid 3.2.0-3; their repack versions followed
GIMP, while X-Upstream-Version retained their actual source version.

All 33 real Debian manual packages were fetched and examined, rather than
extrapolating from German help. Only de, en, fr and sv contained postinst scripts.
They were identical except for the language path. Their full operative content
was a /bin/sh -e script that removed an existing non-symlink documentation
directory with rmdir, then created a relative symlink to gimp-help-common when
the language documentation path did not exist. There were no additional
debhelper operations hidden from that review.

The German script was recorded as follows; substitute en, fr or sv for de in
the other three scripts:

```sh
#!/bin/sh -e
# if /usr/share/doc/gimp-help-de is a directory, it's probably from an older
# package, so remove it and make the symlink
if [ ! -L /usr/share/doc/gimp-help-de -a  -d /usr/share/doc/gimp-help-de ];
then
    rmdir /usr/share/doc/gimp-help-de
fi
if [ ! -e /usr/share/doc/gimp-help-de ]; then
    ln -s gimp-help-common /usr/share/doc/gimp-help-de
fi
```

Each language already shipped the documentation symlink. gimp-help-common owned
the real common documentation directory, and every language depended exactly on
the matching common version. These were legacy directory-to-symlink migrations,
not language-specific help generation. The user directed discarding the scripts
and recording a possible Debian bug report for later. No bug was filed.

Potential report details include rmdir failing on nonempty historical directories,
no maintainer-script argument dispatch, and ! -e treating a dangling symlink as
absent before ln attempts to create an existing name. Establish actual supported
upgrade scenarios and Debian's migration requirements before reporting a bug.
Current import validation still removes only the known scripts and rejects
unexpected maintainer files, preserving licensing and payload links.

The later, separately authorized split superseded the combined design. Current
help discovery updates automatically from sid, repackages all declared manuals
without requiring clients to enable sid, and uses an epoch to upgrade from old
application-derived versions. For example, Debian 3.2.0-3 becomes tracked
1:3.2.0+deb3 and an initial repack version 1:3.2.0+deb3-1. Preserve that transition
and the exact language/common relationships; see the help split handoff.

## Historical verification and evidence limits

The original five-package stage and subsequent eight-package/combined-help stage
were different checkpoints. Their package counts and recipe fingerprints should
not be mixed. The original final combined build used GIMP 3.2.6-1 for both
architectures, with 41 outputs per architecture and 48 unique package identities
after sharing architecture-independent outputs.

Reported checks for that expanded stage included:

- All 14 then-existing GIMP regression tests passed.
- Package identity, shared recipe metadata, Installed-Size, generated index
  values, ownership and external DT_NEEDED coverage passed.
- Clean amd64 APT installation and Debian GIMP removal without purge followed
  by repack installation passed. Existing configuration was preserved.
- All 260 ELF objects in the expanded amd64 payload resolved under relocation
  checks. Earlier five-package reports counted 259; that is a different payload.
- The SDK compiled and ran a C program with distro babl/GEGL development packages
  coinstalled. System library hashes and versions remained unchanged.
- English help, headless operations and Xvfb GUI checks passed. GEGL inversion,
  XCF, PNG, JPEG, TIFF with thumbnails disabled, WebP, HEIC, AVIF, JPEG XL, XPM
  and SVG were checked using dimensions and pixels.
- Arm64 packages built and received static inspection. No arm64 application,
  desktop or codec execution was established.

These results supported completion of the packaging work, with explicit
limitations. They did not constitute publication, deployment, universal plugin
compatibility or proof that every future 3.2 release works.

The original evidence locations included build/gimp-expanded-live/gimp/output/,
build/gimp-expanded-logs/, build/gimp-help-inspection/ and
build/gimp-install-IoF2og/. Original logs included
family-build-20261026T233552Z.log, package-regression-20261026T233552Z.log,
installation-20261026T233552Z.log and replacement-20261027T003035Z.log.
Those directories are absent from today's checkout. These names preserve
provenance; they are not links to currently available proof. Do not reconstruct
their content or claim the original artifacts can still be inspected.

### Deferred TIFF failure

A 64x64 TIFF exported with include-thumbnail=True reopened through Gimp.file_load
as 256x256 and failed the size assertion with batch exit 64. There was also an
old-style JPEG compression warning. Disabling thumbnails passed the round trip.
The user deferred investigation and asked to finish packaging.

Earlier notes reported the same failure with the preserved original extracted
runtime and libtiff 4.7.0. That did not establish a controlled run of the untouched
AppImage through AppRun. Possible causes include export/import behavior, thumbnail
selection by the harness, or library behavior. No cause was established, and
thumbnail=False is a passing control rather than a fix.

The original reproducer and failing TIFF/log are gone. To resume, adapt the
current smoke test in an isolated profile, enable thumbnails explicitly, retain
the TIFF and logs, compare the matching untouched AppImage, and inspect image
directories with an independent TIFF reader. Current smoke coverage disables
thumbnails and does not cover this deferred case.

### Other failures and outstanding checks

An early nine-package draft failed during a direct APT/dpkg upgrade for an
undiagnosed reason. The successful replacement test removed Debian GIMP without
purging and then installed the repack; that is not direct-upgrade coverage.
Third-party GIMP 3 plugins, including an actual G'MIC plugin, were not validated.
The gmic CLI would not substitute for that test. Arm64 runtime, a complete
per-file copyright audit and actual desktop help browsing retain their own
validation boundaries. Current maintained notes give follow-up criteria.

Earlier harness failures included overly broad extraction/inspection, a checker
incorrectly treating Debian field names as case-sensitive, and missing Xvfb
temporary-directory setup. These were corrected before the relevant successful
runs; they should not be confused with the unresolved TIFF behavior.

## Docker use, disk exhaustion and ownership

Docker provided disposable Debian installation, dependency, SDK, GUI and codec
test environments. Those lengthy runs were not evidence that every repack
operation inherently requires Docker. Binary extraction and ELF editing use
ordinary host tools; the project's production publisher itself runs in a
container. Test image creation does not deploy that publisher.

Repeated AppImage extractions, duplicated manuals, staging trees, package outputs
and Docker layers exhausted local disk space. The user removed unused Docker
images and ran a buildx cleanup. One run had already passed clean installation,
SDK and GUI checks when Docker failed writing its buildx activity timestamp due
to the full filesystem; the replacement phase had not started. It was rerun
after cleanup. Preserve this distinction rather than treating the whole earlier
command as an application test failure.

build/gimp-install-62UICa was host root:root with mode 700 because a host-side
coordinator had accidentally run as root inside a container with a bind mount.
mktemp's private permissions were expected; its owner was wrong. The host user
could not traverse it. The prevention was to run the coordinator directly as
the host user, reject EUID 0, and use host UID/GID for bind-mounted writes.
Do not solve this by making all test contexts world-readable or writable.

The user authorized removal of superseded attempts. Old contexts and obsolete
extractions were removed; useful source downloads, successful packages and
failure evidence were retained at that checkpoint. Identical manual outputs
were deduplicated and successful builds reused. Cleanup did not touch production
packages or keys. The replacement context was checked as host-owned with mode
700. Those old local contexts are no longer present today.

## Test refactor implemented in this conversation

After packaging, the user requested that package tests live in matching stream
directories and non-package tests remain under tests/. Shared test utilities
were deliberately separated from production publisher code in tests/lib/.
One runner with selectors was chosen and implemented.

| Entry or directory | Responsibility |
| --- | --- |
| tests/run.sh | Public shell entry point; establish context and log bounded commands |
| tests/run.py | Validate selectors and explicitly discover each selected test root |
| tests/test_*.py | Framework, setup and runner regression tests |
| tests/test-signed-repo.sh | Real signing/APT integration using isolated state and a throwaway key |
| tests/STREAM/ | Stream-specific regressions, fixtures and optional installation coordinators |
| tests/lib/publisher_test_support.py | Shared Python test fixtures and publisher test support |
| tests/lib/common.sh | Shared shell root validation and run_logged |

The original move covered codex, ghostty, gimp-3.2 and zed. GIMP's Dockerfile,
auditor, smoke scripts, SDK fixture and real-build checker moved together; the
installation entry became tests/gimp-3.2/test-install.sh. Its Docker context
copies explicit fixture files rather than accidentally including test modules
and caches. The later help split has its own tests/gimp-help-3.2 directory.

| Command from project root | Scope |
| --- | --- |
| bash tests/run.sh | All offline regressions, then real signing/APT integration |
| bash tests/run.sh --offline | All offline regressions only |
| bash tests/run.sh --framework | Framework/setup/runner regressions only |
| bash tests/run.sh gimp-3.2 | Selected application regressions only |
| bash tests/run.sh gimp-3.2 gimp-help-3.2 | Both selected stream regression suites |
| bash tests/test-signed-repo.sh | Standalone real signing/APT integration |

Selected regression runs do not implicitly build Docker images, run installation
tests or invoke the real signing check. The current grouped packages/repack,
packages/rebuild and packages/redistribute layout is supported by the runner;
tests remain keyed by stream directory name directly under tests/.

Ordinary recursive unittest discovery can skip directories such as gimp-3.2
because they are not importable Python package names. The runner explicitly
discovers each root, validates selectors, rejects missing tests, deduplicates
repeated selectors, and fails before execution for unknown names or conflicting
selection flags. Later changes also isolate reused test module names.

run_logged redirects child stdout/stderr into its named log, prints the location,
uses timeout with a kill grace period, and preserves nonzero status and failure
evidence. The entry point establishes its context rather than requiring the
operator to export production variables.

The refactor's historical validation reported all 100 existing regression tests
preserved and five new runner tests added: 105 passed without skips in the test
image. The full run also passed the real signing check. A package-selected GIMP
run passed 14 tests; the relocated replacement coordinator passed using existing
packages and cached layers. Shell syntax and final working-tree whitespace checks
passed. No production package recipe was changed by that refactor.

The five new coverage areas were explicit discovery/selection, invalid selection
rejection, signing only for a full invocation, logged failure status/evidence and
bounded timeout. These are behavioral checks rather than tests of formatting.
The suite has since grown; 105 is the historical count, not today's expected
total.

Original refactor evidence was under build/test-refactor-logs/, including
validation-4Jh2Kc and its recorded nested test-run paths. Those logs are absent
today. An intermediate extra-blank-line whitespace failure was corrected in the
working tree. The user was staging changes during implementation, so that final
check did not imply that every intermediate staged snapshot was identical.

## How to continue without the chat

Read current AGENTS.md, README and architecture first, inspect working-tree
changes, then choose the relevant maintained notes above. The packaging and test
refactor implementation is complete; there is no task to restore obsolete
combined builds, old caches, dependency-root trees or missing historical logs.

For a documentation-only change, check links, facts and whitespace. For package
changes, run the appropriate selected regressions with named logs and a timeout.
Use the real installation coordinator for installation/runtime changes. Only run
the full/signing suite when its scope is warranted. No builds, regression tests,
signing tests, live downloads or deployment were run to write this handoff.

Production revision selection comes from stored packages and embedded recipe
metadata. Historical local versions and placeholder maintainers are not a
production release plan. Publishing, target-machine arm64 checks, direct upgrades,
third-party plugin coverage, the TIFF diagnosis and any Debian bug report require
their own deliberate follow-up; documentation does not mark them complete.

## Handoff verification

For this documentation task, the current architecture, README, application/help
notes, historical inventory, help-split handoff, dependency map, launcher, test
runner and shared helpers were inspected. Local links in the two new documents
were checked, and whitespace checks covered the edited notes and new files.
The original packaging/refactor evidence directories were checked and found
absent. Existing staged and unstaged work was preserved. Inspection and check
logs are under build/documentation-handover/; those are temporary local evidence,
while this document and the linked maintained notes are the durable record.
