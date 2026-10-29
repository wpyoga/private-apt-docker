# GIMP 3.2.6 investigation history

This preserves useful findings from the 2026-10-26 amd64 AppImage investigation,
consolidated on 2026-10-29 before retiring the local investigation directory.
These are historical observations, not freshly reproduced checks or requirements
for future releases. The maintained [GIMP packaging notes](gimp-3.2.md) describe
the current adapter and outstanding issues.

## Evidence and availability

The source notes were HANDOFF.md, RESUME.md, VALIDATION.md,
STATIC-LIBRARY-VERSIONS.md, DIRECT-VERSION-CHECK.md,
INSTALLED-RUNTIME-COMPARISON.md, and REMAINING-RUNTIME-VERSIONS.md.
Only those seven notes and the original amd64 AppImage remained at consolidation.
The extraction trees, scripts, signed index snapshots, TSV evidence ledgers,
draft packages, test profiles, and validation logs mentioned in them were already
absent. The tables below preserve their reported findings; they cannot replace
those missing primary artifacts or make the old experiment reproducible.

The chronological handoffs contain conflicting checkpoints. The latest RESUME.md
section takes precedence: the final experiment removed every external runtime
family and retained only private babl/GEGL. Instructions to finish the adapter,
retain other libraries, or rerun missing scripts describe superseded work.
The current adapter now supports both architectures, eight core packages, and
independent help packaging; the early nine- and five-package drafts do not
describe today's package split.

## Final experimental runtime selection

The preserved external-runtime subset contained 250 SONAME families represented
by 280 files/links. The final checkpoint reports 235 exact upstream-release
matches removed (264 entries), plus 15 explicitly reviewed compatible families
(16 entries), leaving zero external families. The broader static inventory
contains 275 SONAME rows, including components outside that subset; these scopes
must not be mixed. Private babl 0.1.128 and GEGL 0.4.72, their modules and typelibs
remained, about 42 MiB (draft Installed-Size 42224 KiB).

GIMP required GEGL >= 0.4.66; bundled GEGL required babl >= 0.1.116. The saved
Trixie indexes provided GEGL 0.4.62 and babl 0.1.114, with no matching backports.
This motivated private copies rather than replacing Debian's libraries.

Reviewed replacements included:

| Bundled component | Debian replacement | Reported review evidence |
| --- | --- | --- |
| libblkid 2.41.0 | 2.41.5 | All 125 bundled public symbol names retained |
| libmount 2.41.0 | 2.41.5 | All 348 bundled public symbol names retained |
| Expat 2.7.1 | 2.9.0 | All 69 public names retained; Libtool 11:2:10 to 14:0:13 preserves old interfaces |
| libsystemd metadata 257 | 257.13 | All 892 public names retained |
| OpenSSL 3.5.6 | 3.5.7 | Accepted symbol/version and compatibility review; crypto/SSL treated as a pair |
| libuuid 2.41 | 2.41.5 | Accepted interface compatibility review |
| Xpm, release unknown | 3.5.17 | All 34 exported entries retained; release remained unknown |
| libheif 1.19.8 | 1.23.6 | All 271 public heif_ exports retained; six system codec plugins checked |

Symbol coverage alone does not establish semantic compatibility. The final
selection also received the runtime tests described below. The Expat review
consulted upstream tags R_2_7_1 and R_2_9_0, expat/CMakeLists.txt; it did not
establish a general semantic-versioning guarantee.

Mesa EGL/GLX/Gallium were replaced together. Bundled frontends required
libgallium-25.0.7-2.so, whereas Debian's frontends used
libgallium-25.0.7-2+deb13u1.so. Replacing a backend alone was unsafe despite matching
upstream versions. Consistent releases within the OpenSSL and Mesa groups were
accepted assumptions; direct evidence did not independently identify each member.
libheif and its six plugins were likewise replaced as a complete family, and the
private LIBHEIF_PLUGIN_PATH override was removed. Unknown Xpm/plugin releases
were never retroactively identified by choosing replacements.

The observed indirect libsystemd chain was GTK -> ATK bridge -> D-Bus ->
libsystemd. Depending on libsystemd0 does not require systemd as the init daemon.

## Identification methods and limits

Saved Debian main, updates, security and backports InRelease signatures were
checked with Debian's archive keyring. Index sizes and SHA256 values were checked
against Release metadata. The notes report 138 identifications through GNU build
IDs matched to checksum-verified package-owned host files, 21 through official
Debian archives, and 16 through strings/constants/statically inspected getters;
some evidence overlaps. Twenty-two downloaded official Debian packages were
extracted as data. No library getter or target application was executed for
static identification.

GNU build IDs can survive AppImage ELF path patching: they identify original
build provenance, not identical bytes after patching. Similar versions, matching
SONAMEs, and available Debian providers do not prove compatibility. SuiteSparse
provenance uses the parent source release rather than component ABI numbers.
FreeType headers identify 2.13.3 despite a pkg-config value of 26.2.20; Graphite2
headers identify 1.3.14 despite a pkg-config value of 3.0.1. Xpm's getter value
30411 was not established as an upstream release number.

## Validation results and lessons

The final local five-package 3.2.6-3 drafts used placeholder maintainer metadata;
they were not publisher outputs. The checkpoint reports successful package and
index checks, Installed-Size against staged trees, private-library hash checks,
HEIF plugin checks, and clean-container linker resolution for all 259 ELF objects.
Native, headless and Xvfb image tests passed GEGL inversion, XCF, PNG, JPEG, TIFF
with thumbnails disabled, WebP, HEIC, AVIF, JPEG XL, XPM and SVG dimensions/pixels.
Fresh APT installation and Debian GIMP test/remove-without-purge/reinstall passed,
preserving configuration and Debian babl/GEGL package versions and file hashes.
These results apply to those amd64 drafts, not every later build or arm64 GUI.

A 64x64 TIFF exported with include-thumbnail=True reopened as 256x256 and failed
with batch exit 64, accompanied by an old-style JPEG compression warning. Earlier
notes report this with the preserved original runtime too, but no controlled
untouched-AppImage/AppRun comparison was established. Disabling thumbnails passed;
it did not fix or diagnose the default behavior. See the maintained notes for
follow-up steps and other validation limits.

A direct APT/dpkg upgrade attempt failed for an undiagnosed reason during an
earlier nine-package experiment. Work switched to removal without purging followed
by installation. The failure does not establish that today's adapter cannot
upgrade; neither does the passing replacement sequence verify a direct upgrade.

Useful test-harness lessons:

- A host fallback filesystem initially lacked GExiv2 introspection and libmypaint.
  Cached Debian archives filled test-only gaps; clean containers used APT.
  Such host-derived trees are not shipped payloads or proof of dependency closure.
- Python fallback links could run under a host-system prefix and misdirect babl
  executable-relative module discovery. Keeping both python3 and its python3.13
  executable in the test view removed that warning. This did not prove a normal
  installation needed a BABL_PATH override; the current private layout has its
  own launcher requirements.
- A missing GTK icon caused an early GUI crash. Adding adwaita-icon-theme,
  librsvg2-common and fonts resolved it. Fresh profiles separated headless/GUI runs.
- Delayed allocation changed measured sizes in early drafts; syncing staged
  files before measurement stabilized checks. Final Installed-Size and published
  index values still require verification for each build.
- ELF resolution cannot cover every dlopen, typelib, script or resource dependency.
  Codec and desktop checks complement static dependency inspection.
- Tests used isolated profiles, disposable containers and network-disabled runtime
  checks. No host package installation, production keys or publication occurred.

An earlier installation recipe recorded Debian Trixie base digest
sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad.
APT dependencies were fetched during image builds and were not version-locked;
the digest alone cannot reproduce that dependency environment.

## Historical direct version checks

## Newly identified versions

| Library | Bundled release | Direct evidence |
| --- | --- | --- |
| libuuid.so.1 | 2.41 | Embedded FDO packaging note identifies util-linux 2.41-5. The upstream release is 2.41; -5 is the Debian revision. |
| libpoppler.so.147 | 25.03.0 | Embedded string at virtual address 0x2b3cab is passed to the `poppler pdftops version: {0:s}` format string at 0x2f8138 in PSOutputDev::writeHeader. |
| libjbig2dec.so.0 | 0.20 | jbig2_ctx_new_imp checks the supplied major against zero and minor against 0x14 (20), and supplies 0 and 20 to its incompatible-header/library-version diagnostic. |

## Versions not independently exposed by these files

| Libraries | What the direct check establishes |
| --- | --- |
| libssl.so.3 | No embedded release string or own release-version getter found. Its bundled libcrypto identifies OpenSSL 3.5.6; 3.5.6 is the likely paired release, but libssl itself does not confirm it. SSL_get_version and similar functions describe TLS protocol versions. |
| libEGL_mesa.so.0, libGLX_mesa.so.0 | No embedded release string or release-version getter found. The bundled Gallium backend identifies Mesa 25.0.7; the frontends themselves do not confirm that release. |
| Six libheif plugins: aomenc, dav1d, j2kdec, j2kenc, libde265, x265 | No embedded libheif release strings found. The accompanying libheif is 1.19.8. Exported plugin_info structures and codec-version functions do not establish the plugins' libheif source release. |
| libXpm.so.4 | XpmLibraryVersion returns 30411 (0x76cb). No upstream release string found; this numeric interface value has not been established as the package release. |


## Historical installed-runtime comparison

This final comparison table reports installed amd64 versions on 2026-10-26,
not necessarily the versions in every earlier snapshot or the current archive.
An earlier host had libheif 1.23.4; final clean-container checks used 1.23.6.

| Library | Bundled | Installed package version | Action |
| --- | --- | --- | --- |
| libcrypto.so.3 | 3.5.6 | 3.5.7-1~deb13u3 | Remove bundled copy |
| libssl.so.3 | 3.5.6 | 3.5.7-1~deb13u3 | Remove bundled copy |
| libEGL_mesa.so.0 | 25.0.7 | 25.0.7-2+deb13u1 | Remove bundled copy |
| libGLX_mesa.so.0 | 25.0.7 | 25.0.7-2+deb13u1 | Remove bundled copy |
| libgallium-25.0.7-2.so | 25.0.7 | 25.0.7-2+deb13u1 | Remove bundled copy |
| libpoppler.so.147 | 25.03.0 | 25.03.0-5+deb13u4 | Remove bundled copy |
| libjbig2dec.so.0 | 0.20 | 0.20-1+deb13u1 | Remove bundled copy |
| libuuid.so.1 | 2.41 | 2.41.5-0+deb13u1 | Remove bundled copy |
| libheif.so.1 | 1.19.8 | 1.23.6-2~deb13u1 | Remove bundled copy |
| libXpm.so.4 | UNKNOWN | 1:3.5.17-1+deb13u1 | Remove bundled copy |
| libheif-aomenc.so | UNKNOWN | 1.23.6-2~deb13u1 | Remove bundled copy |
| libheif-dav1d.so | UNKNOWN | 1.23.6-2~deb13u1 | Remove bundled copy |
| libheif-j2kdec.so | UNKNOWN | 1.23.6-2~deb13u1 | Remove bundled copy |
| libheif-j2kenc.so | UNKNOWN | 1.23.6-2~deb13u1 | Remove bundled copy |
| libheif-libde265.so | UNKNOWN | 1.23.6-2~deb13u1 | Remove bundled copy |
| libheif-x265.so | UNKNOWN | 1.23.6-2~deb13u1 | Remove bundled copy |

Mesa EGL, GLX, and Gallium are replaced together. OpenSSL is replaced as
a pair; libheif and its six plugins are replaced as a complete family.

## Saved static inventory

The following inventory is the saved report's snapshot. Later direct checks and
accepted component assumptions resolved some unknowns; its counts and unknown
labels are retained as historical report data, not final runtime decisions.
Stable/backports versions describe saved indexes, not current availability.

## Main findings

- GIMP 3.2.6 declares GEGL >= 0.4.66; stable provides 0.4.62.
- Bundled GEGL 0.4.72 declares babl >= 0.1.116; stable provides 0.1.114.
- Neither babl nor GEGL appears in the signed Trixie backports index.
- TIFF is 4.7.0 on both sides; the round-trip discrepancy cannot be
  explained by different upstream release numbers alone.
- FreeType is 2.13.3 and Graphite2 is 1.3.14 according to their headers;
  the pkg-config values 26.2.20 and 3.0.1 are not their release versions.
- Unknown releases were not classified by version alone; later reviewed replacements
  used additional evidence described above.

## Stable comparison counts

- Debian-newer-different-major-minor: 2
- Debian-newer-same-major-minor: 4
- Debian-older-different-major-minor: 9
- Debian-older-same-major-minor: 4
- bundle-release-unknown: 11
- different-version-detail: 2
- same-upstream-release: 243

## Known release versions

| SONAME | Bundle | Debian stable | Backports | Stable comparison |
| --- | --- | --- | --- | --- |
| libEGL.so.1 | 1.7.0 | 1.7.0-1+b2 | unavailable | same-upstream-release |
| libEGL_mesa.so.0 | 25.0.7 | 25.0.7-2+deb13u1 | 26.1.6-1~bpo13+1 | same-upstream-release |
| libGL.so.1 | 1.7.0 | 1.7.0-1+b2 | unavailable | same-upstream-release |
| libGLESv1_CM.so.1 | 1.7.0 | 1.7.0-1+b2 | unavailable | same-upstream-release |
| libGLESv2.so.2 | 1.7.0 | 1.7.0-1+b2 | unavailable | same-upstream-release |
| libGLX.so.0 | 1.7.0 | 1.7.0-1+b2 | unavailable | same-upstream-release |
| libGLX_mesa.so.0 | 25.0.7 | 25.0.7-2+deb13u1 | 26.1.6-1~bpo13+1 | same-upstream-release |
| libGLdispatch.so.0 | 1.7.0 | 1.7.0-1+b2 | unavailable | same-upstream-release |
| libICE.so.6 | 1.1.1 | 2:1.1.1-1 | unavailable | same-upstream-release |
| libINIReader.so.0 | 59 | 59-1 | unavailable | same-upstream-release |
| libIex-3_1.so.30 | 3.1.13 | 3.1.13-2 | unavailable | same-upstream-release |
| libIlmThread-3_1.so.30 | 3.1.13 | 3.1.13-2 | unavailable | same-upstream-release |
| libImath-3_1.so.29 | 3.1.12 | 3.1.12-1+b3 | unavailable | same-upstream-release |
| libLLVM.so.19.1 | 19.1.7 | 1:19.1.7-3+b1 | unavailable | same-upstream-release |
| libLerc.so.4 | 4.0.0 | 4.0.0+ds-5 | unavailable | same-upstream-release |
| libOpenEXR-3_1.so.30 | 3.1.13 | 3.1.13-2 | unavailable | same-upstream-release |
| libSM.so.6 | 1.2.6 | 2:1.2.6-1 | unavailable | same-upstream-release |
| libX11-xcb.so.1 | 1.8.12 | 2:1.8.12-1 | unavailable | same-upstream-release |
| libX11.so.6 | 1.8.12 | 2:1.8.12-1 | unavailable | same-upstream-release |
| libXau.so.6 | 1.0.11 | 1:1.0.11-1 | unavailable | same-upstream-release |
| libXcomposite.so.1 | 0.4.6 | 1:0.4.6-1 | unavailable | same-upstream-release |
| libXcursor.so.1 | 1.2.3 | 1:1.2.3-1 | unavailable | same-upstream-release |
| libXdamage.so.1 | 1.1.6 | 1:1.1.6-1+b2 | unavailable | same-upstream-release |
| libXdmcp.so.6 | 1.1.5 | 1:1.1.5-1 | unavailable | same-upstream-release |
| libXext.so.6 | 1.3.4 | 2:1.3.4-1+b3 | unavailable | same-upstream-release |
| libXfixes.so.3 | 6.0.0 | 1:6.0.0-2+b4 | unavailable | same-upstream-release |
| libXft.so.2 | 2.3.6 | 2.3.6-1+b4 | unavailable | same-upstream-release |
| libXi.so.6 | 1.8.2 | 2:1.8.2-1 | unavailable | same-upstream-release |
| libXinerama.so.1 | 1.1.4 | 2:1.1.4-3+b4 | unavailable | same-upstream-release |
| libXmu.so.6 | 1.1.3 | 2:1.1.3-3+b4 | unavailable | same-upstream-release |
| libXrandr.so.2 | 1.5.4 | 2:1.5.4-1+b3 | unavailable | same-upstream-release |
| libXrender.so.1 | 0.9.12 | 1:0.9.12-1 | unavailable | same-upstream-release |
| libXt.so.6 | 1.2.1 | 1:1.2.1-1.2+b2 | unavailable | same-upstream-release |
| libXtst.so.6 | 1.2.5 | 2:1.2.5-1 | unavailable | same-upstream-release |
| libXxf86vm.so.1 | 1.1.4 | 1:1.1.4-1+b4 | unavailable | same-upstream-release |
| libaa.so.1 | 1.4p5 | 1.4p5-51.1+b1 | unavailable | same-upstream-release |
| libacl.so.1 | 2.3.2 | 2.3.2-2+b1 | unavailable | same-upstream-release |
| libamd.so.3 | 7.10.1 | 1:7.10.1+dfsg-1 | unavailable | same-upstream-release |
| libaom.so.3 | 3.12.1 | 3.12.1-1+deb13u1 | unavailable | same-upstream-release |
| libappstream.so.5 | 1.0.5 | 1.0.5-1 | unavailable | same-upstream-release |
| libarchive.so.13 | 3.7.4 | 3.7.4-4+deb13u1 | unavailable | same-upstream-release |
| libasound.so.2 | 1.2.14 | 1.2.14-1+deb13u1 | 1.2.16.1-1~bpo13+1 | same-upstream-release |
| libassuan.so.9 | 3.0.2 | 3.0.2-2 | unavailable | same-upstream-release |
| libatk-1.0.so.0 | 2.56.2 | 2.56.2-1+deb13u2 | 2.62.1-1~bpo13+1 | same-upstream-release |
| libatk-bridge-2.0.so.0 | 2.56.2 | 2.56.2-1+deb13u2 | 2.62.1-1~bpo13+1 | same-upstream-release |
| libatomic.so.1 | 14.2.0 | 14.2.0-19 | unavailable | same-upstream-release |
| libatspi.so.0 | 2.56.2 | 2.56.2-1+deb13u2 | 2.62.1-1~bpo13+1 | same-upstream-release |
| libavahi-client.so.3 | 0.8 | 0.8-16 | unavailable | same-upstream-release |
| libavahi-common.so.3 | 0.8 | 0.8-16 | unavailable | same-upstream-release |
| libbabl-0.1.so.0 | 0.1.128 | 1:0.1.114-2 | unavailable | Debian-older-same-major-minor |
| libblas.so.3 | 3.12.1 | 3.12.1-6 | unavailable | same-upstream-release |
| libblkid.so.1 | 2.41.0 | 2.41.5-0+deb13u1 | unavailable | Debian-newer-same-major-minor |
| libbrotlicommon.so.1 | 1.1.0 | 1.1.0-2+deb13u1 | unavailable | same-upstream-release |
| libbrotlidec.so.1 | 1.1.0 | 1.1.0-2+deb13u1 | unavailable | same-upstream-release |
| libbrotlienc.so.1 | 1.1.0 | 1.1.0-2+deb13u1 | unavailable | same-upstream-release |
| libbsd.so.0 | 0.12.2 | 0.12.2-2 | unavailable | same-upstream-release |
| libbz2.so.1.0 | 1.0.8 | 1.0.8-6 | unavailable | same-upstream-release |
| libc.so.6 | 2.41 | 2.41-12+deb13u4 | unavailable | same-upstream-release |
| libcairo-gobject.so.2 | 1.18.4 | 1.18.4-1+b1 | unavailable | same-upstream-release |
| libcairo.so.2 | 1.18.4 | 1.18.4-1+b1 | unavailable | same-upstream-release |
| libcamd.so.3 | 7.10.1 | 1:7.10.1+dfsg-1 | unavailable | same-upstream-release |
| libcanberra-gtk3.so.0 | 0.30 | 0.30-18 | unavailable | same-upstream-release |
| libcanberra.so.0 | 0.30 | 0.30-18 | unavailable | same-upstream-release |
| libcap.so.2 | 2.75 | 1:2.75-10+deb13u1+b3 | unavailable | same-upstream-release |
| libccolamd.so.3 | 7.10.1 | 1:7.10.1+dfsg-1 | unavailable | same-upstream-release |
| libcdt.so.5 | 2.42.4 | 2.42.4-3 | unavailable | same-upstream-release |
| libcfitsio.so.10 | 4.6.2 | 4.6.2-2 | unavailable | same-upstream-release |
| libcgraph.so.6 | 2.42.4 | 2.42.4-3 | unavailable | same-upstream-release |
| libcholmod.so.5 | 7.10.1 | 1:7.10.1+dfsg-1 | unavailable | same-upstream-release |
| libcloudproviders.so.0 | 0.3.6 | 0.3.6-2 | unavailable | same-upstream-release |
| libcolamd.so.3 | 7.10.1 | 1:7.10.1+dfsg-1 | unavailable | same-upstream-release |
| libcolord.so.2 | 1.4.7 | 1.4.7-3 | unavailable | same-upstream-release |
| libcom_err.so.2 | 1.47.2 | 1.47.2-3+b12 | unavailable | same-upstream-release |
| libcrypto.so.3 | 3.5.6 | 3.5.7-1~deb13u3 | unavailable | Debian-newer-same-major-minor |
| libcups.so.2 | 2.4.10 | 2.4.10-3+deb13u2 | unavailable | same-upstream-release |
| libcurl-gnutls.so.4 | 8.14.1 | 8.14.1-2+deb13u7 | 8.21.0-2~bpo13+1 | same-upstream-release |
| libdatrie.so.1 | 0.2.13 | 0.2.13-3+b1 | unavailable | same-upstream-release |
| libdav1d.so.7 | 1.5.1 | 1.5.1-1 | unavailable | same-upstream-release |
| libdb-5.3.so | 5.3.28 | 5.3.28+dfsg2-9 | unavailable | same-upstream-release |
| libdbus-1.so.3 | 1.16.2 | 1.16.2-2 | unavailable | same-upstream-release |
| libde265.so.0 | 1.0.15 | 1.0.15-1+deb13u2 | unavailable | same-upstream-release |
| libdeflate.so.0 | 1.23 | 1.23-2 | unavailable | same-upstream-release |
| libdrm.so.2 | 2.4.124 | 2.4.124-2 | unavailable | same-upstream-release |
| libdrm_amdgpu.so.1 | 2.4.124 | 2.4.124-2 | unavailable | same-upstream-release |
| libdrm_intel.so.1 | 2.4.124 | 2.4.124-2 | unavailable | same-upstream-release |
| libduktape.so.207 | 2.7.0 | 2.7.0-2+b2 | unavailable | same-upstream-release |
| libedit.so.2 | 3.1-20250104 | 3.1-20250104-1 | unavailable | same-upstream-release |
| libelf.so.1 | 0.192 | 0.192-4 | 0.196-1~bpo13+2 | same-upstream-release |
| libepoxy.so.0 | 1.5.10 | 1.5.10-2 | unavailable | same-upstream-release |
| libexiv2.so.28 | 0.28.5 | 0.28.5+dfsg-1 | unavailable | same-upstream-release |
| libexpat.so.1 | 2.7.1 | 2.9.0-1~deb13u1 | unavailable | Debian-newer-different-major-minor |
| libffi.so.8 | 3.4.8 | 3.4.8-2 | unavailable | same-upstream-release |
| libfontconfig.so.1 | 2.15.0 | 2.15.0-2.3 | unavailable | same-upstream-release |
| libfreetype.so.6 | 2.13.3 | 2.13.3+dfsg-1+deb13u1 | unavailable | same-upstream-release |
| libfribidi.so.0 | 1.0.16 | 1.0.16-1 | unavailable | same-upstream-release |
| libgallium-25.0.7-2.so | 25.0.7 | 25.0.7-2+deb13u1 | 26.1.6-1~bpo13+1 | same-upstream-release |
| libgbm.so.1 | 25.0.7 | 25.0.7-2+deb13u1 | 26.1.6-1~bpo13+1 | same-upstream-release |
| libgcc_s.so.1 | 14.2.0 | 14.2.0-19 | unavailable | same-upstream-release |
| libgck-2.so.2 | 4.4.0.1 | 4.4.0.1-3 | unavailable | same-upstream-release |
| libgcr-4.so.4 | 4.4.0.1 | 4.4.0.1-3 | unavailable | same-upstream-release |
| libgcrypt.so.20 | 1.11.0 | 1.11.0-7+deb13u1 | unavailable | same-upstream-release |
| libgdk-3.so.0 | 3.24.49 | 3.24.49-3 | unavailable | same-upstream-release |
| libgdk_pixbuf-2.0.so.0 | 2.42.12 | 2.42.12+dfsg-4+deb13u1 | unavailable | same-upstream-release |
| libgegl-0.4.so.0 | 0.4.72 | 1:0.4.62-2+deb13u2 | unavailable | Debian-older-same-major-minor |
| libgegl-npd-0.4.so | 0.4.72 | 1:0.4.62-2+deb13u2 | unavailable | Debian-older-same-major-minor |
| libgegl-sc-0.4.so | 0.4.72 | 1:0.4.62-2+deb13u2 | unavailable | Debian-older-same-major-minor |
| libgexiv2.so.2 | 0.14.3 | 0.14.3-1+b1 | unavailable | same-upstream-release |
| libgfortran.so.5 | 14.2.0 | 14.2.0-19 | unavailable | same-upstream-release |
| libgimp-3.0.so.0 | 3.2.6 | 3.0.4-3+deb13u11 | unavailable | Debian-older-different-major-minor |
| libgimpbase-3.0.so.0 | 3.2.6 | 3.0.4-3+deb13u11 | unavailable | Debian-older-different-major-minor |
| libgimpcolor-3.0.so.0 | 3.2.6 | 3.0.4-3+deb13u11 | unavailable | Debian-older-different-major-minor |
| libgimpconfig-3.0.so.0 | 3.2.6 | 3.0.4-3+deb13u11 | unavailable | Debian-older-different-major-minor |
| libgimpmath-3.0.so.0 | 3.2.6 | 3.0.4-3+deb13u11 | unavailable | Debian-older-different-major-minor |
| libgimpmodule-3.0.so.0 | 3.2.6 | 3.0.4-3+deb13u11 | unavailable | Debian-older-different-major-minor |
| libgimpthumb-3.0.so.0 | 3.2.6 | 3.0.4-3+deb13u11 | unavailable | Debian-older-different-major-minor |
| libgimpui-3.0.so.0 | 3.2.6 | 3.0.4-3+deb13u11 | unavailable | Debian-older-different-major-minor |
| libgimpwidgets-3.0.so.0 | 3.2.6 | 3.0.4-3+deb13u11 | unavailable | Debian-older-different-major-minor |
| libgio-2.0.so.0 | 2.84.4 | 2.84.4-3~deb13u5 | unavailable | same-upstream-release |
| libgirepository-1.0.so.1 | 1.84.0 | 1.84.0-1 | unavailable | same-upstream-release |
| libgjs.so.0 | 1.82.3 | 1.82.3-1 | unavailable | same-upstream-release |
| libglib-2.0.so.0 | 2.84.4 | 2.84.4-3~deb13u5 | unavailable | same-upstream-release |
| libgmodule-2.0.so.0 | 2.84.4 | 2.84.4-3~deb13u5 | unavailable | same-upstream-release |
| libgmp.so.10 | 6.3.0 | 2:6.3.0+dfsg-3 | unavailable | same-upstream-release |
| libgnomekbd.so.8 | 3.28.1 | 3.28.1-2 | unavailable | same-upstream-release |
| libgnomekbdui.so.8 | 3.28.1 | 3.28.1-2 | unavailable | same-upstream-release |
| libgnutls.so.30 | 3.8.9 | 3.8.9-3+deb13u4 | unavailable | same-upstream-release |
| libgobject-2.0.so.0 | 2.84.4 | 2.84.4-3~deb13u5 | unavailable | same-upstream-release |
| libgomp.so.1 | 14.2.0 | 14.2.0-19 | unavailable | same-upstream-release |
| libgpg-error.so.0 | 1.51 | 1.51-4 | unavailable | same-upstream-release |
| libgpgme.so.11 | 1.24.2 | 1.24.2-3 | unavailable | same-upstream-release |
| libgpgmepp.so.6 | 1.24.2 | 1.24.2-3 | unavailable | same-upstream-release |
| libgpm.so.2 | 1.20.7 | 1.20.7-11+b2 | unavailable | same-upstream-release |
| libgraphite2.so.3 | 1.3.14 | 1.3.14-2+deb13u1 | unavailable | same-upstream-release |
| libgs.so.10 | 10.05.1 | 10.05.1~dfsg-1+deb13u3 | unavailable | same-upstream-release |
| libgssapi_krb5.so.2 | 1.21.3 | 1.21.3-5+deb13u1 | unavailable | same-upstream-release |
| libgtk-3.so.0 | 3.24.49 | 3.24.49-3 | unavailable | same-upstream-release |
| libgudev-1.0.so.0 | 238 | 238-6 | unavailable | same-upstream-release |
| libgvc.so.6 | 2.42.4 | 2.42.4-3 | unavailable | same-upstream-release |
| libharfbuzz-gobject.so.0 | 10.2.0 | 10.2.0-1+deb13u1 | unavailable | same-upstream-release |
| libharfbuzz.so.0 | 10.2.0 | 10.2.0-1+deb13u1 | unavailable | same-upstream-release |
| libheif.so.1 | 1.19.8 | 1.23.6-2~deb13u1 | unavailable | Debian-newer-different-major-minor |
| libhogweed.so.6 | 3.10.1 | 3.10.1-1 | unavailable | same-upstream-release |
| libhwy.so.1 | 1.2.0 | 1.2.0-2+b2 | unavailable | same-upstream-release |
| libibus-1.0.so.5 | 1.5.32 | 1.5.32-2 | unavailable | same-upstream-release |
| libidn.so.12 | 1.43 | 1.43-1 | unavailable | same-upstream-release |
| libidn2.so.0 | 2.3.8 | 2.3.8-2 | unavailable | same-upstream-release |
| libijs-0.35.so | 0.35 | 0.35-15.2 | unavailable | same-upstream-release |
| libinih.so.1 | 59 | 59-1 | unavailable | same-upstream-release |
| libjbig.so.0 | 2.1 | 2.1-6.1+b2 | unavailable | same-upstream-release |
| libjbig2dec.so.0 | 0.20 | 0.20-1+deb13u1 | unavailable | same-upstream-release |
| libjpeg.so.62 | 2.1.5 | 1:2.1.5-4 | unavailable | same-upstream-release |
| libjson-c.so.5 | 0.18 | 0.18+ds-1 | unavailable | same-upstream-release |
| libjson-glib-1.0.so.0 | 1.10.6 | 1.10.6+ds-2 | unavailable | same-upstream-release |
| libjxl.so.0.11 | 0.11.2 | 0.11.2-0.1~deb13u3 | unavailable | same-upstream-release |
| libjxl_cms.so.0.11 | 0.11.2 | 0.11.2-0.1~deb13u3 | unavailable | same-upstream-release |
| libjxl_threads.so.0.11 | 0.11.2 | 0.11.2-0.1~deb13u3 | unavailable | same-upstream-release |
| libk5crypto.so.3 | 1.21.3 | 1.21.3-5+deb13u1 | unavailable | same-upstream-release |
| libkeyutils.so.1 | 1.6.3 | 1.6.3-6 | unavailable | same-upstream-release |
| libkrb5.so.3 | 1.21.3 | 1.21.3-5+deb13u1 | unavailable | same-upstream-release |
| libkrb5support.so.0 | 1.21.3 | 1.21.3-5+deb13u1 | unavailable | same-upstream-release |
| liblapack.so.3 | 3.12.1 | 3.12.1-6 | unavailable | same-upstream-release |
| liblber.so.2 | 2.6.10 | 2.6.10+dfsg-1 | unavailable | same-upstream-release |
| liblcms2.so.2 | 2.16 | 2.16-2+deb13u2 | unavailable | same-upstream-release |
| libldap.so.2 | 2.6.10 | 2.6.10+dfsg-1 | unavailable | same-upstream-release |
| libltdl.so.7 | 2.5.4 | 2.5.4-4 | unavailable | same-upstream-release |
| liblz4.so.1 | 1.10.0 | 1.10.0-4 | unavailable | same-upstream-release |
| liblzma.so.5 | 5.8.1 | 5.8.1-1+deb13u2 | unavailable | same-upstream-release |
| libmd.so.0 | 1.1.0 | 1.1.0-2+b1 | unavailable | same-upstream-release |
| libmng.so.1 | 1.0.10 | 1.0.10+dfsg-3.1+b6 | unavailable | same-upstream-release |
| libmount.so.1 | 2.41.0 | 2.41.5-0+deb13u1 | unavailable | Debian-newer-same-major-minor |
| libmozjs-128.so.0 | 128.14.0 | 128.14.0-1~deb13u1 | unavailable | same-upstream-release |
| libmypaint-1.5.so.1 | 1.6.0 | 1.6.0-4 | unavailable | same-upstream-release |
| libncurses.so.6 | 6.5+20250216 | 6.5+20250216-2 | unavailable | same-upstream-release |
| libncursesw.so.6 | 6.5+20250216 | 6.5+20250216-2 | unavailable | same-upstream-release |
| libnettle.so.8 | 3.10.1 | 3.10.1-1 | unavailable | same-upstream-release |
| libnghttp2.so.14 | 1.64.0 | 1.64.0-1.1+deb13u1 | unavailable | same-upstream-release |
| libnghttp3.so.9 | 1.8.0 | 1.8.0-1 | 1.15.0-1~bpo13+1 | same-upstream-release |
| libngtcp2.so.16 | 1.11.0 | 1.11.0-1+deb13u1 | 1.22.1-1~bpo13+1 | same-upstream-release |
| libngtcp2_crypto_gnutls.so.8 | 1.11.0 | 1.11.0-1+deb13u1 | 1.22.1-1~bpo13+1 | same-upstream-release |
| libnspr4.so | 4.36 | 2:4.36-1 | unavailable | same-upstream-release |
| libnss3.so | 3.110 | 2:3.110-1+deb13u4 | unavailable | same-upstream-release |
| libnssutil3.so | 3.110 | 2:3.110-1+deb13u4 | unavailable | same-upstream-release |
| libnuma.so.1 | 2.0.19 | 2.0.19-1 | unavailable | same-upstream-release |
| libogg.so.0 | 1.3.5 | 1.3.5-3+b2 | unavailable | same-upstream-release |
| libopenjp2.so.7 | 2.5.3 | 2.5.3-2.1~deb13u2 | unavailable | same-upstream-release |
| libp11-kit.so.0 | 0.25.5 | 0.25.5-3 | unavailable | same-upstream-release |
| libpanelw.so.6 | 6.5+20250216 | 6.5+20250216-2 | unavailable | same-upstream-release |
| libpango-1.0.so.0 | 1.56.3 | 1.56.3-1 | unavailable | same-upstream-release |
| libpangocairo-1.0.so.0 | 1.56.3 | 1.56.3-1 | unavailable | same-upstream-release |
| libpangoft2-1.0.so.0 | 1.56.3 | 1.56.3-1 | unavailable | same-upstream-release |
| libpaper.so.2 | 2.2.5 | 2.2.5-0.3+b2 | unavailable | same-upstream-release |
| libpathplan.so.4 | 2.42.4 | 2.42.4-3 | unavailable | same-upstream-release |
| libpciaccess.so.0 | 0.17 | 0.17-3+b3 | unavailable | same-upstream-release |
| libpcre2-8.so.0 | 10.46 | 10.46-1~deb13u3 | unavailable | same-upstream-release |
| libpixman-1.so.0 | 0.44.0 | 0.44.0-3 | unavailable | same-upstream-release |
| libplc4.so | 4.36 | 2:4.36-1 | unavailable | same-upstream-release |
| libplds4.so | 4.36 | 2:4.36-1 | unavailable | same-upstream-release |
| libpng16.so.16 | 1.6.48 | 1.6.48-1+deb13u6 | unavailable | same-upstream-release |
| libpoppler-glib.so.8 | 25.03.0 | 25.03.0-5+deb13u4 | unavailable | same-upstream-release |
| libpoppler.so.147 | 25.03.0 | 25.03.0-5+deb13u4 | unavailable | same-upstream-release |
| libproxy.so.1 | 0.5.9 | 0.5.9-1 | unavailable | same-upstream-release |
| libpsl.so.5 | 0.21.2 | 0.21.2-1.1+b1 | unavailable | same-upstream-release |
| libpxbackend-1.0.so | 0.5.9 | 0.5.9-1 | unavailable | same-upstream-release |
| libreadline.so.8 | 8.2 | 8.2-6 | unavailable | same-upstream-release |
| librsvg-2.so.2 | 2.60.0 | 2.60.0+dfsg-1+deb13u1 | unavailable | same-upstream-release |
| librtmp.so.1 | 2.4+20151223.gitfa8646d.1 | 2.4+20151223.gitfa8646d.1-2+b5 | unavailable | same-upstream-release |
| libsasl2.so.2 | 2.1.28 | 2.1.28+dfsg1-9 | unavailable | same-upstream-release |
| libsecret-1.so.0 | 0.21.7 | 0.21.7-1 | unavailable | same-upstream-release |
| libselinux.so.1 | 3.8.1 | 3.8.1-1 | unavailable | same-upstream-release |
| libsensors.so.5 | 3.6.2 | 1:3.6.2-2 | unavailable | same-upstream-release |
| libsepol.so.2 | 3.8.1 | 3.8.1-1 | unavailable | same-upstream-release |
| libsharpyuv.so.0 | 1.5.0 | 1.5.0-0.1 | unavailable | same-upstream-release |
| libslang.so.2 | 2.3.3 | 2.3.3-5+b2 | unavailable | same-upstream-release |
| libsmime3.so | 3.110 | 2:3.110-1+deb13u4 | unavailable | same-upstream-release |
| libsqlite3.so.0 | 3.46.1 | 3.46.1-7+deb13u2 | unavailable | same-upstream-release |
| libssh2.so.1 | 1.11.1 | 1.11.1-1+deb13u2 | unavailable | same-upstream-release |
| libssl.so.3 | 3.5.6 | 3.5.7-1~deb13u3 | unavailable | Debian-newer-same-major-minor |
| libstdc++.so.6 | 14.2.0 | 14.2.0-19 | unavailable | same-upstream-release |
| libstemmer.so.0d | 2.2.0 | 2.2.0-4+b2 | unavailable | same-upstream-release |
| libsuitesparseconfig.so.7 | 7.10.1 | 1:7.10.1+dfsg-1 | unavailable | same-upstream-release |
| libsystemd.so.0 | 257 | 257.13-1~deb13u1 | unavailable | different-version-detail |
| libtasn1.so.6 | 4.20.0 | 4.20.0-2+deb13u1 | unavailable | same-upstream-release |
| libtdb.so.1 | 1.4.13+samba4.22.11 | 2:1.4.13+samba4.22.11+dfsg-0+deb13u1 | 2:1.4.15+samba4.24.7+dfsg-1~bpo13+1 | same-upstream-release |
| libthai.so.0 | 0.1.29 | 0.1.29-2+b1 | unavailable | same-upstream-release |
| libtiff.so.6 | 4.7.0 | 4.7.0-3+deb13u3 | unavailable | same-upstream-release |
| libtinfo.so.6 | 6.5+20250216 | 6.5+20250216-2 | unavailable | same-upstream-release |
| libudev.so.1 | 257.13 | 257.13-1~deb13u1 | unavailable | same-upstream-release |
| libumfpack.so.6 | 7.10.1 | 1:7.10.1+dfsg-1 | unavailable | same-upstream-release |
| libunistring.so.5 | 1.3 | 1.3-2 | unavailable | same-upstream-release |
| libunwind.so.8 | 1.8.1 | 1.8.1-0.1 | unavailable | same-upstream-release |
| libuuid.so.1 | 2.41 | 2.41.5-0+deb13u1 | unavailable | different-version-detail |
| libvorbis.so.0 | 1.3.7 | 1.3.7-3 | unavailable | same-upstream-release |
| libvorbisfile.so.3 | 1.3.7 | 1.3.7-3 | unavailable | same-upstream-release |
| libwayland-client.so.0 | 1.23.1 | 1.23.1-3 | unavailable | same-upstream-release |
| libwayland-cursor.so.0 | 1.23.1 | 1.23.1-3 | unavailable | same-upstream-release |
| libwayland-egl.so.1 | 1.23.1 | 1.23.1-3 | unavailable | same-upstream-release |
| libwayland-server.so.0 | 1.23.1 | 1.23.1-3 | unavailable | same-upstream-release |
| libwebp.so.7 | 1.5.0 | 1.5.0-0.1 | unavailable | same-upstream-release |
| libwebpdemux.so.2 | 1.5.0 | 1.5.0-0.1 | unavailable | same-upstream-release |
| libwebpmux.so.3 | 1.5.0 | 1.5.0-0.1 | unavailable | same-upstream-release |
| libwmf-0.2.so.7 | 0.2.13 | 0.2.13-1.1+b3 | unavailable | same-upstream-release |
| libwmflite-0.2.so.7 | 0.2.13 | 0.2.13-1.1+b3 | unavailable | same-upstream-release |
| libx265.so.215 | 4.1 | 4.1-2 | unavailable | same-upstream-release |
| libxapp.so.1 | 2.8.8 | 2.8.8-1 | unavailable | same-upstream-release |
| libxcb-dri3.so.0 | 1.17.0 | 1.17.0-2+b1 | unavailable | same-upstream-release |
| libxcb-glx.so.0 | 1.17.0 | 1.17.0-2+b1 | unavailable | same-upstream-release |
| libxcb-present.so.0 | 1.17.0 | 1.17.0-2+b1 | unavailable | same-upstream-release |
| libxcb-randr.so.0 | 1.17.0 | 1.17.0-2+b1 | unavailable | same-upstream-release |
| libxcb-render.so.0 | 1.17.0 | 1.17.0-2+b1 | unavailable | same-upstream-release |
| libxcb-shm.so.0 | 1.17.0 | 1.17.0-2+b1 | unavailable | same-upstream-release |
| libxcb-sync.so.1 | 1.17.0 | 1.17.0-2+b1 | unavailable | same-upstream-release |
| libxcb-xfixes.so.0 | 1.17.0 | 1.17.0-2+b1 | unavailable | same-upstream-release |
| libxcb.so.1 | 1.17.0 | 1.17.0-2+b1 | unavailable | same-upstream-release |
| libxkbcommon.so.0 | 1.7.0 | 1.7.0-2 | 1.13.1-1~bpo13+1 | same-upstream-release |
| libxkbfile.so.1 | 1.1.0 | 1:1.1.0-1+b4 | unavailable | same-upstream-release |
| libxklavier.so.16 | 5.4 | 5.4-5+b2 | unavailable | same-upstream-release |
| libxml2.so.2 | 2.9.14 | 2.12.7+dfsg+really2.9.14-2.1+deb13u3 | unavailable | same-upstream-release |
| libxmlb.so.2 | 0.3.22 | 0.3.22-1 | unavailable | same-upstream-release |
| libxshmfence.so.1 | 1.3.3 | 1.3.3-1 | unavailable | same-upstream-release |
| libxxhash.so.0 | 0.8.3 | 0.8.3-2 | unavailable | same-upstream-release |
| libyaml-0.so.2 | 0.2.5 | 0.2.5-2 | unavailable | same-upstream-release |
| libz.so.1 | 1.3.1 | 1:1.3.dfsg+really1.3.1-1+b1 | unavailable | same-upstream-release |
| libz3.so.4 | 4.13.3 | 4.13.3-1 | unavailable | same-upstream-release |
| libzstd.so.1 | 1.5.7 | 1.5.7+dfsg-1 | unavailable | same-upstream-release |

## Declared dependency constraints

- `gimp-3.0.pc`: `cairo >= 1.14.0, gdk-pixbuf-2.0 >= 2.32.0, gegl-0.4 >= 0.4.66, gexiv2 < 0.15.0, gexiv2 >= 0.14.0, pango >= 1.50.0`
- `gegl-0.4.pc`: `glib-2.0 >= 2.44.0, gobject-2.0 >= 2.44.0, gmodule-2.0 >= 2.44.0, gio-2.0 >= 2.44.0, gio-unix-2.0 >= 2.44.0, json-glib-1.0 >= 1.0.0, babl-0.1 >= 0.1.116`

