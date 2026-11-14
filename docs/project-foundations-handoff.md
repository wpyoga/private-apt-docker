# Project foundations: decisions and conversation handoff

This document preserves the original publisher-design conversation so it can be
deleted. It was checked against the repository on 2026-11-14. It records the
maintainer's intent, the alternatives discussed, what was implemented, and what
later work superseded. It contains no operator configuration or private keys.

Start with [the documentation index](README.md) for current guides,
[AGENTS.md](../AGENTS.md) for development rules, and
[ARCHITECTURE.md](../ARCHITECTURE.md) for current behavior. Historical paths and
commands below explain evolution; they are not instructions to restore old code.

## Goal and working agreement

The project started with a working Codex APT publisher. The initial request was
to make it readable, generalize the publisher, and support multiple packages
with independent update queries and packaging methods. The framework should
coordinate work, while each package handles its actual upstream conventions.

The maintainer repeatedly prioritized simplicity over cleverness. The intended
reader is an average high-school student: ordinary code comprehension is a
reasonable assumption, familiarity with intricate shell tricks is not. Code
should be easy to explain from top to bottom.

The detailed style agreement is:

- Prefer descriptive names, explicit steps, smaller functions, and smaller
  scripts with meaningful responsibilities. A shorter expression is not better
  if a maintainer must decode it.
- DRY is a tool rather than an objective. Some duplication is easier to maintain
  than a general abstraction with configuration and indirection. Shared helpers
  are useful when they simplify their callers, not just remove repeated lines.
- Use blank lines between logical operations and line breaks for long commands.
  Do not insert a blank line after every statement. A download followed by JSON
  interpretation is a useful boundary; assignments describing one operation can
  remain together.
- Use `UPPER_CASE` for shell variables, local variables, and project config keys.
  Use lowercase descriptive function names. Python retains normal Python style.
  External commands keep their own option spelling; do not uppercase curl, jq,
  Docker, APT, or other tools' options to match project variable style.
- Quote expansions and positional arguments, including `VERSION="$1"`. Use
  arrays for argument lists. The framework deliberately splits declared package
  and architecture lists, but paths must remain safe when they contain spaces.
- Require necessary context and fail early with a useful error. Do not make each
  internal hook a standalone general-purpose program with path guessing and
  fallback configuration.
- Use logs for maintainer-visible errors. External email/Slack notifications and
  an emergency-update feature were discussed as possible later work, not part of
  the original implementation.

The maintainer asked for visible progress and direct answers about current work.
Finish the authorized task, explain what changed and what was verified, and do
not stop for repeated confirmations about already agreed routine work. Later
verification refinements require batched commands, named logs, waiting for
completion, host-user coordinators, and reuse of useful verified downloads;
the current [verification rules](../AGENTS.md#verification) take precedence over
the original live-output examples.

## Choosing Bash, jq, and Python

The maintainer questioned using Python for jobs largely consisting of file
operations. The accepted approach is to choose the clearest tool for the job:
shell for command coordination and files, jq for ordinary JSON selection, and
Python when structured bookkeeping or metadata/date processing is clearer.
Replacing a Python file with a large inline Python heredoc in shell was explicitly
rejected: it combines the navigation and quoting problems of both languages.

The original Codex `query` plus `release.py` became one Bash/jq query hook. This
removed a helper that mostly selected JSON fields. The archive helper, first
Python and later shell, had only one production caller and was folded into
short functions in Codex's build hook. A separate archive framework was not
needed for that package.

Outside the adapters, `package-files.py` originally both selected revisions and
stored artifacts. It was split by responsibility: target validation and revision
selection now live in `lib/resolve-builds.py`; final validation and file storage
live in `lib/store-packages.sh`. The separate `validate-targets.py` was merged
into resolution so that the target file is interpreted in one place. A small
`write-env.py` was folded into setup using awk and an atomic replacement file.
Publication was organized into short functions. Python remains for fingerprints,
revision bookkeeping, activity dates, and later tasks where it is useful.

The initial large test module was split by responsibility. Later work established
the current per-adapter test directories and `tests/lib/` shared test helpers.
Use the current test runner, not the original recursive unittest command.

Later shared operations in `lib/adapter/` are compatible with this principle:
they handle publisher mechanics, and adapters declare their dependencies through
`helper-inputs`. Upstream layout or version policy still belongs in adapters.
See [the adapter refactor handoff](adapter-refactor-handoff.md).

## Explicit context, configuration, and templates

The framework exports `ADAPTER_DIR` and `WORKSPACE` to hooks. `query` takes no
workspace argument; `build VERSION ARCH OUTPUT_DIR` receives only values that
vary for that invocation. Internal scripts use the supplied context instead of
deriving paths from `$0`, `BASH_SOURCE`, or a series of alternative variables.

The discussion compared `WORKSPACE="$WORKSPACE"` with a proper requirement check.
With `set -u`, self-assignment fails for an unset variable but accepts an empty
one. The chosen form rejects both:

```bash
: "${WORKSPACE:?WORKSPACE must be set and non-empty}"
```

The original public scripts also required exported `FRAMEWORK_DIR`. Later host
entry points intentionally adopted the project-root working directory as their
default and export it internally. That is the current public-entry behavior;
hooks still require their caller's context. Do not reintroduce script-relative
discovery or remove an intentional current public default based on old examples.

The operator's `.env` owns `MAINTAINER`, repository identity, paths, scheduling,
and signing settings. Someone cloning the project can set their own identity
without editing package templates. Adapter `config` files are parsed as data,
not sourced as arbitrary shell. Operator `.env` is trusted shell-compatible data
and is sourced by setup. The two configuration mechanisms have different roles.

The maintainer asked to move the generated control-file block out of the build
script. `control.in` was chosen as the conventional template name.
`gettext-base`/envsubst was rejected as an unnecessary dependency. Templates use
`@VARNAME@` placeholders and common tools such as sed, with replacement values
escaped where needed. Current shared rendering supplies these mechanics.

Installed size was added in later work. Repacked and rebuilt outputs must
recalculate `Installed-Size` from the final staged tree excluding `DEBIAN/`, even
when importing a package that already has a value. Redistribution keeps archive
bytes intact and supplies its size estimate in the signed index. Follow the
current hook contract and adapter tests for these requirements.

## Execution order, waiting, and locks

The maintainer asked whether processing was depth first, step by step across
packages, or parallel. The agreed model finishes one stream, including its
architecture builds, before starting the next. There is no worker pool in a
publisher cycle. Later dependency ordering can reorder streams but remains
sequential. Separate services can run independently; services sharing repository
storage serialize their cycles through that repository's lock.

The maintainer specifically preferred waiting X hours after work, rather than
executing every X hours on a clock schedule. The first cycle starts immediately.
With the default 21600-second wait, a cycle running 08:00–08:20 is followed by
the next at 14:20. Update urgency was considered low; emergency triggering was
left as a potential feature. A manual single-cycle command is documented in
[publisher operations](publisher-operations.md#running-an-update-now).

Blocking on child scripts handles work inside a cycle. The lock addresses a
different problem: another manual invocation or container writing the same
repository. A kernel `flock` is not a test for whether a file exists. The kernel
releases it when the holders exit, so a leftover empty file is not a stale lock.
The maintainer accepted retaining that protection.

The original implementation used a nonblocking lock and skipped a competing
cycle. Later rebuild work exposed skipped architecture updates and changed it to
a blocking lock. Current `update.sh` prints `Waiting for repository update lock`,
waits, and runs its complete cycle. See [the lock incident](rebuild-lock-incident.md)
for the diagnosis and observed checks. Do not restore `flock -n` from this chat.

## Release streams, versions, and disappearing upstreams

The agreed default is to query the latest eligible release per selected
architecture rather than rebuilding all versions upstream still hosts. Existing
older packages remain published. A packaging change rebuilds the current query
targets; it does not sweep historical versions and issue new revisions for each.

The maintainer raised maintained major/minor branches, parallel release lines,
and non-semantic versioning. Stream interpretation belongs to the query hook,
not a generic semantic-version selector. One adapter directory follows one
stream; another stream can have its own directory, dependencies, and packaging
logic. There is no automatic stream migration.

The maintainer explicitly rejected forcing unique Debian package names across
streams. A GIMP stream may publish `gimp` and override Debian's older package;
it need not be named `gimp-3.2`. Different streams may use the same package name.
Stream IDs must be unique within a coordinator, while duplicates within an
individual declared binary output set remain invalid. APT's versions and
preferences determine what clients install.

A central package registry was also rejected. Directory membership selects
adapters. Later repository groups place streams beneath `packages/repack/`,
`packages/rebuild/`, and `packages/redistribute/`; each coordinator lists its group.
The configured `RELEASE_STREAM`, rather than the directory's name, is persistent
identity. Architecture-specific output sets and `all` packages were added later;
the original restriction to one common amd64/arm64 output set is obsolete.

Absence from a remote listing cannot establish that a stream has permanently
died. The chosen simple signal is optional per-stream `stale-after-days` plus a
publication timestamp from query. Cadence varies by project, so there is no
universal threshold. Old releases warn every cycle; missing or invalid monitoring
data warns too. Continue checking and publishing. Logs are sufficient for now;
there is no automatic deletion, retirement, migration, or notification delivery.

## Build checksums and dynamic Debian revisions

An early static Codex build revision existed so APT would install changed local
packaging even without a new upstream version. The maintainer wanted that revision
to be automatic and later rejected separate revision-management machinery as too
complicated. Parsing existing package identities and inspecting their control
metadata became the source of revision history. The old `lib/revisions.py` and
separate revision state are not part of the current repack/rebuild design.

The checksum identifies packaging inputs; the highest stored revision establishes
the next available version. For a given queried upstream version, inspect all
declared binary names across streams. Reuse this stream's own latest revision
when its checksum matches; otherwise allocate the highest stored revision plus
one. A completely failed build leaves no artifact and retries the same next
revision. Partial outputs carry enough metadata to resume. A recipe reversion
also gets a new revision because it differs from the stream's latest artifact.

The checksum is embedded in each repacked/rebuilt `.deb` as
`X-Build-Inputs-SHA256`, alongside `X-Publisher-Stream`. The maintainer proposed
using the archive's small control metadata rather than separate checksum files.
Reading control metadata leaves the main payload compressed:

```bash
dpkg-deb --field PACKAGE.deb Version X-Build-Inputs-SHA256 X-Publisher-Stream
```

`revision-env` briefly listed per-adapter environment dependencies, initially
just `MAINTAINER`. The maintainer suggested rendering `control.in` and hashing
the result instead. The discussion clarified that the checksum field would need
to be excluded, and that the publisher revision cannot determine the checksum
that determines that same revision. The upstream version is already a separate
target identity; it was not added as a new checksum input by that discussion.

The final accepted choice was simpler: always include global `MAINTAINER`
directly in the checksum and remove `revision-env` and its parser. Partially
rendered control-file hashing was discussed but not implemented. Do not treat it
as a pending approved refactor.

Current checksum inputs include adapter-relative file paths, contents, executable
bits, declared shared helper files, Dockerfile text, and global `MAINTAINER`.
Private build-dependency selections add their identities and hashes plus worker
implementation inputs. See the current checksum code and
[dependency guide](build-dependencies.md) for those later additions. Timestamps,
adapter directory names, activity settings, architecture selection, unrelated
helpers, and caches do not normally change a recipe's checksum.

Changing comments or docs inside an adapter changes its recipe. General docs
therefore live outside `packages/`. A changed Dockerfile or maintainer can affect
current targets across repack/rebuild streams. A changed repository name affects
signed repository metadata. Remote download digests serve integrity checks and
are not general recipe-change inputs. Unchanged Dockerfile text also does not
detect a moving base image or newly resolved dependency version.

The later redistribute mode is an explicit exception: it preserves upstream
versions and bytes. Its `.state/imports` records are required provenance, not the
rejected revision counters. Never remove them as supposed obsolete checksum
sidecars. See [redistribution](../README.md#unchanged-package-redistribution).

## Extraction and fixed-layout decisions

The maintainer questioned `find_package_root`, archive member checks, and link
checks. The accepted layout policy is strict: within a release stream, required
paths should be known. If upstream changes them, fail and log the missing path
so a maintainer updates the adapter deliberately. Do not automatically unwrap a
new directory or search for plausible executable locations.

GNU tar handles extraction-path protections but also supports legitimate
special files and links. Those entries can be inappropriate for a binary bundle.
For example, extracting an external-pointing symlink can succeed without writing
outside the extraction directory; a later chmod, copy, or read may follow it.
Codex therefore rejects unexpected special entry types and links escaping its
source tree before subsequent permission changes and packaging.

The original local symlink probe showed that distinction: extraction accepted
the symlink while leaving its outside target unchanged. The later operation was
the concern. These are adapter-specific rules, not a claim that tar is broken
or a universal prohibition on links/devices in all packages. GNU tar's ordinary
name exclusions do not directly express this entire packaging policy;
`--check-links` concerns hard-link completeness, not symlink containment.

## Local storage, image tags, and names

The maintainer requested `build/` as the ignored parent for local artifacts,
including `build/local/repo` and `build/local/gnupg` at the time. Scattered root
`repo/` and `gnupg/` test directories and separate ignore entries were unnecessary.
Current manual tests can use group-specific subdirectories under `build/local/`;
production outputs and signing directories follow explicit `.env` paths.

In `docker build -t apt-publisher:local .`, `-t` assigns an image reference. The
custom name is useful for later commands to find the image; it is not needed by
APT and does not name the repository or signing key. The command also needs its
build context, normally `.`. The current setup and Compose intentionally refer
to `private-apt-publisher:local`, so keep those references consistent if changing
the image name. See [image and identity operations](publisher-operations.md).

Several names were discussed independently: Git checkout/repository name, local
image tag, Compose service, APT Origin/Label, distribution codename, output path,
Debian package name, stream identity, and GPG user ID. Changing one does not
automatically change the others. The historical `codex-repo-updater` service name
still exists even though it processes all repack streams.

The source checkout was renamed from `codex-apt-docker` to
`private-apt-docker` during this conversation. Old absolute workstation paths
and image names in chat examples are historical; scripts and documentation
should use the current checkout and configured context rather than embedding
that original machine's directory name.

## Historical implementation checks and their limits

At the stages described in this chat:

- The maintainer reported committing changes and later committing/pushing the
  working changes to GitHub. No commit IDs were recorded in the conversation.
- The global-maintainer checksum simplification passed 61 offline regression
  tests, including rebuilding every stream after a maintainer change.
- The subsequent script cleanup also passed 61 regression tests after missing
  test imports introduced by the test-file split were corrected. Shell syntax
  and whitespace checks passed.
- A real throwaway-key signing/APT test passed. It exposed both fixture streams
  sharing the package name `gimp` at versions `3.2.1-1` and `3.4.0-1`, and APT
  simulated selecting either. These were fixtures, not a real GIMP build.
- A one-time comparison confirmed that the cleanup kept the checksum unchanged
  for identical packaging inputs. No Docker publisher image or production
  deployment was performed by that cleanup task.
- The initial AGENTS/architecture documentation changes passed local-link and
  whitespace checks. They did not run package builds or signing tests.

These are historical observations, not results for the expanded current checkout.
Current runners, test counts, groups, key isolation, and adapters have changed.
Fresh work should record the exact command, revision/working-tree scope, log,
exit status, and validation limitations without claiming old checks passed for
new code. Follow [current verification](../AGENTS.md#verification).

## Package requests and what remains from this conversation

GIMP 3.2 was initially requested here, then explicitly moved to a separate
session. Only preliminary upstream research was done in this chat. A network
permission request to download the public manifest was interrupted; no GIMP
adapter was implemented by that attempt. At that moment, AppImage packaging was
not decided. Later sessions implemented it: read
[current GIMP notes](gimp-3.2.md) and
[investigation history](gimp-3.2-investigation-history.md). The old deferral does
not mean GIMP is still absent or that preliminary AppImage-wrapping suggestions
describe its current native packaging.

Ghostty appeared in the checkout through other work before the first architecture
handoff. Its implementation history and source choices are in
[Ghostty notes](ghostty.md). The many later packages and framework extensions
have their own documents listed in [the index](README.md); this chat is not
evidence that their live deployment or desktop behavior was tested.

The original chat leaves no additional approved implementation task outstanding.
Emergency updates, automatic retention, and external alerts were ideas rather
than commitments. The requested developer handoff is implemented. Future sessions
should inspect current code and working-tree changes, read the relevant guide,
and ask about any new product decision rather than reconstructing this chat.

## Documentation verification on 2026-11-14

This handoff was compared with the current README, architecture, development
rules, configuration example, Compose services, setup, update loop, checksum
implementation, adapter helpers, test runner, and storage/signing history.
The audit verified local links and heading anchors across the affected
documents, parsed new shell examples with `bash -n` without executing them,
and passed documentation whitespace and `git diff --check` checks.

The audit logs are under ignored `build/documentation-audit/`, including
`inventory.log`, `setup.log`, `details.log`, `contracts.log`, and `validation.log`.
They contain public code/configuration examples rather than the operator's `.env`.
No runtime source, adapter, image, repository artifact, key, deployment, or client
installation was changed by this documentation task. Package and signing tests
were not rerun because these are documentation-only edits. Historical test results
above remain separately labeled and do not claim current full-suite success.
