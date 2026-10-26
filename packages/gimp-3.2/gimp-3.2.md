# GIMP 3.2 packaging and deferred investigation

These notes intentionally live beside the adapter, as requested. Editing them
changes the recipe checksum and can allocate a packaging revision.

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
expected SONAMEs, and the owning package (gimp or runtime), separated by pipes.
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

The same gimp-3.2 adapter imports all 32 current Debian sid language packages and
gimp-help-common, bringing the complete family to 41 packages per build (48 unique
packages across amd64/arm64). It verifies SHA256 and fixed layout, preserves
licenses, and rewrites exact common-package dependencies to the GIMP stream's
assigned version, e.g. 3.2.6-1. X-Upstream-Version records the original manual
package version, currently 3.2.0-3. The common package contains documentation and
a link to the help directory, rather than owning the actual language files.
Inspection of all 33 checksum-verified Debian 3.2.0-3 packages found postinst
scripts only in de, en, fr, and sv. All four perform the same documentation
symlink migration with their respective package name. The other 28 languages
and common package have no maintainer scripts. At the user's request, discard
these four legacy scripts. All four Debian package payloads already ship their
documentation symlinks pointing to gimp-help-common; preserve those links.
Binary inspection report: build/gimp-help-inspection/scripts.txt; download and
verification log: build/gimp-expanded-logs/help-package-inspection.log.

Potential Debian bug report (deferred, not submitted): gimp-help 3.2.0-3 still
ships these four legacy postinst scripts. They unconditionally try to remove a
real documentation directory with rmdir, so nonempty directories cause package
configuration to fail under sh -e. They do not dispatch on maintainer-script
arguments, and an existing dangling symlink passes ! -e but makes ln -s fail.
Investigate whether the historical migration is still needed, given that the
links are already shipped as package contents. Preserve the original
scripts under build/gimp-help-inspection/control/ as evidence for that report.

The AppImages, API reference archive, and user manual packages are separate
source artifacts processed by one adapter, not separate release streams. The
static help-assets manifest pins source versions, filenames, and SHA256 values
from Debian sid metadata retrieved on 2026-10-26. Updating it changes the recipe
checksum, ensuring a source-only manual update rebuilds the current GIMP family.
Keep its package names synchronized with config's BINARY_PACKAGES. The source
metadata was https://deb.debian.org/debian/dists/sid/main/binary-amd64/Packages.xz;
packages are downloaded directly from the corresponding Debian pool paths.
Clients need only our repository and Debian stable; no sid sources are added.
Help packages are built once per workspace and reused for the second architecture.
The declared language list is static; missing or differently versioned inputs
fail rather than mixing manual releases. Upstream's current manual archive is
source, not the generated HTML archive supplied for the API reference.

Sources: https://docs.gimp.org/download.html,
https://download.gimp.org/gimp/v3.2/api-docs/,
https://packages.debian.org/sid/gimp-help-en,
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
Reproducible real-package tests are in `tests/test-gimp-install.sh` and
`tests/gimp/`; runtime execution testing is amd64 only.

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

Reproducer: gimp-investigation/gimp-repack/tiff-default-thumbnail-test.py.
Saved log: gimp-investigation/gimp-repack/validation-runs/system-runtime-3.2.6-3/
default-tiff-thumbnail.log. Those generated investigation artifacts are deliberately
not copied into adapters or the publisher image.

Earlier investigation notes report the same failure with the preserved original
extracted runtime and libtiff 4.7.0, but do not establish a controlled test of the
untouched AppImage through AppRun. The cause is unresolved: GIMP export/import,
thumbnail selection in the test harness, or shared library behavior remain
possible. Do not attribute it to libtiff or to repackaging without further evidence.
Future investigation should compare the untouched AppImage and inspect the TIFF's
main image/thumbnail directories with an independent reader. This work is deferred
at the user's request and is not a prerequisite for enabling this adapter.

Third-party plugin compatibility and arm64 desktop execution require separate
validation. The investigation's dependency-root/native-root directories are test
filesystems, not shipped payloads. No production publishing or host package
installation is part of adapter development.
