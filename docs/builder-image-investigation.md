# Prebuilt Debian and GUI builder image investigation

Recorded on 2026-11-13 from the builder-image discussion and the repository's
current build configuration. This document preserves the questions, findings,
maintainer preference, and unfinished validation so the discussion can be deleted.
Upstream image tags and Dockerfiles can change; these are investigation findings,
not a guarantee about the contents of a future pull.

## Request and decision status

The initial question was whether an existing Debian builder image could avoid
installing build tools and development libraries ourselves. The follow-up asked
specifically for an image that also contains GUI development libraries.

The maintainer explicitly rejected building and publishing our own builder image.
Do not revive a custom registry image as an agreed solution. That approach was
suggested during the discussion and declined.

Two relevant candidates were identified:

| Image | What it provides | Fit for this repository |
| --- | --- | --- |
| `buildpack-deps:trixie` | Debian Trixie, common compilers, build tools, and development libraries | Matches the Debian release, but lacks the complete GTK/Xfce packaging and cross-build environment |
| `xfce/xfce-build` | Xfce's development environment, including extensive GUI headers and tools | Relevant to GUI compilation, but the inspected recipe uses Ubuntu 26.04 and builds Xfce libraries from source |

No replacement image was selected or integrated. The investigation did not find
a verified prebuilt Debian Trixie image containing the complete dependency set
for our GTK/Xfce builds and the required arm64 cross-build environment. This is
a limit of the search, not proof that no such image exists.

The request to avoid publishing our own builder image did not itself authorize
removing the existing local Docker build setup. No Dockerfile, adapter, Compose
service, dependency declaration, or deployment was changed in this investigation.

## Candidate: buildpack-deps:trixie

This is a Docker Official Image intended as a general build base. The full
`trixie` variant layers development packages on top of `trixie-scm`, which adds
source-control tools on top of `trixie-curl`.

The inspected full recipe includes GCC, G++, Make, Autoconf, Automake, libtool,
patch, dpkg-dev, and common development headers such as GLib, OpenSSL, curl,
PNG, JPEG, XML, SQLite, and compression libraries. Git comes from its SCM layer.
The published image metadata reviewed during the discussion listed both amd64
and arm64 variants.

The illustrative base-image change discussed was:

```dockerfile
FROM buildpack-deps:trixie
```

This example was not applied. It would reduce some explicit installations, but
would still require the missing application and Debian packaging dependencies.
The inspected recipe does not declare GTK 3, VTE, the Xfce development libraries,
debhelper, devscripts, quilt, or the arm64 cross-build toolchain our scripts use.
Installing libraries for the image's native architecture also does not establish
that arm64 development libraries are available inside an amd64 container.

Using the smaller `-curl` or `-scm` variants would not supply the full compiler
and development-library set of the unsuffixed image.

Sources:

- [Docker Official Image description](https://hub.docker.com/_/buildpack-deps).
- [Trixie development-package recipe](https://github.com/docker-library/buildpack-deps/blob/master/debian/trixie/Dockerfile).
- [Trixie SCM recipe](https://github.com/docker-library/buildpack-deps/blob/master/debian/trixie/scm/Dockerfile).
- [Published tags and architectures](https://github.com/docker-library/official-images/blob/master/library/buildpack-deps).

## Candidate: xfce/xfce-build

Xfce publishes this image for building its own components. Xfce's developer-tools
documentation identifies it as a reusable development environment and historically
shows the `master` tag in its example. The Docker Hub listing also exposes image
tags. A tag must be checked before use; no particular tag or digest was validated
for this repository.

The inspected upstream Dockerfile begins with `FROM ubuntu:26.04`. It installs
GTK 3 and GTK 4 development packages, GLib, VTE, X11 and Wayland headers, and many
desktop integration dependencies. Examples include PAM, systemd, D-Bus, libwnck,
libutempter, and libxklavier headers. It also installs compilers and build tools,
including CMake and Meson, and runs `ci/build_libs.sh` to build Xfce core libraries.

This answers the general GUI-image question: an existing image with extensive GUI
development libraries does exist, maintained by the relevant desktop project.

It does not establish suitability for our Trixie Debian packages. Our assessment
is that directly building against an Ubuntu 26.04 environment and its additional
Xfce libraries could introduce library, symbol, or package-version requirements
that Trixie cannot satisfy. This is a compatibility concern inferred from the
recipe, not an observed failure from a test build. The image could be useful for
upstream compilation or testing in its own environment, but a successful build
there would not validate installation on Trixie.

Architecture manifests, arm64 cross-compilation support, installed Debian
packaging tools, and the complete dependency closure were not verified. Building
Xfce core libraries inside the image also differs from our current approach of
using Debian development packages for the Xfce adapters.

Sources:

- [Xfce image listing](https://hub.docker.com/r/xfce/xfce-build).
- [Upstream Dockerfile mirror](https://github.com/xfce-mirror/xfce4-dev-tools/blob/master/Dockerfile).
- [Upstream Dockerfile on Xfce GitLab](https://gitlab.xfce.org/xfce/xfce4-dev-tools/-/blob/master/Dockerfile).
- [Xfce developer-tools README in Debian source 4.20.0-2](https://sources.debian.org/src/xfce4-dev-tools/4.20.0-2/README.md).

The GitHub mirror was readable during the investigation. Some raw-file and GitLab
requests failed through the browsing tool. The Debian source README was available
through search results during the original discussion; its direct fetch failed
when this handoff was written. These access limits are not evidence that the
upstream image or documentation was removed.

## Repository requirements and existing caching

The authoritative dependency lists remain in the adapters. Relevant files are:

- [Root Dockerfile](../Dockerfile).
- [Terminal build dependencies](../packages/rebuild/xfce4-terminal/install-build-dependencies).
- [Screensaver build dependencies](../packages/rebuild/xfce4-screensaver/install-build-dependencies).
- [libgit2 build dependencies](../packages/rebuild/libgit2-1.9/install-build-dependencies).
- [Terminal build and deployment notes](xfce4-terminal.md).
- [Screensaver notes](xfce4-screensaver.md).
- [Private build dependencies and isolated workers](build-dependencies.md).

At handoff time, the root Dockerfile starts from `debian:trixie-slim`. Its `tools`
stage installs publisher utilities. `publisher-files` copies framework and adapter
files. Separately, `rebuild-tools` copies and runs the terminal, screensaver, and
libgit2 dependency installers before the final `rebuild` stage copies publisher
files. The default final target remains `publisher` for ordinary repack builds.

The Xfce builds currently use an amd64 host, with native amd64 compilation and
an arm64 cross compiler plus target development packages. The terminal installer
supplies shared tools such as build-essential, crossbuild-essential-arm64,
debhelper, devscripts, quilt, gtk-doc-tools, intltool, and xfce4-dev-tools. It also
installs target GLib, GTK 3, PCRE2, startup-notification, utempter, VTE, and Xfce UI
development libraries.

The screensaver installer relies on those shared tools and adds gettext and
target development packages for D-Bus GLib, Garcon GTK 3, PAM, systemd, libwnck,
X11, Xfce UI/utilities, xfconf, xklavier, and XScreenSaver. These application
requirements explain why a generic compiler image is insufficient.

The two target environments are separate because their architecture-specific
Xfce dependency sets pull in conflicting xfconf packages. A multi-architecture
image tag alone does not replace this target-environment handling. The current
Dockerfile also installs libgit2 dependencies; a future replacement assessment
must include those rather than considering only the original GUI question.

The existing Docker layers already avoid reinstalling dependencies for ordinary
adapter edits while the dependency inputs and earlier layers remain reusable.
Changing an installer invalidates its layer and subsequent layers. Refreshing
base images or disabling the cache can also cause installation to run again.
This local caching is separate from the rejected proposal to publish our own
prebuilt image to a registry.

Private dependency workers derive temporary local images from the rebuild image
to install exact selected private packages. That existing feature is documented
separately; it was not introduced, removed, or redesigned by this discussion.

## Validation boundaries and future evaluation

The work consisted of reading repository configuration and inspecting upstream
documentation, Dockerfiles, and published metadata. Neither candidate was pulled,
executed, benchmarked, used to build a package, or tested for clean Trixie
installation. No image-size or speed improvement was measured. No production
repository, signing key, package, or service was touched.

If the search resumes, compare an actual published tag and digest against the
adapter dependency declarations. Check the base distribution, installed package
versions, native and target architectures, Debian packaging tools, and any
libraries installed outside APT. Then build the affected packages and validate
their dependency metadata and clean installation on Trixie before adopting the
image. Follow the repository's host UID/GID and image-layer installation rules.

Do not change the root Dockerfile merely to record this research: its text is a
recipe-checksum input for repack/rebuild streams and can trigger package revisions.
This document belongs outside `packages/` for the same reason. The existing
architecture and hook contract remain authoritative.
