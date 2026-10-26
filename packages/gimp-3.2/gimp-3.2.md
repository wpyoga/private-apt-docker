# GIMP 3.2 packaging and deferred investigation

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
