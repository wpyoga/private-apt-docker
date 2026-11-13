# VirtualBox investigation and canceled packaging

Recorded on 2026-11-13 from the repository investigation and its conversation.
This document preserves the findings, corrections, proposed design, completed
fixture checks, and cancellation so the conversation is not needed to resume.
It is a historical record, not an adapter specification awaiting implementation.

## Final decision

Use Oracle's official APT repository for VirtualBox and the Guest Additions
supplied by the original Oracle package. The operator confirmed that Guest
Additions were supplied and explicitly canceled the private packaging work.

There is no VirtualBox adapter, private ISO package, or installation metapackage
in this repository. Do not recreate the canceled packages unless a new,
independently verified requirement establishes that Oracle's package is
insufficient. The Extension Pack was never in scope for implementation.

The original package's exact ISO location and the cause of the initial failure
to find it were not reported in the conversation. Do not treat the initially
suggested path, or its absence on one machine, as proof about all Oracle builds.

## Original request and upstream findings

The investigation began with a request to plan VirtualBox packaging and establish
whether Oracle supplies official binaries. The proposed client baseline was
Debian 13 Trixie on amd64, tracking the stable 7.2 series rather than automatically
following future major/minor series.

Oracle supplies official Debian and Ubuntu binaries, a Linux installer, release
checksums, and an official APT repository. Once the repository was confirmed,
the operator chose to install the main package directly from Oracle instead of
duplicating it in the private repository.

Sources consulted:

- [Oracle download page](https://www.oracle.com/virtualization/technologies/vm/downloads/virtualbox-downloads.html)
- [Oracle release archive](https://download.virtualbox.org/virtualbox/)
- [Trixie repository Release metadata](https://download.virtualbox.org/virtualbox/debian/dists/trixie/Release)
- [Trixie amd64 package index](https://download.virtualbox.org/virtualbox/debian/dists/trixie/contrib/binary-amd64/Packages)

The metadata examined during the conversation advertised
`virtualbox-7.2` version `7.2.22-175245~Debian~trixie`, architecture `amd64`.
This is an observation of the consulted metadata, not a version pin or a promise
about what is current when this record is read. No official Linux arm64 host
artifact was identified in the release directory examined. That does not limit
the guest architectures supported by individual Guest Additions components.

The repository entry discussed was:

```text
deb [arch=amd64 signed-by=/etc/apt/keyrings/oracle-virtualbox.gpg] https://download.virtualbox.org/virtualbox/debian trixie contrib
```

This assumes Oracle's verified signing key has been installed at the named path;
the source line does not install a key. This investigation did not modify client
APT configuration or signing keys.

## Guest Additions troubleshooting and corrections

Guest Additions are drivers and services installed inside a guest OS. The host
can supply their installer as an ISO mounted in the virtual optical drive. They
are distinct from the host-installed Extension Pack and do not appear as a
separate host desktop application.

The conversation initially suggested this host path:

```text
/usr/share/virtualbox/VBoxGuestAdditions.iso
```

The suggested diagnostic was:

```sh
dpkg-query -L virtualbox-7.2 | grep -i 'GuestAdditions.*iso'
```

The operator reported that the path did not exist and the command did not find
an ISO. The assistant then incorrectly concluded that the installed Oracle
package did not bundle it. That conclusion was not established by inspecting
the actual installed package or its complete archive contents. The operator's
later finding that Oracle supplies Guest Additions supersedes that conclusion.

An early local `dpkg-query` check ran in the agent's workspace, not necessarily
on the operator's VirtualBox host, and did not establish the installed host
package contents. Local environment observations must not be silently attributed
to the operator's machine.

Oracle also distributes standalone, versioned ISO downloads. For example, the
consulted [7.2.22 release directory](https://download.virtualbox.org/virtualbox/7.2.22/)
listed `VBoxGuestAdditions_7.2.22.iso`, with its hash in
[SHA256SUMS](https://download.virtualbox.org/virtualbox/7.2.22/SHA256SUMS).
The existence of this separate download does not imply the host package omits it.
Manual downloading was suggested as a troubleshooting workaround, not established
as necessary after the operator's final finding.

For normal use, start the VM and select **Devices → Insert Guest Additions CD
Image**. If selecting an image manually, use the running VM's optical-drive menu
and the actual ISO location on that host. Run the appropriate installer inside
the guest. See [Oracle's Guest Additions instructions](https://docs.oracle.com/en/virtualization/virtualbox/7.2/user/guestadditions.html).
No guest installation was performed or verified during this repository work.

## Licensing and the operator's preference

The operator wanted non-proprietary components and explicitly excluded the
separately licensed Extension Pack. Oracle describes the VirtualBox base platform
as open source under GPLv3; its components can carry their own license notices.
See [Oracle's component description](https://docs.oracle.com/en/virtualization/virtualbox/7.2/user/Introduction.html)
and [upstream COPYING](https://github.com/VirtualBox/virtualbox/blob/main/COPYING).

Debian places its prebuilt `virtualbox-guest-additions-iso` package in `non-free`.
That archive classification must not be equated automatically with the Guest
Additions being proprietary or with the ISO being the Extension Pack.

In [Debian bug 962311, maintainer response 20](https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=962311#20),
the maintainer explains the issue in terms of included platform binaries that
Debian cannot recompile from source, and distinguishes the ISO's overall GPL
status from whether every included component meets the DFSG. The operator
understood the obstacle as needing proprietary build tools, accepted the official
ISO, and did not request a reduced image or a source-built replacement. This
investigation did not audit every component or establish the exact toolchain
requirements of every binary in the image.

The assistant's suggestion that Debian's classification alone justified treating
the complete ISO as proprietary was too broad. Preserve the distinction between
licensing, availability of corresponding source, build prerequisites, and Debian
archive policy when discussing this again.

## Package names, conflicts, and dependency discussion

`virtualbox-guest-additions-iso` is a real Debian package name, not merely a
virtual package. See the [Debian package page](https://packages.debian.org/sid/virtualbox-guest-additions-iso).
Oracle's consulted `virtualbox-7.2` metadata explicitly declared a conflict with
that name, alongside `virtualbox`, `virtualbox-dkms`, `virtualbox-ose`, and
`virtualbox-qt`. Oracle's package itself provided the name `virtualbox`.

Renaming a private ISO package but adding
`Provides: virtualbox-guest-additions-iso` would still expose it to Oracle's
conflict. The draft therefore avoided both the real name and that `Provides`.
See [Debian Policy on virtual packages and conflicts](https://www.debian.org/doc/debian-policy/ch-relationships.html#virtual-packages-provides).
Do not bypass this conflict merely to install Debian's ISO alongside Oracle's
package; first inspect why the upstream package declares it and what files each
package owns.

The operator also asked whether APT configuration could make the unchanged
Oracle package depend on a private ISO package. APT pinning selects versions;
it does not add package dependency declarations. See
[apt_preferences(5)](https://manpages.debian.org/trixie/apt/apt_preferences.5.en.html).

A metapackage was selected as the proposed installation mechanism. Installing
the metapackage would pull both packages; installing `virtualbox-7.2` directly
would not gain a new dependency. This design was canceled along with the ISO
package once the operator confirmed the original package supplies Guest
Additions. No APT hooks, metadata overrides, or client configuration workaround
were implemented.

## Canceled design and implementation

The following describes the deleted draft, not available packages or commands
to install from the current repository.

| Item | Draft choice |
| --- | --- |
| Adapter directory | `packages/repack/virtualbox-guest-additions-7.2/` |
| Release stream | `virtualbox-guest-additions-7.2` |
| ISO package | `virtualbox-guest-additions-iso-7.2` |
| Metapackage | `virtualbox-with-guest-additions` |
| Upstream tracking | Latest stable 7.2 release in Oracle's Trixie amd64 index |
| Outputs | Two `Architecture: all` packages |
| ISO payload | Unchanged official ISO at `/usr/share/virtualbox/VBoxGuestAdditions.iso`, mode `0644` |
| ISO relationships | Suggest Oracle's `virtualbox-7.2`; conflict with Debian's ISO package; no conflicting `Provides` |
| Metapackage relationships | Depend on Oracle's `virtualbox-7.2` and exactly the same private ISO package version |
| Versioning | Upstream `7.2.x` plus the framework's stored-artifact-derived revision |
| Host/ISO coupling | Independent patch updates; no matching-host version requirement |

The draft selected a release from Oracle's index, downloaded that release's
`SHA256SUMS`, selected exactly the expected ISO entry, and verified the ISO hash.
Duplicate or malformed matching metadata and checksum failures were errors;
absence of an eligible series produced no targets. Download verification used
Oracle's HTTPS metadata, not independent verification of an Oracle APT signature.

It used Bash hooks, a small adapter-local Python metadata selector, external
control templates, existing package helpers, declared helper checksum inputs,
and calculated `Installed-Size` from the final staged trees. It preserved license
notices, reused verified workspace downloads, and did not execute ISO contents.
No framework behavior or Dockerfile dependency was changed for this adapter.

The same architecture-independent outputs were selected for requested amd64 and
arm64 cycles and stored once by the framework. This represented ISO data, not
Linux arm64 host support. The metapackage's Oracle dependency still required an
available compatible host package.

## Checks actually completed and evidence retained

The draft regression coordinator completed successfully before cancellation:

```text
bash tests/run.sh virtualbox-guest-additions-7.2
Ran 11 tests in 15.205s
OK
```

The retained logs were inspected when writing this record:

- `build/virtualbox-verification/regression.log`: coordinator result and log path.
- `build/test-run-llrUaE/regression.log`: all 11 test names, individual success
  results, duration, and final result.

These are ignored local build logs, not versioned fixtures or durable test
infrastructure. The test source was removed when the work was canceled. The old
adapter test selector is no longer a supported command in this checkout.

The fixture suite covered:

1. Exact packaged ISO bytes and permissions, license-document presence, absence
   of maintainer scripts, publisher fields, dependencies/conflicts, and
   `Installed-Size` in packages and published indexes.
2. amd64-only, arm64-only, and combined requested architectures, with one stored
   architecture-independent output set.
3. Repeat-update reuse, recipe revision changes, and preservation of old bytes.
4. Selecting the newest stable 7.2 release without following another series.
5. An absent series producing no packages.
6. Invalid architecture/version fields and duplicate host release records.
7. Missing, malformed, duplicate, or extra-field matching checksum entries.
8. A corrupt downloaded ISO storing no packages.
9. A build request inconsistent with the selected ISO version.
10. Reusing a verified download across architecture builds.
11. An isolated APT simulation with an already-installed, older-patch host
    fixture carrying Oracle's conflicts, installing the bundle without removing
    or upgrading that host fixture.

The ISO tests used artificial bytes, not a real upstream image. The APT test
used fixture host metadata, not a completed installation of Oracle's real
package or a clean-host installation with all its dependencies resolved.

A separate command was prepared to download live metadata, build from the real
ISO, verify the host `.deb` hash, and inspect its file list. That tool request
was interrupted. No completed live-verification log, live ISO, or live host
archive was found under `build/virtualbox-verification/` when documenting the
history. Do not claim this step, automatic ISO discovery, or runtime guest
installation passed. No signing test, container deployment, or production
publication was completed as part of the canceled work.

## Cancellation, cleanup, and future work

On learning that Guest Additions were supplied by Oracle's original package,
the operator canceled the feature. Cleanup removed:

- The complete draft adapter directory listed above.
- `tests/virtualbox-guest-additions-7.2/` and its fixture tests.
- The draft `docs/virtualbox-guest-additions.md` installation guide.
- Only the VirtualBox sections added to `README.md` and `ARCHITECTURE.md`.

Unrelated framework/build-dependency work and the pre-existing `temp/` directory
were preserved. Production repository packages and signing keys were not used
for tests, modified, migrated, or deleted. Cleanup passed `git diff --check`
and a search confirmed the canceled feature references were gone from maintained
code/docs before this historical record was added.

There is no pending implementation task. If another missing-ISO report occurs,
inspect the actual host's installed package, complete file list, archive
contents, version, and VirtualBox image-selection behavior before proposing
another private package. Record the real location and failure cause rather than
assuming the first suggested filesystem path applies to that installation.
