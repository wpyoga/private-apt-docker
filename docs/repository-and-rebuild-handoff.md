# Repository grouping and patched Debian rebuilds: maintenance handoff

This document preserves the requirements, decisions, implementation history and
verification boundaries of the conversation that introduced source rebuilds.
It was checked against the working tree on 2026-11-13. It is intended to make
that conversation disposable. Current code and the linked operational guides
supersede historical examples below. No operator secrets are recorded here.

## Goal and agreed requirements

The original need was to install local xfce4-terminal changes on a laptop without
waiting for Xfce maintainers or Debian to merge them. The build server is another
machine and has no graphical desktop. It should follow current Debian package
updates, start from clean Debian source, reapply local patches, and publish a
normal replacement Debian package. Dependency libraries should normally come
from Debian binary packages rather than being rebuilt just because the terminal
was changed.

The initial agreed source stream was Debian Trixie, not sid or a Git development
branch. Both amd64 and arm64 packages must be buildable from an amd64 server.
The operator prefers retaining a working patched package when Debian updates
before a successful local rebuild. Patch and build errors should be prominent
in logs. External notifications were discussed and deliberately left out.

The operator approved committing local patches to the public project. The first
adapter had an empty series so infrastructure could be tested independently of
application changes. That is historical: the current series contains
`000-shift-enter.patch` and `001-title-bar-tabs.patch`. For their current behavior,
source compatibility and detailed patch application rules, see
[xfce4-terminal](xfce4-terminal.md). Do not replace the current series with an
empty one when following the original infrastructure discussion.

## Repository membership and deployment decisions

`rebuild` was explicitly chosen as a repository name, not a framework instruction
to compile a package. The adapter's scripts own discovery and packaging. The
existing publisher already supports source compilation through its build hook;
reprepro or another archive manager was not needed.

The discussion considered an implicit default repository, mandatory per-adapter
`REPOSITORY` fields, APT components, and separate deployments with separate env
files. The accepted design instead uses directory membership:

```text
packages/
  repack/       # adapters that produce locally packaged binaries
  rebuild/      # adapters that compile selected source packages
  redistribute/ # later extension: preserve upstream .deb bytes and versions
```

There is no per-package repository override. Each publisher receives its group's
path as PACKAGES_DIR and discovers its stream directories. RELEASE_STREAM in
an adapter's data-only config identifies the stream within its repository.
The test runner still accepts an adapter name such as xfce4-terminal, rather
than requiring the operator to specify its group path.

One Git checkout, one `.env`, and one `compose.yaml` manage the deployment.
The initial grouping needed three services; the current configuration adds a
fourth for redistribution:

| Service | Group | Build selection | Repository identity |
| --- | --- | --- | --- |
| codex-repo-updater | repack | ARCHES from .env | REPO_NAME from .env |
| rebuild-amd64 | rebuild | amd64 | rebuild |
| rebuild-arm64 | rebuild | arm64 cross-build | rebuild |
| redistribute | redistribute | ARCHES from .env | redistribute |

The two rebuild services intentionally share one repository and its signing
identity. Repacks and rebuilds have separate output directories, keys and locks.
The current update lock blocks until available: a second rebuild worker waits
rather than skipping a complete interval. Earlier instructions describing a
nonblocking lock are superseded; see the
[rebuild lock incident](rebuild-lock-incident.md).

## Independent outputs and signing identities

The operator explicitly rejected a shared master keyring, cloned keyrings, and
using one repository's keyring for another. Each repository independently creates
or selects its key. There is no copy or synchronization relationship. Sharing the
common key-generation algorithm and validity settings does not share key material.

The current example paths are:

| Repository | Public output | Private GnuPG directory | Fingerprint setting |
| --- | --- | --- | --- |
| repack | /srv/apt/repack | /var/lib/apt-publisher/gnupg/repack | REPACK_GPG_KEY |
| rebuild | /srv/apt/rebuild | /var/lib/apt-publisher/gnupg/rebuild | REBUILD_GPG_KEY |
| redistribute | /srv/apt/redistribute | /var/lib/apt-publisher/gnupg/redistribute | REDISTRIBUTE_GPG_KEY |

Each pair of paths is configurable through PREFIX_REPO_DIR and PREFIX_GNUPG_DIR
in `.env`; PREFIX is REPACK, REBUILD or REDISTRIBUTE. Containers see only their
selected output as /repo and their selected keyring as /gnupg. Public exports are
repack-pubkey.asc, rebuild-pubkey.asc and redistribute-pubkey.asc. Setup writes the
host UID/GID and three selected fingerprints into the single `.env`.

An earlier example used /srv/apt/codex and then /srv/apt/repack/repo with an
adjacent gnupg directory. The operator requested replacing the codex path name.
The later public-root design uses the paths above so serving /srv/apt does not
serve private keyrings. REPO_DATA_DIR and the single global GPG_KEY are obsolete.
Do not automatically move existing production data or rotate working keys.
Configure explicit existing paths and fingerprints when preserving a deployment.

Current setup runs GPG in temporary containers with private agent sockets; it
no longer requires host GPG commands to operate on the keyrings. Each running
publisher also gets a container-local socket directory. Read
[storage and signing](storage-and-signing.md) before migration, recovery or
key maintenance. That guide records the later operational incidents and checks.

## Source-to-package workflow

1. The terminal query hook creates isolated APT list storage and updates the
   Trixie, trixie-updates and trixie-security source indexes declared by its
   sources.list. APT verifies archive metadata and downloaded source checksums.
2. `apt-get source --download-only xfce4-terminal` downloads the selected source
   descriptor, original source archive and Debian packaging archive. A persistent
   clone of Debian's Git repository is unnecessary: released Debian source is
   the build input. Git is useful separately for investigation and patch work.
3. The metadata helper requires one descriptor and a valid source version, and
   writes architecture targets while preserving Debian's complete source version.
4. The framework chooses a local revision from stored package metadata. The
   adapter starts each architecture from a fresh `dpkg-source -x` extraction.
   Debian patches, if present in that source version, remain the baseline.
5. Quilt imports the checked-in local series in order and pushes with zero fuzz.
   Offsets can still occur; zero fuzz does not mean zero offset. A failed patch
   stops that stream's build instead of silently dropping the local change.
6. The adapter makes guarded Debian packaging adjustments and compiles with
   dpkg-buildpackage. Currently it enables maintainer mode while preserving
   utempter support, and marks xfce4-dev-tools native for arm64 cross-building.
   These adjustments and their exact expected Debian lines are documented in
   the [terminal guide](xfce4-terminal.md).
7. It verifies package identity, architecture, executable and desktop entry,
   recalculates Installed-Size from final staged contents excluding DEBIAN/, and
   embeds publisher checksum/stream metadata before returning its .deb.
8. The framework validates outputs, stores new artifacts without overwriting
   existing package identities, and generates signed indexes. Other streams
   continue after a stream failure; previously published packages remain stored.

For inspected source version 1.1.4-1, Debian supplied no quilt patch directory.
Its packaging was still in 3.0 (quilt) format. The general rule to preserve Debian
patches must not be read as proof that every source version contains patches.

## Versions, patch revisions and rebuild boundaries

A Debian version such as 1.1.4-1 becomes a query target of 1.1.4-1+local. The
publisher appends its stored-artifact-derived numeric revision, yielding
1.1.4-1+local-1. A later recipe revision can yield 1.1.4-1+local-2; a newer Debian
source version has a separate revision history. No manual revision counters or
checksum sidecars are needed for repack/rebuild streams.

Adapter files, including patches, executable modes and comments, affect the
recipe checksum. Declared shared helpers, the shared Dockerfile and MAINTAINER
also participate. Thus a terminal-only patch edit affects that adapter; changing
the Dockerfile or maintainer can affect other current targets. The original
move into groups changed the Dockerfile and caused a one-time broad recipe
change. Documentation belongs outside packages/ to avoid accidental revisions.
Historical upstream versions are not rebuilt just because a recipe changes.
Matching partial outputs resume at their existing revision; old artifacts remain.

Changing repository identity or output paths is different from changing package
contents. Repository metadata can change without recompilation. These rules
apply to local repacks/rebuilds; unchanged redistribution has its own provenance
contract, described in [the build/redistribution handoff](build-and-redistribution-handoff.md).

## Building and operating without this chat

Run host entry points from the checkout root. FRAMEWORK_DIR defaults to the
current directory and is exported internally. A manual export is not required;
explicit overrides remain supported. Internal hooks still require FRAMEWORK_DIR,
ADAPTER_DIR and WORKSPACE rather than inferring their paths from script names.

For a new server, follow [README setup](../README.md#first-time-setup): copy
.env.example to .env, set operator values and independent paths, run
`./codex-repo-setup.sh`, then `docker compose up -d --build`. Setup itself builds
the base image before using containers for signing operations. Setup and service
startup have real effects; do not use production settings for experiments.

A desktop session is unnecessary for compilation. Development libraries come
from Debian binary packages in image layers. Native amd64 and arm64 cross-build
images are separate because their Xfce dependencies require conflicting xfconf
packages. Current Compose uses the root Dockerfile's rebuild target with a
TARGET_ARCH build argument. It no longer uses the initial adapter-local Dockerfile
or Compose service build contexts. See [Docker build cache](docker-build-cache.md)
for the current stages and refresh behavior. Packages are copied into images;
a source edit needs an image rebuild and service recreation before deployment.

Rootless Docker was discussed as a possible server environment. It was not
validated in the original work. The checked Compose deployment uses configured
host UID/GID for bind-mounted writes; rootless UID mapping must be checked
separately. Successful container compilation does not establish rootless support,
bit-for-bit reproducibility, or interactive desktop correctness.

To consume the patched terminal, serve the rebuild output, install its exported
public key in the laptop's keyring, and configure a Signed-By APT entry for the
rebuild URL. The package remains named xfce4-terminal. Prefer its repository
using a package-specific pin with `Pin: release o=rebuild` and priority 990,
then check `apt-cache policy xfce4-terminal` before installation. Confirm the
candidate on machines with APT::Default-Release. This keeps the last successful
patched version preferred while newer Debian source is being rebuilt. Quit old
terminal processes before checking new behavior. Exact client commands are in
[the terminal guide](xfce4-terminal.md#laptop) and [README](../README.md#debian-client).

## Verification history and limits

The original implementation successfully built Debian source 1.1.4-1 for amd64
and cross-compiled it for arm64 with an empty local series. ELF architecture,
package identity and Installed-Size in packages and indexes were checked. Those
results predate the current patches, maintainer-mode change, later build-image
refactors and dependency framework; they do not validate all current features.

Original retained evidence, if still available under ignored build/, includes
rebuild-artifact-checks.log, rebuild-live-amd64.log,
rebuild-live-arm64-retry.log, independent-keys-tests.log,
groups-focused-final.log and framework-root-tests.log. Logs can be removed or
become stale; source-controlled docs and test inputs are the durable handoff.

The original grouping regression run executed 196 tests. Four errors were
reported: one setup fixture still lacked the newly required settings and three
GIMP download tests could not bind loopback sockets in the sandbox. The setup
fixture was corrected and focused checks passed. The three socket tests remained
unverified after an escalation request was interrupted. They were included because
GIMP adapter paths moved with the other repacks; they were unrelated to terminal
compilation. Do not describe that full run as entirely passing.

Separate targeted checks passed for setup/signing-directory selection, Compose
keyring and storage isolation, grouped discovery, framework behavior, terminal
fixture packaging, and FRAMEWORK_DIR defaults. Syntax and whitespace checks
passed for those edits. These historical checks are not new test executions by
this documentation task. The current terminal guide records later patch and
configure verification and its narrower runtime limitations.

No production deployment or laptop installation was performed in the original
infrastructure conversation. The operator explicitly chose to test production
later. This handoff neither establishes production readiness nor deploys changes.
For current testing use the documented runner from the project root, redirect
output to named logs, wait for completion and inspect results:

```sh
mkdir -p build
timeout 30m bash tests/run.sh --framework > build/handoff-framework.log 2>&1
timeout 30m bash tests/run.sh xfce4-terminal > build/handoff-terminal.log 2>&1
```

Run the signing integration test when changing signing code, or intentionally
running the full suite. This documentation-only task needs factual, local-link
and whitespace checks rather than package builds or signing operations. Keep
failure evidence and useful verified sources; never clean production artifacts
or keys as part of test housekeeping.
