# Codex adapter and stream configuration: conversation handoff

This document preserves the explanation, decisions, implementation history, and
verification limits from the original Codex/package-configuration conversation.
It was checked against the current source on 2026-11-14 so the chat can be deleted.
The original checkout was named `codex-apt-docker`; the current checkout is
`private-apt-docker`. Paths in the current-state sections use today's layout.

Use [README](../README.md) for the maintained configuration and exact hook
contract, [ARCHITECTURE](../ARCHITECTURE.md) for system design, and
[AGENTS](../AGENTS.md) for development conventions. Historical examples below
explain decisions; they must not replace the current contract.

## What the user wanted

The discussion began by asking whether the number of scripts made the code too
complicated, starting with Codex. The aim was to understand each responsibility
and remove needless configuration or indirection, rather than minimize file count
at any cost. The questions then established these requirements:

- Combine related adapter parameters in one configuration file.
- Remove the revision-policy file when automatic revision assignment is the
  intended standard behavior.
- Treat the directory name as descriptive only. A name such as
  `alice-bob-charlie` must not become package identity or revision history.
- One adapter directory follows one release stream, explicitly named in config.
- One upstream download or compilation may produce multiple Debian packages.
  Do not require separate adapters and repeated compilation for each output.
- Derive revision history collectively from stored outputs. Do not nominate one
  binary package as the authoritative version record.
- Use a key-value file that shell can read, rather than JSON for these settings.
  Parse it as data; do not execute it with `source` or `eval`.

The word “family” was discussed as a way to describe related output packages.
It did not become a separate required identity field. There is no inferred family
name from the directory and no mandatory family-plus-channel naming convention.
The configured stream identifier is authoritative.

## The resulting identity and configuration model

Today's [Codex config](../packages/repack/codex/config) contains:

```sh
RELEASE_STREAM=codex
BINARY_PACKAGES=codex-cli
```

A hypothetical adapter that builds two related packages could declare:

```sh
RELEASE_STREAM=example-stable
BINARY_PACKAGES="example-cli example-common"
```

The example is illustrative, not a request to split Codex into those packages.
Codex still produces one `codex-cli` package per architecture.

| Concept | Meaning |
| --- | --- |
| Adapter directory | Location of config, query, build, and recipe inputs |
| `RELEASE_STREAM` | Persistent stream identity used for metadata, revision tracking, and storage |
| `BINARY_PACKAGES` | Debian binary package names the build must produce |
| Upstream version | Version selected by this adapter's query |
| Debian revision | Publisher suffix, such as `-1` or `-2`, for repack/rebuild recipes |
| `PUBLISHER_STREAM` | Exported runtime value derived from `RELEASE_STREAM` |

The stream value is an identifier, not an instruction that the runner interprets
as “stable” or “preview.” The query implements the actual release-selection
policy. Renaming a directory while preserving its contents and configuration
must not change stream metadata, pool paths, recipe checksum, or selected
revision. Names may affect discovery order for independent adapters and appear
in diagnostic paths. Group membership is a separate current feature: placing an
adapter under `repack/`, `rebuild/`, or `redistribute/` selects its repository mode.
Moving between groups is not equivalent to renaming a leaf directory.

Multiple streams may produce the same Debian package name. For example, separate
GIMP release lines can both produce `gimp`. The publisher does not force unique
Debian names, pin clients to a stream, or migrate them automatically. APT version
ordering and client preferences govern selection.

The [configuration parser](../lib/config.sh) accepts one `KEY=value` per line,
blank lines, whole-line comments, and matching single or double quotes around
values. Quotes are removed without shell expansion. There are no spaces around
`=`. Unknown keys, duplicate keys, invalid stream IDs, duplicate package names,
and missing required values fail. A shell expression in a value is not executed.
Stream IDs must be unique among adapters in a cycle.

The initial implementation used lowercase `release_stream` and `binary_packages`.
Those names are historical: current keys and shell variables are uppercase.
Current architecture-specific lists are a later extension:
`BINARY_PACKAGES_AMD64` and `BINARY_PACKAGES_ARM64` may replace the common list.
Both must be supplied, and the common and architecture-specific forms cannot be
mixed. Revision selection considers their union; each architecture build must
produce its own declared names. See the
[config contract](../README.md#one-directory-per-configured-release-stream).

## Why revision-policy and package-name disappeared

Originally, `package-name` held one Debian name and `revision-policy` contained
`automatic`. These were two one-value parameter files.

`automatic` was the only accepted explicit revision-policy value. Nevertheless,
there was a second behavior: absence of the file meant the query supplied a full
Debian version and owned its revision. Any other explicit value failed. The
choice was therefore “automatic file present” versus “adapter-owned version
when absent,” rather than several useful named policy values.

The user chose to remove that switch. Repack and rebuild queries supply upstream
versions, and the shared runner always assigns publisher revisions. There is no
revision-policy file, configurable manual revision mode, revision counter, or
checksum sidecar. Current byte-preserving redistribution is a later, separate
repository mode; it retains upstream versions and bytes and does not restore the
old revision-policy mechanism. Its provenance is documented in the
[redistribution contract](../README.md#unchanged-package-redistribution).

`package-name` was replaced by the config's package list. This handles both the
original single-output case and several binary packages built together.
Removing or changing an adapter file changes recipe inputs, so this migration
can allocate a new revision for the currently queried upstream release. It does
not rewrite stored packages or rebuild all historical upstream releases.

For a custom adapter migrating from the original layout, use its old stream
identity as `RELEASE_STREAM` if that history should continue. Do not choose a new
identity merely because the directory is being renamed. Update its hooks to the
current contract too; the historical command arguments below are not supported
compatibility interfaces.

## Multiple executable files versus multiple Debian packages

A Debian binary package is a `.deb`, not an individual executable file.
`codex-cli` already contains several upstream files, including `bin/codex` and
`bin/codex-code-mode-host`. This never required several package-name entries.

A source release may instead produce several `.deb` files, for example a CLI,
common data, and developer headers. Such outputs belong in one adapter when
building them together is useful. The build hook owns download, extraction,
compilation if needed, and the split into package trees. The framework does not
require downloading or compiling the same source separately per binary package.
Codex itself repackages precompiled binaries; it does not compile a Debian source
package or generate a `.dsc` as part of this process.

For the current repack/rebuild contract:

```sh
query
build VERSION ARCH OUTPUT_DIR
```

The framework exports `FRAMEWORK_DIR`, `ADAPTER_DIR`, `WORKSPACE`,
`PUBLISHER_STREAM`, architecture/package lists, and other required context.
The changing version, architecture, and output directory are build arguments;
there is no workspace argument today. Hooks must use supplied context rather
than infer their location from `$0` or `BASH_SOURCE`.

Build runs once for each incomplete queried architecture and returns the whole
required output set in the output directory. Output names are
`NAME_VERSION_ARCH.deb`; current support also permits `Architecture: all` outputs
with `_all.deb`. All outputs for a selected upstream version share the assigned
publisher version. Architecture-independent outputs are stored once and indexed
for both architectures. Missing/extra files or incorrect identity, version,
architecture, stream, or checksum metadata fail validation before any output
from that invocation is stored. See the
[hook contract](../README.md#query-and-build-hooks) for exact requirements.

## Version truth and recovery on the next run

No individual binary package is the source of truth. For repacks and rebuilds,
the query selects the current upstream version and stored `.deb` control metadata
supplies revision history. The framework inspects all declared binary names and
architectures, including artifacts from other streams with overlapping names.

For each selected upstream version:

1. Find the highest numeric Debian revision already used by any declared name.
2. Find this stream's latest revision and embedded recipe checksum.
3. If that checksum matches current inputs, reuse this stream's revision.
   Another stream's higher revision does not prevent that reuse.
4. Otherwise allocate the highest existing revision plus one, or `-1` when none
   exists for that upstream version.
5. Check every required output for each requested architecture at that revision.
   Skip a complete architecture; rebuild an incomplete one.
6. Validate the regenerated output set. Preserve bytes already stored with the
   matching identity/metadata and install only missing packages.

For example, `example-cli` and `example-common` at `2.0.0-3` collectively establish
that revision. If the arm64 common package is missing, rebuild that architecture
at `2.0.0-3`; do not allocate `-4` merely because one output is missing. A recipe
change does allocate a new revision. A completely failed build with no stored
artifact retries the same candidate revision next time. A new upstream version
starts its own history. Reverting a recipe still creates a new revision because
it differs from the latest stored recipe.

The important embedded fields are `X-Publisher-Stream` and
`X-Build-Inputs-SHA256`. Pool storage is `pool/main/STREAM/`, using config identity.
Whole-set validation precedes storage, but storage is atomic per file, not a
transaction over all packages. If storage fails after one complete file was
installed, its metadata allows a later cycle to resume. Existing package bytes
are never replaced by a resumed build.

Today's checksum includes adapter-relative files, contents, executable bits,
Dockerfile text, global `MAINTAINER`, and declared shared helper inputs. Codex
lists its shared package/GitHub helpers in `helper-inputs`. Directory names and
timestamps are excluded. General notes belong outside `packages/` because
adapter comments and documentation are recipe inputs. Do not revive the original
`revision-env` file: later design made maintainer handling explicit. See
[checksum design](../ARCHITECTURE.md#checksums-and-revision-history) for current
source-build dependency inputs and other limits.

## Codex: current files and execution flow

The current adapter is [packages/repack/codex](../packages/repack/codex).

| File | Responsibility |
| --- | --- |
| `config` | Declare stream `codex` and output package `codex-cli` |
| `query` | Select latest stable GitHub release and per-architecture archive metadata |
| `build` | Download, verify, extract, validate, stage and package one architecture |
| `control.in` | Debian control template, including dependencies and publisher metadata |
| `helper-inputs` | Declare shared implementation files that contribute to the recipe checksum |

The process is:

```text
update.sh: discover adapter and load configured identity
  lib/update-package.sh: process this stream
    Codex query: release.json, assets.json, targets.tsv, release-date
    lib/checksum.py: current packaging fingerprint
    lib/resolve-builds.py: assign revision and identify incomplete targets
    Codex build: produce codex-cli_VERSION_ARCH.deb
    lib/store-packages.sh: validate output set and store missing packages
  lib/publish.sh: index and sign stored versions
```

The framework handles locking, sequencing, revisions, output storage, and signed
publication. The adapter handles upstream-specific release selection and payload
rules. One stream's failure does not stop other streams or the publication
attempt; successful stored artifacts remain available. The interval starts after
the complete cycle finishes. These are current framework responsibilities, not
extra work that every adapter should duplicate.

### Query details

The [query hook](../packages/repack/codex/query) uses Bash/jq and shared
[GitHub helpers](../lib/adapter/github.sh):

1. Fetch GitHub's latest release for `openai/codex`, rejecting drafts and
   prereleases and requiring a structured asset list.
2. Require a tag like `rust-v1.2.3`; remove `rust-v` to obtain `1.2.3`.
3. Map `amd64` to `x86_64-unknown-linux-musl` and `arm64` to
   `aarch64-unknown-linux-musl`.
4. Select `codex-package-TARGET.tar.gz`, requiring a unique matching asset,
   SHA256 digest, and an HTTPS URL without whitespace.
5. Warn and omit a missing architecture rather than invent a download.
6. Write query outputs in `WORKSPACE`.

| Generated file | Consumer and purpose |
| --- | --- |
| `release.json` | Adapter's fetched upstream release metadata |
| `assets.json` | Build's architecture-indexed version, filename, URL and SHA256 |
| `targets.tsv` | Runner's upstream-version and architecture rows, separated by tabs |
| `release-date` | Publication timestamp for optional inactivity monitoring, when supplied upstream |

These are temporary working data, not more maintained scripts. `assets.json` is
adapter-private structured download metadata; using JSON here does not make the
simple key-value configuration JSON. If an architecture appears upstream later,
the next cycle can add it at the existing matching revision. Existing older
architecture packages are retained while an upstream asset is missing.

### Build details

The [build hook](../packages/repack/codex/build) reads its selected asset from
`assets.json`, checks that the assigned version's upstream component agrees,
and uses the shared download helper in refresh mode to download and verify the
SHA256. It then performs these adapter-specific steps:

- Reject unsupported tar member types before extraction. Use GNU tar's path
  protections without enabling absolute names or link dereferencing.
- Reject extracted symlinks resolving outside the extraction root before later
  reads or permission changes. Remove privileged and group/other writable bits.
- Require `bin/codex`, `bin/codex-code-mode-host`, and `codex-package.json`
  directly under the extraction root. A new enclosing directory is an error.
- Check that metadata version starts with the expected upstream version and
  that its entrypoint is exactly `bin/codex`. The version check is a prefix
  check, not strict equality.
- Copy the payload under `/usr/lib/openai-codex/` in the staged package tree.
- Replace `codex-resources/bwrap` and `codex-path/rg` with executable wrappers
  that invoke `/usr/bin/bwrap` and `/usr/bin/rg`, forwarding arguments.
- Ensure the required Codex executables are executable and create `/usr/bin/`
  symlinks for executable files in the upstream `bin/` directory.
- Render `control.in` and build the `.deb` with the shared package helper.

The package depends on Debian `bubblewrap` and `ripgrep`, and recommends `git`.
Wrappers preserve upstream relative paths while allowing Debian to manage those
tools. `MAINTAINER` comes from global configuration. The control template includes
publisher stream/checksum fields and `Installed-Size`; the size is calculated in
KiB from the final staged tree excluding `DEBIAN/`, not from compressed archive
size. `dpkg-deb --build` does not invent that field.

Codex validation tests cover metadata, download integrity, architecture selection,
permissions, links, traversal, required paths, wrappers, dependencies, installed
size and its published index value. Those checks inspect fixtures and artifacts;
they do not establish interactive Codex runtime behavior on a client.

## Original files and interfaces: historical only

At the start of the chat, `packages/codex/` contained four scripts and two
single-value configuration files:

| Original file | Original purpose | Current replacement |
| --- | --- | --- |
| `query` | Download latest GitHub release JSON and call Python parser | Bash/jq query plus declared shared GitHub helpers |
| `release.py` | Validate release/tag/assets and write targets/download metadata | Logic now in query and shared GitHub helpers |
| `build` | Download and stage one precompiled archive into one `.deb` | Current build hook, output-directory contract and shared package helpers |
| `archive.py` | Extract with Python tarfile and validate layout/metadata | Fixed-layout GNU tar and jq checks in build |
| `package-name` | Hold `codex-cli` | `BINARY_PACKAGES` in config |
| `revision-policy` | Opt in to automatic revisions | Removed; standard repack/rebuild behavior |

The old archive helper accepted either root-level files or one enclosing
directory. That fallback is explicitly superseded by current fixed-layout policy.
The old shared `lib/package-files.py` combined revision resolution and storage;
current responsibilities live in `lib/resolve-builds.py` and
`lib/store-packages.sh`. Do not recreate removed helpers just to match the chat.
The later [adapter refactor handoff](adapter-refactor-handoff.md) records shared
helper extraction and subsequent verification.

The original interfaces were `query WORKDIR` and
`build WORKDIR VERSION ARCH OUTPUT`, where OUTPUT was one file. The multi-output
change first made the fourth argument an output directory; a later context
refactor moved WORKSPACE into the exported environment. Today's interfaces are
shown above and owned by the README. Lowercase key examples and the early
statement that `Architecture: all` was unsupported are likewise superseded.

## Historical verification and the GPG sandbox limitation

The conversation recorded these successful offline runs at the time:

| Milestone | Historical result |
| --- | --- |
| Remove revision-policy and make revisions unconditional | 34 regression tests passed |
| Add data-only config, configured identity and multi-output builds | 41 regression tests passed |
| Shell syntax and whitespace checks for those changes | Passed |

Coverage included directory renaming without rebuild/history changes, shared
revisions across outputs, allocation considering every binary name, resuming
missing packages, rejecting invalid configuration without executing commands,
and validating all outputs before storing any. These counts refer to the old
suite, not today's complete suite. Temporary failed development runs were fixed
before those successful runs. No production deployment, live upstream runtime
acceptance, or real-signing success was established by this conversation.

Real signing was attempted with a throwaway key and isolated APT state, without
host installation. The test already created its GPG homedir under the project:
`build/signed-test-XXXXXX/keyring`. GPG wrote its keybox but failed to start its
agent. A later explicit diagnostic used a shorter project-local directory,
`build/gpg-DETQtS`, and reported:

```text
error binding socket to '.../build/gpg-DETQtS/S.gpg-agent': Operation not permitted
```

A separate `/tmp` attempt had the same error, but the project-local result is the
important evidence: making the homedir writable did not grant permission to bind
a socket. The user requested that operations stay in the sandbox and explicitly
preferred a homedir beneath the project. The proposed outside-sandbox signing
run was not completed. Temporary diagnostic keyrings were cleaned up; there are
no test keys from this chat that should be recovered or used for production.

The user also asked whether batch mode could avoid gpg-agent. The signing test
already used `gpg --batch --pinentry-mode loopback --passphrase ''` for temporary
key generation. Batch mode suppresses interactive prompts; the installed GnuPG
still delegates private-key operations to its agent. Loopback pinentry does not
remove the agent or its socket requirement. The conclusion was a verification
limit, not a decision to remove signing, disable sandbox controls, or replace
production signatures with test stubs.

Later production work isolates container agents with private runtime tmpfs
sockets; see [storage and signing operations](storage-and-signing.md). That is a
separate design and verification history. The original sandbox failure must not
be described as proof that today's production signing fails, nor do later
container changes retroactively verify the original test run.

An earlier part of the conversation also encountered a read-only session profile.
The user changed project permissions and implementation then proceeded. That was
a session execution restriction, independent of the current directory and
collaboration mode, not a repository feature or a requirement to alter host file
permissions. Do not treat the chat's old session settings as the current setup.

## Continuing without this chat

The requested revision-policy removal, key-value config, configured stream
identity, and multiple-output support are implemented. There is no deferred
package-family schema or directory-identity redesign left from this discussion.
Any new work should start from current source and the maintained contract, not
from the first explanation's file list. Preserve unrelated working-tree changes.

For regression work, use today's entry points from the project root. Redirect
stdout and stderr to named logs, wait for completion or a bounded timeout, and
then inspect the logs. For example:

```bash
mkdir -p build/logs
timeout 15m bash tests/run.sh codex > build/logs/codex-regression.log 2>&1
timeout 15m bash tests/run.sh --framework > build/logs/framework-regression.log 2>&1
```

Use `bash tests/run.sh --offline` for the complete offline suite. Run the signing
check only for signing changes or an intentional full run, using an isolated
throwaway keyring. It requires local socket permission as well as filesystem
write access. Keep signing failures as explicit test limitations if the execution
environment denies that permission. Do not use production data or keys, deploy,
or migrate storage merely to validate documentation.

This handoff's 2026-11-14 update is documentation-only. Current source, local
links, and whitespace were checked; no package builds, regression suite, signing
checks, container builds, or live publication were rerun for this documentation.
The historical test counts above remain historical evidence only.
