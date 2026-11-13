# GIMP AppImage build base and library-version comparison

Recorded on 2026-11-13 from the conversation about the official GIMP AppImage's
base distribution, build instructions, and differences from an updated Debian
13 installation. This note preserves the answers, their corrections, source
locations, and evidence limits so the conversation can be deleted.

The concrete release checked was **GIMP 3.2.6**, source tag `GIMP_3_2_6`.
Do not extend its findings automatically to another release or to unofficial
GIMP AppImages. This documentation update did not build or execute GIMP.

## Confirmed build base and CI inheritance

The release's [CI configuration](https://github.com/GNOME/gimp/blob/GIMP_3_2_6/.gitlab-ci.yml)
establishes this chain:

| Location in that file | Finding |
| --- | --- |
| `.default`, lines 102–107 | Default image name uses `DEB_VERSION`; its default is `bookworm`. |
| `.debian`, lines 340–358 | AppImage jobs override `DEB_VERSION` to `trixie`, with runners `aarch64` and `x86_64_v3`. |
| `deps-debian`, lines 359–370 | Reuses the dependency script that generates `FROM debian:${DEB_VERSION}` at line 175: therefore `debian:trixie`. |
| Dependency script, lines 265–277 | Builds babl and GEGL from upstream source into a private prefix. |
| `gimp-debian`, lines 371–395 | Builds relocatable GIMP and invokes the packaging script with `--bundle-only`. |
| `dist-appimage-weekly`, lines 1016–1028 | Consumes `gimp-debian` artifacts and invokes the packaging script again. It extends `.default`, whose default is Bookworm. |

Thus **Debian 13 Trixie is the dependency/application build base**. Saying every
AppImage pipeline stage runs on Trixie would be too broad. The dependency job's
`quay.io/containers/aio:latest` image runs Buildah; it is not the generated
application build image.

These are recipe facts, not a captured release-job execution record. The checked
configuration does not establish the exact base-image digest, point release,
installed package revisions, or dependency commits of a particular download.

## Where the build instructions live

The official [Linux build guide](https://developer.gimp.org/core/setup/build/linux/)
documents dependency/environment setup and directs readers to `.gitlab-ci.yml`
for the Debian CI environment used to make AppImages. Its dependency list and
general source-build instructions are useful starting points. The checked guide
does not provide a dedicated, complete local AppImage tutorial.

Use the release-tagged CI recipe above for job order and inputs. Its packaging
entry point is
[`build/linux/appimage/3_dist-gimp-goappimage.sh`](https://github.com/GNOME/gimp/blob/GIMP_3_2_6/build/linux/appimage/3_dist-gimp-goappimage.sh).
The CI references establish the filename and invocations. The web reader could
not retrieve the script body during this conversation or this documentation
pass; no detailed account of its internal behavior was verified here. In
particular, the previously guessed name `3_dist-gimp-appimage.sh` was not the
entry point found in CI.

For a future reproduction, inspect those files in the chosen release tag and
resolve their environment, tool and artifact requirements before running them.
Do not treat the packaging command alone as a complete build recipe. Read its
body before assuming how the final distribution job uses the earlier AppDir.
The earlier chat linked `master`; release-specific work should use the tag to
avoid silently following later dependency or packaging changes.

## Why library versions can differ

The user's comparison system was described as Debian 13, fully updated, with
backports enabled. That statement was accepted as context; this conversation
did not inspect the host's sources, APT preferences, installed versions or holds.

The agreed conclusion is conditional: **a library obtained from the same Trixie
repositories at AppImage build time should normally be the same version as, or
older than, its counterpart on a subsequently fully updated installation**.
This is an expectation to check against actual package provenance, not proof
that every bundled library came from Trixie or has the same build configuration.

Different cases need different explanations:

- A library built separately from upstream source can be newer than Debian's
  version. babl and GEGL are the explicitly identified examples. An unspecified
  claim that some other library needed a newer version is not evidence that it
  was actually built or bundled that way.
- An older build environment can explain older bundled dependencies. Merely
  saying the container and host were updated at different times does not explain
  a newer bundled library on an otherwise current system using the same sources.
- A distribution release name does not identify an exact package snapshot.
  Reproducing an artifact requires more provenance than its distro name.
- Upstream release numbers, Debian package revisions and ABI/SONAME numbers
  answer different questions. A changed Debian revision may include patches
  without changing the upstream release number. A matching SONAME alone does
  not prove identical versions or runtime behavior.

Backports needs a separate qualification. Adding `trixie-backports` does not
automatically upgrade every installed package to a backported version. Under
the normal policy, backports have priority 100 and packages are selected
explicitly. Debian also tries to reuse stable libraries where possible; enabling
backports is not a promise that a newer build of every library exists. See the
[official instructions](https://backports.debian.org/Instructions/#installing-a-package-from-backports).
Custom APT preferences can change selection; none were inspected here.

## Corrections to the conversation's earlier answers

1. The initial answer combined the build distro with the download page's stated
   supported-system baseline. A runtime support statement alone does not prove
   the build image. The release-tagged CI inheritance supplies the evidence for
   the Trixie dependency/application build base.
2. The statement that the general CI default was Trixie was too broad for this
   release. Its default is Bookworm; the AppImage build jobs override it. The
   final distribution job also needs to be distinguished from compilation.
3. The earlier suggestion that update timing explains any differing library
   version was incomplete. For the same repository sources, an old snapshot
   normally explains older copies, not unexpectedly newer ones.
4. The backports clarification was about default APT behavior. It did not
   establish that the user had failed to install a particular backport.

No particular unexpected external library/version pair was supplied in this
chat, so there is no completed diagnosis of such a discrepancy here.

## Relationship to this repository's GIMP repack

The official AppImage and this repository's native packages have different
runtime layouts. The maintained adapter selects GIMP-owned payloads and retains
private babl/GEGL libraries, modules and typelibs. Other external libraries are
provided through explicit Debian dependencies. Its build does not inspect the
host's installed packages to decide compatibility.

See [GIMP packaging notes](gimp-3.2.md) for the current package split, dependency
map and validation limits. The
[historical investigation](gimp-3.2-investigation-history.md#final-experimental-runtime-selection)
already preserves the detailed static inventory, methods, replacement reviews,
and historical runtime checks; duplicating that inventory here would create two
competing records.

That record reports private babl 0.1.128 and GEGL 0.4.72, compared with saved
Trixie versions 0.1.114 and 0.4.62, and no matching babl/GEGL backports in the
indexes checked then. These are historical findings, not a fresh archive query.
It also records TIFF 4.7.0 on both sides, so the deferred TIFF-thumbnail issue
cannot be explained solely by different upstream TIFF release numbers.

## How to investigate a concrete difference later

Preserve the AppImage filename, architecture and SHA256, the matching GIMP tag,
the exact library path, and the method used to identify its version. Distinguish
an untouched AppImage from an extracted tree and from the native repack.

On the comparison system, collect the relevant package's installed version and
APT candidate/origin information. These read-only examples require replacing
`PACKAGE` with the actual Debian binary package name:

```bash
dpkg-query -W -f='${binary:Package}\t${Version}\n' PACKAGE
apt-cache policy PACKAGE
```

These commands describe locally cached APT metadata; they do not refresh it.
Compare the upstream component release and the complete Debian package revision
separately. If a bundled external library appears newer, trace its build ID,
package/source provenance and release CI before attributing the difference to
Trixie, backports, or an upstream version requirement. Recover the actual build
logs/image digest where available. Static strings or filenames alone may not
identify a release reliably; the historical inventory documents such cases.

Before raising a native dependency minimum, identify the required feature or
bug fix and check Debian's patches. A newer bundled version is not automatically
the oldest version that works. Matching versions or exported symbols are also
insufficient to prove semantic compatibility; meaningful runtime checks remain
necessary for a packaging change.

## Documentation verification

This pass rechecked the tagged CI configuration, official Linux guide and Debian
Backports instructions through the web reader, and reviewed the current adapter,
tests and existing GIMP notes. The packaging script body remained unavailable
through that reader. Local documentation links and whitespace were checked.
No package builds, signing tests, deployment, host package installation or new
library comparison were performed. Existing staged work was preserved.
