# GIMP 3.2 packaging and deferred investigation

General investigation notes stay outside packages/ so documentation edits do
not allocate unnecessary package revisions.

The gimp-3.2 adapter follows the latest stable 3.2.x entry in GIMP's official
gimp_versions.json, even after a newer series appears. It verifies each official
AppImage's SHA256 and extracts SquashFS as data, without running AppRun or FUSE.
It supports amd64/x86_64 and arm64/aarch64 and targets Debian 13.

The five binary packages are gimp, gimp-data, libgimp-3.0-0, gir1.2-gimp-3.0,
and gimp-bundled-runtime. They share the framework-assigned GIMP version and
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
generated for the final package trees. Developer tooling/headers are not shipped.

## Build verification (2026-10-26)

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
