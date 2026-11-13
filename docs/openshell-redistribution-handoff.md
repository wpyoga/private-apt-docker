# OpenShell and unchanged-package redistribution handoff

Recorded on 2026-11-13 so the implementation conversation can be deleted.
This document preserves its decisions, implementation details, observed results,
limitations and next steps. It describes the investigation of OpenShell v0.1.8
on 2026-11-11; it does not claim that version remains the latest release.

Read [OpenShell usage notes](openshell.md), the
[operator contract](../README.md#unchanged-package-redistribution), and the
[architecture](../ARCHITECTURE.md#redistribution-provenance) for maintained behavior.
The separate [build and commit-splitting handoff](build-and-redistribution-handoff.md)
records another conversation about organizing the same changes into commits.
Its statements about not running tests apply to that conversation, not to the
implementation work recorded here.

## Maintainer intent and final decisions

The initial request was to investigate NVIDIA OpenShell, explain its daemon and
architecture, and decide how to package it. Investigation established that upstream
already publishes Debian packages. The maintainer then chose to host those
packages unchanged rather than maintain a new package split.

| Question | Final decision |
| --- | --- |
| Compile OpenShell from source? | No; use the official release `.deb` assets. |
| Split the CLI, gateway, prover and VM driver? | No; retain upstream's single `openshell` package. |
| Rewrite Debian control metadata? | No; preserve the complete upstream archive bytes. |
| Allocate publisher revisions? | No; retain upstream's full Debian version, including its revision. |
| Add provenance fields inside the package? | No; keep import records externally and expose provenance in the signed index. |
| Category name? | `redistribute`, alongside `repack` and `rebuild`. |
| Repository membership? | Adapter parent directory, with a separate output and signing identity. |
| Missing Installed-Size? | Calculate an index-only estimate without rebuilding the archive. |

The earlier proposal for four binary packages was superseded. It must not be
treated as an outstanding implementation requirement.

The maintainer explicitly objected to excessive verification for this task and
asked to stop the broader test work. Keep future verification proportional and
focused on an actual change or known failure. This documentation update does not
authorize resuming tests, deployment, or unrelated improvements.

## Upstream findings and sources

Upstream distributes Debian archives as GitHub Release assets, under the Assets
list at the bottom of each release page. They are not prominently listed in the
repository README. The installer downloads a release checksum list, selects an
architecture-specific archive and installs the downloaded file.

At investigation time, no upstream-maintained OpenShell APT repository was found
in the official installation documentation or installer. That is a dated finding,
not proof that upstream can never introduce one. A local-file installation by
itself does not establish an APT source for later upstream releases.

Primary sources inspected:

- [OpenShell v0.1.8 release](https://github.com/NVIDIA/OpenShell/releases/tag/v0.1.8).
- [Tagged installer](https://github.com/NVIDIA/OpenShell/blob/v0.1.8/install.sh).
- [Debian packaging script](https://github.com/NVIDIA/OpenShell/blob/v0.1.8/tasks/scripts/package-deb.sh).
- [Debian control template](https://github.com/NVIDIA/OpenShell/blob/v0.1.8/deploy/deb/control.in).
- [Gateway user service](https://github.com/NVIDIA/OpenShell/blob/v0.1.8/deploy/deb/openshell-gateway.service).
- [Debian post-install script](https://github.com/NVIDIA/OpenShell/blob/v0.1.8/deploy/deb/postinst.sh).
- [Tagged architecture](https://github.com/NVIDIA/OpenShell/blob/v0.1.8/docs/about/architecture.mdx).
- [Tagged installation documentation](https://github.com/NVIDIA/OpenShell/blob/v0.1.8/docs/about/installation.mdx).

GitHub's rendered release asset list failed intermittently in the browsing tool.
The GitHub release API subsequently supplied the exact filenames and digests,
and both archives were downloaded and checked. The adapter uses that API's asset
digests rather than parsing the installer's separate checksum text file.

## Architecture and package contents

The gateway is the control-plane daemon. It manages sandbox lifecycle,
authentication, policy, credentials and interactive connections. The CLI and SDKs
talk to the gateway. A compute driver provisions the workload, supervisor and
isolation boundary using Docker, Podman, MicroVMs or Kubernetes.

The trusted supervisor mediates requests, checks policy and supplies credentials
to approved upstream requests. The sandbox runs with the agent on the untrusted
side of that boundary and reports operations to the supervisor. Linux enforcement
includes Landlock and seccomp. Early descriptions involving a Docker/k3s gateway
should not be assumed to describe this investigated release.

The downloaded Debian package contains these fixed paths:

| Path | Purpose |
| --- | --- |
| `/usr/bin/openshell` | CLI and terminal interface |
| `/usr/bin/openshell-gateway` | Gateway daemon |
| `/usr/bin/openshell-prover` | Standalone policy verification |
| `/usr/libexec/openshell/openshell-driver-vm` | VM compute driver helper |
| `/usr/lib/systemd/user/openshell-gateway.service` | Per-user systemd service |
| `/usr/share/doc/openshell/copyright` | License |
| `/usr/share/doc/openshell/changelog.gz` | Upstream changelog |

The importer requires the first six paths, verifies regular files at those paths,
and checks that the four executables have an executable mode and little-endian
64-bit ELF headers for the selected machine. It rejects absolute/traversing tar
paths. These are fixed-layout checks, not an exhaustive security audit, ELF
dependency audit or runtime compatibility test.

Upstream's user service performs configuration preflight and certificate
generation before starting the gateway. The Debian post-install script does not
enable the service for an arbitrary account; the installer separately starts it
for its target user. Redistribution preserves these upstream scripts and service
bytes. They are not executed during import, but can run on client installation.

The documented local endpoint is `https://127.0.0.1:17670`. Configuration is under
`~/.config/openshell/`, including `gateway.toml` and optional `gateway.env`.
The investigated runtime requirements include Docker Engine 28+, Podman 5.x with
cgroups v2 and a user socket, or KVM for Linux MicroVMs. Runtime images remain
managed by OpenShell and the runtime; they are not distributed as host packages
by this adapter. Gateway, runtime and agent execution were not tested here.

## Implementation map and data flow

The implementation is now committed: `ae1aa67` contains redistribution framework
support, and `d94ffe1` contains OpenShell. Related documentation also landed in
`ea4aad2`; contributor policy exceptions landed in `0ead9fc`. At the start of this
documentation update HEAD was `268ad5d`. Do not recreate or rewrite those commits.

| File or component | Responsibility |
| --- | --- |
| `packages/redistribute/openshell/config` | Declare stream `openshell` and output package `openshell` |
| Adapter `query` | Select the latest stable release and exact requested-architecture Debian assets |
| Adapter `build` | Verify the download, package identity and fixed layout; copy original bytes to output |
| Adapter `validate.py` | Inspect the tar payload and ELF headers without extracting or executing upstream code |
| Adapter `helper-inputs` | Declare shared GitHub/download helpers for recipe fingerprinting |
| `lib/redistribute.py` | Validate manifests, resolve imports, store original archives/provenance and enrich indexes |
| `lib/resolve-builds.py` | Dispatch redistribution resolution before ordinary revision allocation; read external provenance for stored imports |
| `lib/store-packages.sh` | Dispatch redistribution storage instead of requiring embedded publisher fields |
| `lib/publish.sh` | Enrich Packages entries before compression and signing |
| `lib/repository.sh` | Validate the optional repository mode |
| Compose, setup and `.env.example` | Configure the third output, keyring, signing fingerprint and service |
| `tests/run.py`, runner/setup tests | Discover the third category and account for the third signing identity |
| `tests/openshell/test_openshell.py` | Offline importer regression fixtures |

The explicit coordinator setting is `REPOSITORY_MODE=redistribute`. The existing
repack/rebuild paths retain their normal embedded metadata and revision behavior.
Compose sets both the mode and `PACKAGES_DIR` for the new service; merely putting
an adapter in a directory does not set the mode in a manually launched coordinator.

Query writes normal `targets.tsv` rows using full upstream Debian versions, plus
`WORKSPACE/imports.json`. Each import record declares `package`, `version`,
`architecture`, HTTPS `url` and lowercase hexadecimal `sha256`. The OpenShell
selector accepts numeric upstream Debian revisions instead of assuming `-1`.
Absent architecture assets produce no target for that architecture; duplicate
matching assets, malformed tags and missing/invalid digests fail explicitly.

Resolution checks the declared digest against an existing package and its import
record. Matching bytes, recipe checksum and URL permit reuse. A changed recipe,
changed URL or missing record causes current-target validation again, without
changing the package version. Changed bytes at an already stored identity fail.

Storage validates the complete declared output set before publishing files. It
checks control identity and artifact digest, and rejects conflicting bytes for
the same Package/Version/Architecture elsewhere in the repository. Packages go
under `pool/main/STREAM/`; provenance records go under:

```text
REPO_DIR/.state/imports/STREAM/PACKAGE_VERSION_ARCH.deb.json
```

Records contain the manifest fields plus `stream`, `recipe_sha256` and
`installed_size`. A record is atomically written before its package is published
using the existing complete-file/hard-link approach. A crash can leave an orphan
record; retry is safe under the repository lock. Storage is atomic per artifact,
not across the entire set. Existing package bytes are not overwritten.

Publication verifies recorded artifact digests and enriches each entry by its
Filename, preserving distinctions between versions and architectures. It adds:

- `X-Publisher-Stream`.
- `X-Import-Recipe-SHA256`.
- `X-Upstream-URL`.
- Calculated `Installed-Size`.

The package's own Maintainer and Version are unchanged. The import recipe hash
is not the upstream artifact digest; the normal index SHA256 identifies the
archive bytes. Index-only fields do not appear in `dpkg-deb --field` output and
do not automatically become installed dpkg metadata.

Installed-Size is the sum of regular-file payload lengths, rounded up to KiB.
This is a logical-size estimate; it excludes directory/block allocation overhead
and does not use the repack staging-tree `du` method. It replaces missing or stale
upstream values in the index only. The original OpenShell 0.1.8-1 control archive
has no Installed-Size.

Back up `.state/imports` with stored packages. Current-target records can be
recovered through revalidation. Historical missing records require operator
recovery; redistribution publication fails rather than silently omitting their
provenance. There is no automatic migration, retirement, cleanup or notification.

## Verification actually observed

Both official 0.1.8-1 archives were imported through the new hooks, checked and
indexed in isolated ignored build storage. The observed upstream SHA256 values:

| Architecture | Filename | SHA256 |
| --- | --- | --- |
| amd64 | `openshell_0.1.8-1_amd64.deb` | `b3339527085d9b44afc0d5e4f835c2d34e44e33d0b67d6a4cac9d96f25a656b1` |
| arm64 | `openshell_0.1.8-1_arm64.deb` | `3d53db93dc2f130ae570a838c2dd48fda626bd1ab964ea1de895e13a21a667a9` |

The generated two-entry Packages file retained those SHA256 values and upstream
metadata and contained the added provenance fields. Calculated Installed-Size
was 218073 KiB for amd64 and 198381 KiB for arm64. This manual path verified
download, static payload validation, storage and index enrichment; it did not
perform production publication or exercise gateway execution.

Changed shell scripts passed `bash -n` in the live verification batch. A
`git diff --check` also passed during implementation.

### Important correction: the regression suite did finish, with one failure

The chat's final implementation summary said the full suite was not completed
after the maintainer requested stopping tests. The retained logs provide a more
precise result: the offline runner completed **254 tests in 462.551 seconds, with
one failure**. Therefore the suite must not be reported as passing or merely
unverified. The log contains no errors or other failures; the other 253 cases,
including the other 11 OpenShell cases, report success.

The failure is:

```text
test_missing_architecture_is_added_later_without_rewriting_existing
tests/openshell/test_openshell.py:97
Upstream changed bytes for openshell_0.1.8-1_amd64.deb; stored package preserved
```

The fixture builds an amd64 archive, stores it, then calls `fixture()` again to
add arm64. That second call rebuilds amd64 too. The likely cause is changing tar
timestamps or other build-time bytes in the regenerated fixture: identical
logical files do not guarantee byte-identical Debian archives. This is an
inference from the fixture and failure, not a reproduced diagnosis. The stored
bytes were preserved, consistent with the intended collision rule.

If the maintainer requests a fix, preserve/reuse the first amd64 fixture archive
when adding arm64, or make fixture creation reproducible. Do not weaken the
production digest check merely to make this test pass. Fixing or rerunning this
test was not part of the documentation request.

The signing test was requested but its tool invocation was aborted by the user;
there is no successful signing-test result from this conversation. Production
setup, Docker image builds, Compose deployment, client APT installation, gateway
startup, sandbox creation and native arm64 execution were not performed.

### Local evidence and retention

These paths existed when this handoff was written. They are ignored local data,
not version-controlled evidence, so they may disappear after a checkout/machine
change. The hashes and results above are preserved here for that reason.

| Path | Evidence |
| --- | --- |
| `build/openshell-inspection/release.json` | Release API response used for selection |
| `build/openshell-inspection/imports.json` | Selected upstream import declarations |
| `build/openshell-inspection/openshell_0.1.8-1_ARCH.deb` | Verified original downloads |
| `build/openshell-inspection/control.log`, `contents.log` | amd64 control metadata and payload listing |
| `build/openshell-inspection/validation.log` | Successful standalone amd64 static validation; empty output |
| `build/openshell-inspection/live-query.log` | Live query; empty successful output |
| `build/openshell-inspection/live-build-ARCH.log` | Successful digest checks and adapter execution |
| `build/openshell-inspection/live-store-ARCH.log` | Successful isolated storage; empty output |
| `build/openshell-inspection/repo/` | Isolated imported packages and provenance |
| `build/openshell-inspection/Packages`, `live-index.log` | Two enriched package entries and scan result |
| `build/openshell-inspection/syntax.log` | Successful shell syntax checks; empty output |
| `build/openshell-inspection/offline-run.log` | Coordinator reports test log and failure exit status |
| `build/test-run-UwQaDe/regression.log` | Completed 254-test run, failure traceback and summary |

Keep useful original downloads and failure logs. Temporary outputs or duplicate
inspection copies can be removed when no issue needs them, subject to repository
instructions. Never interpret this as permission to remove served packages, keys
or production provenance. No temporary cleanup was performed for this handoff.

## Deployment handoff

Nothing was deployed during the implementation conversation. Do not assume
operator `.env` changes or new production keys exist merely because the example
settings and Compose service are committed.

Add these settings to the existing operator-owned `.env`, using the intended
host paths and leaving its existing keys/settings intact:

```dotenv
REDISTRIBUTE_REPO_DIR=/srv/apt/redistribute
REDISTRIBUTE_GNUPG_DIR=/var/lib/apt-publisher/gnupg/redistribute
REDISTRIBUTE_GPG_KEY=
```

Setup prepares a separate keyring and output, generates or selects an independent
key, writes the fingerprint, and exports `redistribute-pubkey.asc`. Public output
and private keyrings must stay separate. Follow the README to run setup and
Compose; those are operator actions, not instructions automatically executed
when an agent reads this document.

The additional `redistribute` service uses the ordinary publisher image. Together
with `codex-repo-updater`, `rebuild-amd64` and `rebuild-arm64`, this means four
services and three repository outputs. Older README prose still describing
three services/two repositories predates this addition; the unchanged-package
redistribution section and actual Compose configuration describe the new setup.

Serve the third output at `/redistribute/`, distribute its public key securely
and add a client source using that key. Then `apt install openshell` installs
the original upstream package. The intended user explicitly starts the gateway:

```bash
systemctl --user daemon-reload
systemctl --user enable --now openshell-gateway
openshell gateway add https://127.0.0.1:17670 --local --name openshell
openshell status
```

Prepare the selected runtime first. Linger, credentials, runtime image choices
and gateway configuration are operator decisions. These commands describe the
documented flow; they were not validated against a running gateway here.

## Resume checklist and working-tree boundaries

1. Read current contributor instructions and inspect `git status`; other sessions
   may have changed the repository since this snapshot.
2. Treat redistribution and the OpenShell adapter as implemented and committed,
   with the test limitation above. Do not restart the discarded package split.
3. If asked to resolve verification, address the single fixture failure first
   and use a focused adapter check. Do not launch another full suite by default.
4. If asked to deploy, inspect current operator settings without copying secrets
   into docs, use existing signing identities appropriately, and follow README.
5. Preserve unrelated work. At this handoff's start, README and Thorium notes
   had changes, and build/redistribution and VirtualBox handoff files also existed.

This handoff adds documentation only. It neither fixes the known fixture issue,
runs tests, changes adapter recipe inputs, stages commits nor deploys software.
