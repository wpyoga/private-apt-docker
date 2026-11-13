# Build isolation, redistribution, and commit-splitting handoff

Recorded on 2026-11-13 to preserve the repository-specific information from a
conversation that the maintainer intends to delete. This document records the
questions, decisions, file assignments, actual commits, and verification limits.
It is a historical handoff, not a replacement for the current operator contract.

## Current state and where to resume

The changes discussed in the conversation have already been committed. At the
time of this handoff, HEAD is `268ad5d` (`chore: add temp/ to gitignore`). There
is no need to perform the original five-commit split again or rewrite history
merely to match the proposed commit titles.

The working tree contained these unrelated staged changes before this document
was written:

```text
M  README.md
M  docs/thorium.md
A  docs/virtualbox-investigation-history.md
```

Those changes belong to other work and were left untouched. This handoff is a new
documentation file; it was not staged or committed as part of recording it.

Read these documents for the maintained behavior:

- [Architecture and rationale](../ARCHITECTURE.md).
- [Configuration, deployment, and hook contract](../README.md).
- [Repository contributor instructions](../AGENTS.md).
- [Private build dependencies and host worker deployment](build-dependencies.md).
- [OpenShell adapter notes](openshell.md).

## Questions and decisions from the conversation

The maintainer first asked what `rebuild.sh` does. The answer was that it is a
host-side launcher coordinating the publisher and disposable build containers,
not a command that forces every package to rebuild.

The maintainer then asked how to divide a large set of unstaged changes into
commits. The recommendation was five commits organized by behavior:

1. Contributor guidance about dependency floors.
2. A test-runner fix allowing independent adapters to reuse test module names.
3. Private build dependency selection and isolated builds.
4. Framework support for unchanged upstream Debian package redistribution.
5. The OpenShell redistribution adapter.

The maintainer asked twice for more precise file and hunk assignments. The
complete original assignments are preserved below, together with the actual
commits that subsequently landed.

No commit creation, staging, package build, test execution, production operation,
or deployment was performed by the assistant during the original explanation
and commit-grouping review. It was a read-only assessment of the files and diffs.

## Actual commit history

These commits were inspected locally while preparing this handoff. Their subjects
are quoted exactly; their implementation was not revalidated through test runs.

| Original group | Actual commit | Subject and scope |
| --- | --- | --- |
| 1 | `0ead9fc` | `docs: explain repack, rebuild, and redistribute streams`; changes `AGENTS.md`, including the contributor guidance and redistribution exceptions |
| 2 | `b23b7e2` | `refactor: allow adapters to reuse test module names`; the isolated runner fix and its regression test |
| 3, plus documentation for 4 | `ea4aad2` | `feat: support private dependencies, also new stream for unchanged redistribution of release deb`; private dependency implementation/tests and both features' README/architecture documentation |
| 4 implementation | `ae1aa67` | `feat: redistribution for unmodified deb packages (implementation)`; redistribution helper, framework integration, configuration, setup, and discovery changes |
| 5 | `d94ffe1` | `feat: add openshell (redistribution)`; adapter, OpenShell notes, and offline adapter tests |
| Separate housekeeping | `268ad5d` | `chore: add temp/ to gitignore` |

The main difference from the recommendation is that redistribution documentation
landed with the private-dependency commit rather than the redistribution
implementation commit. The final README link to OpenShell also landed with that
documentation, before the adapter commit added the linked document.

Inspect actual contents without relying on this summary:

```bash
git show --stat b23b7e2
git show --stat ea4aad2
git show --stat ae1aa67
git show --stat d94ffe1
git show b23b7e2 -- tests/run.py tests/test_runner.py
```

## What rebuild.sh does

[`rebuild.sh`](../rebuild.sh) is run on the Docker host from the project root.
It accepts `amd64` or `arm64`, followed by optional `--once` or `--loop`.
The default is `--once`.

```bash
bash rebuild.sh amd64
bash rebuild.sh arm64 --once
bash rebuild.sh amd64 --loop
```

The launcher performs these steps:

1. Establishes and exports `FRAMEWORK_DIR`, checks the expected project files,
   rejects root execution, and validates the architecture and mode.
2. Reads the resolved Compose configuration and checks that the host caller's
   UID/GID matches the configured `rebuild-ARCH` service user.
3. Creates `build/workers/ARCH/queue` and `build/workers/ARCH/tmp`, exports the
   queue context, and takes an architecture-specific launcher `flock`.
4. Builds the ordinary Compose rebuild image and resolves its exact image ID.
5. Starts `lib/build-worker.sh` on the host and waits up to 30 seconds for its
   readiness file.
6. Starts a disposable Compose coordinator with the queue and temporary directory
   available at identical absolute paths on host and coordinator.
7. For `--once`, initializes the coordinator's private GPG agent and invokes
   `update.sh`. For `--loop`, uses the ordinary entrypoint and its interval loop.
8. Waits for worker or coordinator exit. Unexpected worker exit is a failure.
   Exit traps remove the coordinator and stop/wait for the worker.

The coordinator decides which current release targets need builds using the normal
recipe checksum and revision rules. The script does not force all builds, rebuild
historical releases, or create new signing identities.

The host worker creates a temporary image from the selected base, installs the
private dependency snapshot in image layers, and runs the adapter build hook as
the configured publisher UID/GID. Docker access stays on the host; the coordinator
does not receive a Docker socket. Build containers receive the stream workspace
and explicit context rather than the signing keyring or repository bind mounts.

Before replacing ordinary rebuild services with host launchers, follow
[the deployment instructions](build-dependencies.md#running-isolated-builds).
Run each architecture launcher in its own terminal or host service. The shared
repository lock still serializes complete architecture cycles.

Logs are under `build/workers/ARCH/`:

| Path | Purpose |
| --- | --- |
| `image-build.log` | Initial Compose image build |
| `coordinator.log` | Release queries, build requests, storage, and publication |
| `worker.log` | Host worker lifecycle and diagnostics |
| `queue/job-*/build.log` | Individual dependency image/build job output |

Successful queue requests are removed after their logs and installed-package
manifest are copied to the cycle workspace. Failed jobs retain their request and
log. Worker jobs have a 115-minute limit; the coordinator waits up to two hours.
The normal cycle workspace retention rules still apply.

## Original commit assignments, in detail

These lists explain the original unstaged diff. They are historical assignments;
use the actual commit history above to inspect the committed result.

### Group 1: contributor guidance

Suggested subject: `docs: clarify dependency version requirements`.

The initial standalone change was in `AGENTS.md`: investigate the actual feature
or bug-fix requirement, including Debian patches, before raising a dependency
floor solely because upstream names a newer version.

Later, the maintainer supplied replacement instructions explicitly allowing
redistribution provenance outside the package and index-only Installed-Size.
The actual `0ead9fc` commit includes those policy clarifications too.

### Group 2: independent test module discovery

Suggested subject: `fix: allow adapters to reuse test module names`.

Only two portions belong here:

- In `tests/run.py`, the loop inside `discover_tests()` that examines each
  directory's `test_*.py` files, removes a previously imported same-name module
  from `sys.modules` when it belongs to another directory, and explains why.
- In `tests/test_runner.py`, the entire
  `test_adapter_roots_can_reuse_test_module_names()` regression test.

Each adapter is its own unittest discovery root. Without clearing a previously
imported module, two adapters using a filename such as `test_source.py` can
interfere during discovery. The test creates two roots sharing a module name and
checks that both test cases are discovered and can run.

The `redistribute` addition to `select_directories()` and the OpenShell directory
discovery assertions do not belong in this group. They belong to group 4.

### Group 3: private dependencies and isolated builds

Suggested subject: `feat: support isolated builds with private dependencies`.

Whole-file assignments:

```text
docs/build-dependencies.md
lib/build-context.py
lib/build-dependencies.py
lib/build-worker.Dockerfile
lib/build-worker.sh
lib/checksum.py
lib/isolated-build.sh
lib/update-package.sh
rebuild.sh
tests/build_dependency_integration.py
tests/fixtures/build-dependencies/consumer-build
tests/fixtures/build-dependencies/provider-build
tests/test-build-dependencies.sh
tests/test_build_dependencies.py
tests/verify-build-dependencies.sh
update.sh
```

Related documentation portions:

- `ARCHITECTURE.md`: the sentence explaining that dependency ordering remains
  sequential, and the section on private build dependency ordering and isolation.
- `README.md`: the wording about ordering independent streams and placing
  providers first, and the private build dependencies section.

The implementation is one connected build path:

| File | Responsibility |
| --- | --- |
| `lib/build-dependencies.py` | Parse declarations, validate/order streams, select complete stored provider outputs, prepare architecture manifests, and remove unsatisfied targets |
| `update.sh` | Use dependency-aware ordering while preserving the repository lock and continued processing of unrelated streams |
| `lib/update-package.sh` | Prepare dependencies before checksumming and dispatch declared consumers through the isolated path |
| `lib/checksum.py` | Fingerprint dependency versions/hashes and the isolation implementation for adapters declaring private dependencies |
| `lib/build-context.py` | Copy verified dependencies and framework/adapter inputs, create a local APT snapshot and allowlisted environment, and annotate outputs with installed dependency metadata |
| `lib/isolated-build.sh` | Submit a queued request, wait for a bounded result, and retain failure evidence or record successful build metadata |
| `lib/build-worker.sh` | Own host Docker operations, process queued jobs, run the build container, and clean temporary containers/images |
| `lib/build-worker.Dockerfile` | Install exact dependency versions in a disposable image layer and record the installed package list |
| `rebuild.sh` | Launch the worker and publisher coordinator together |

Declarations use `STREAM PACKAGE [OP VERSION]`, with Debian version relations
`<<`, `<=`, `=`, `>=`, and `>>`. Providers must be in the same repository group.
Selection uses stream identities and complete provider output sets, not a
package-name-only search or a central registry.

A failed provider query does not automatically block a consumer if a previous
complete stored build satisfies its requirements. Missing dependencies block
only unavailable consumer architectures. Cycles and invalid declarations block
affected streams while unrelated streams and final publication can continue.

Dependency selection fingerprints both architectures so the two architecture
coordinators can agree on recipe identity. Newly available architecture outputs
can therefore cause an extra consumer revision. Ordinary Debian dependencies
and base image contents still have the documented checksum limitations.

Keep the worker and its dispatch together with selection and checksumming: a
commit that starts dispatching consumers without providing the worker path would
leave the feature incomplete. Existing adapters without dependency declarations
retain their direct build path. No diffofdiffs adapter is enabled by this change.

### Group 4: unchanged Debian package redistribution

Suggested subject: `feat: add unchanged package redistribution`.

Whole-file assignments:

```text
.env.example
codex-repo-setup.sh
compose.yaml
lib/publish.sh
lib/redistribute.py
lib/repository.sh
lib/resolve-builds.py
lib/store-packages.sh
tests/test_setup.py
```

Shared-file portions:

- `tests/run.py`: add `redistribute` to the adapter group discovery list.
- `tests/test_runner.py`: create a fixture redistribution/OpenShell stream and
  verify it is found in default and explicit adapter selection.
- `ARCHITECTURE.md`: qualify embedded revision rules as repack/rebuild behavior,
  include the redistribution group, and explain external import provenance.
- `README.md`: introduce the third group, document the Installed-Size exception,
  define `imports.json`, and explain import storage, configuration, and clients.

The generic README import-contract example can name OpenShell before its adapter
is added. The proposed split put the final link to `docs/openshell.md` and its
test command in group 5. In the actual history all of these README changes landed
in `ea4aad2`.

Redistribution preserves upstream package bytes, versions, control metadata,
dependencies, and maintainer scripts. It allocates no publisher revision.
The framework validates declared output identities and digests and rejects
different bytes claiming the same Package/Version/Architecture, including
collisions with another stored stream.

The new service uses:

```text
REPOSITORY_MODE=redistribute
REDISTRIBUTE_REPO_DIR
REDISTRIBUTE_GNUPG_DIR
REDISTRIBUTE_GPG_KEY
```

Setup provisions an independent signing identity and exports
`redistribute-pubkey.asc`. Public output and private keyring directories must
remain separate. The README contains the exact operator setup and client steps;
none of those operations were executed during this conversation.

Import provenance lives at:

```text
REPO_DIR/.state/imports/STREAM/PACKAGE_VERSION_ARCH.deb.json
```

Records bind the artifact hash to the source URL, stream, recipe checksum, and
size estimate. Publication verifies the stored bytes and enriches each Packages
stanza with `X-Publisher-Stream`, `X-Import-Recipe-SHA256`, `X-Upstream-URL`, and
the calculated `Installed-Size`. The size is the sum of regular-file payload
lengths rounded up to KiB, not a filesystem allocation estimate. These fields
are in the signed repository index; original archive metadata remains unchanged.

Recipe changes revalidate current targets without changing their package versions
or bytes. Missing current-target provenance can be recovered through download
and revalidation. Missing historical provenance requires operator recovery before
publication succeeds. Backups must include `.state/imports` alongside packages.

### Group 5: OpenShell adapter

Suggested subject: `feat: add OpenShell redistribution adapter`.

Whole-file assignments:

```text
docs/openshell.md
packages/redistribute/openshell/build
packages/redistribute/openshell/config
packages/redistribute/openshell/helper-inputs
packages/redistribute/openshell/query
packages/redistribute/openshell/validate.py
tests/openshell/test_openshell.py
```

Also originally assigned here: the final README paragraph linking OpenShell
notes and `bash tests/run.sh openshell`. This group depends on redistribution
support in group 4; it does not depend on private build dependencies in group 3.

The adapter queries the latest stable NVIDIA/OpenShell release, selects one
Debian asset for each requested architecture, validates the GitHub SHA256,
retains the upstream Debian revision, and copies the original archive.
Validation checks fixed executable/service/license paths and ELF architecture
without running upstream binaries or maintainer scripts.

The preserved package contains the CLI, gateway, prover, VM helper, and user
systemd gateway service. Preserved maintainer scripts may execute when a client
installs it. Packaging validation does not establish gateway/sandbox runtime
compatibility. Consult [OpenShell notes](openshell.md) for runtime requirements
and activation instructions; external requirements were not rechecked online
when recording this handoff.

## Files requiring hunk-level separation in the original plan

| Shared file | Group assignments |
| --- | --- |
| `tests/run.py` | Group 2: independent test-module imports; group 4: redistribution directory discovery |
| `tests/test_runner.py` | Group 2: duplicate-module regression; group 4: redistribution discovery assertions |
| `ARCHITECTURE.md` | Group 3: ordering/isolation; group 4: redistribution identity/provenance/storage exceptions |
| `README.md` | Group 3: dependency ordering and feature section; group 4: redistribution contract/configuration; group 5: final OpenShell notes/test link |

The suggested tool was `git add -p`. Some hunks combined adjacent changes from
both features and required splitting or manual patch editing. That staging advice
was for the original unstaged changes, not for the current unrelated staged work.

The original untracked `tests/openshell/test_openshell.py` needed inclusion in the
adapter commit even though it did not appear in ordinary tracked-file diff stats.
The `temp/` directory contained diffofdiffs and libgit2 investigation checkouts and
was excluded from feature commits. It is now covered by the housekeeping commit
listed above. Its contents were not deleted by this work.

## Review finding and its resolution

The initial review noted a mismatch between the then-current contributor rules
and redistribution: the rules prohibited checksum sidecars and required every
binary package to embed Installed-Size, while unchanged upstream redistribution
used external provenance and index-only size correction.

The maintainer supplied replacement instructions explicitly distinguishing the
three modes. The current `AGENTS.md` allows `.state/imports` and index-only size
estimates for byte-preserving redistribution. Repack and rebuild retain embedded
checksum/stream metadata, artifact-derived revisions, and package-level
Installed-Size. README and ARCHITECTURE now document that distinction.

This resolves the documentation/policy mismatch raised in the conversation. It
does not mean that this conversation performed a complete implementation audit.

## Verification status and commands

The original work in this conversation inspected scripts, adapters, tests, diffs,
working-tree state, and documentation to explain behavior and group commits.
It did not run regression tests, Docker integration, signing tests, live queries,
deployment, or client runtime validation. The presence of tests and verification
scripts is not evidence that they passed in this conversation.

The test sources include coverage for:

- Runner discovery with duplicate module names and the redistribution group.
- Dependency ordering, invalid graphs, constraints, retained provider builds,
  partial architecture availability, transitive providers, repeat-cycle reuse,
  shared revision convergence, verified context bytes, and environment filtering.
- A real Docker fixture that installs a private library/development package,
  compiles and executes a consumer, and checks failure retention and retry.
- OpenShell byte preservation, metadata/index size handling, architecture/layout
  validation, missing architecture retries, changed upstream bytes, corrupt
  downloads, missing provenance recovery, digest/asset validation, upstream
  Debian revisions, and publication rejection for corrupt stored packages.

Use these project-root entry points when verification is needed:

```bash
# Offline framework/setup checks, including dependency and runner tests.
bash tests/run.sh --framework

# Offline OpenShell adapter checks.
bash tests/run.sh openshell

# Complete offline regression suite, without the separate signing test.
bash tests/run.sh --offline

# Real Docker private-dependency integration, using an existing base image.
bash tests/test-build-dependencies.sh

# Combined private-dependency verification, including offline and Docker checks.
bash tests/verify-build-dependencies.sh
```

These commands are documented entry points, not commands executed for this
handoff. Run host coordinators as the host user with matching UID/GID. The Docker
integration defaults to `private-apt-rebuild-amd64:local`; an alternate image can
be supplied as its first argument. The combined verifier retains named logs in
`build/dependency-checks-*/`. Follow repository rules to redirect manual check
output to named logs, wait for completion or a bounded timeout, then inspect it.

The native Docker test covers amd64. Offline arm64 selection coverage does not
establish arm64 runtime correctness. A successful offline adapter test does not
establish OpenShell gateway or sandbox operation on a client.

Run the separate signing test when signing behavior changes or when intentionally
running the full suite. No signing test was needed for this documentation-only
handoff. Production configuration, keys, package storage, deployment, migration,
and cleanup were outside the work performed here.
