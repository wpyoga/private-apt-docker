# Adapter helpers and documentation: maintenance handoff

This document preserves the decisions, implementation, and verification from the
conversation that moved package notes into `docs/` and refactored seven adapters
around shared publisher operations. It was checked against the working tree on
2026-11-13. The implementation is recorded in commit `40745dc` (`refactor:
implement common helper functions, make package scripts more declarative`).

The repository has evolved since that work. Paths below use today's layout:
these seven adapters now live under `packages/repack/`. Historical test results
below describe the refactor at the time, not verification of all later changes.
For today's complete hook contract use [README](../README.md#query-and-build-hooks)
and for system design use [ARCHITECTURE](../ARCHITECTURE.md).

## Requested outcome and chosen boundaries

The operator wanted repeated package operations moved into `lib/`, with each
package's query and build remaining scripts. The intended improvement was that
a script could state the source, validation, staging, metadata, and build steps
in readable order, with shared mechanics hidden behind small named functions.

Two explicit choices were made during planning:

1. Cover shared build operations and GitHub release mechanics across all seven
   existing adapters: Codex, Ghostty, Zed, USBImager, Laya, GIMP 3.2, and GIMP help
   3.2. Shared ELF inspection was considered and left outside this refactor.
2. Include only declared shared helper files in each recipe checksum. Hashing
   every helper for every stream would rebuild unrelated streams; leaving all
   of `lib/` excluded would miss future packaging changes in shared code.

Upstream release rules, version conversions, architecture mappings, dependency
maps, archive extraction, expected paths, link policy, ELF inspection and
staging remain adapter-owned. No recipe language, callback registry, automatic
pipeline, or central package registry was introduced. Bash coordinates processes
and files, jq handles simple JSON, and Python handles structured Debian metadata.

The work preserved sequential architecture/stream processing, failure isolation,
stored-package revision history and incomplete-build resumption. It did not add
revision counters, checksum sidecars, automatic artifact retirement, or external
notifications. Later infrastructure changes, including locking and repository
groups, are covered by [the repository handoff](repository-and-rebuild-handoff.md).

## Moving package documentation

The two remaining adapter-local Markdown files were moved:

| Original path | Maintained document |
| --- | --- |
| `packages/zed/zed.md` | [Zed notes](zed.md) |
| `packages/gimp-3.2/gimp-3.2.md` | [GIMP 3.2 notes](gimp-3.2.md) |

README and architecture references were updated. Zed references already pointed
at `docs/zed.md`, so the move also fixed those links. Statements that GIMP notes
intentionally belonged beside the adapter and should affect its checksum were
removed. General maintenance notes belong outside `packages/`: adapter filenames,
contents, comments and executable bits are recipe inputs. Removing a document
from an adapter changes its recipe once; future edits in `docs/` do not.

[GIMP help notes](gimp-help-3.2.md) were then added as a separate document. The
README still contained the old combined application/manual build description;
that was replaced by an independent help-stream section and the duplicated
summary at the end of README was removed. GIMP application notes now point to
help notes rather than carrying the full manual packaging explanation.

The help stream owns 32 language packages plus `gimp-help-common`, selects a
consistent 3.2 source release, and publishes architecture-independent manuals
without requiring clients to configure sid. Original Debian versions are retained
in `X-Upstream-Version`; publisher versions use an epoch and `+deb` source revision,
for example `3.2.0-3` becomes `1:3.2.0+deb3-1`. API documentation remains in the
application stream. The help notes now include later support for dotted Debian
revisions and later live-test tooling; those were not part of this conversation.

## Shared Bash packaging operations

Implementation: [package.sh](../lib/adapter/package.sh). Adapters require exported
`FRAMEWORK_DIR` and source it explicitly. They also require their own context such
as `ADAPTER_DIR` and `WORKSPACE`; helpers do not infer paths from script locations.

| Function and arguments | Behavior |
| --- | --- |
| `installed_size PACKAGE_DIR` | Print allocated size in KiB using GNU du, excluding `DEBIAN/`. |
| `build_deb PACKAGE_DIR OUTPUT` | Run `dpkg-deb --build --root-owner-group -Zgzip`. |
| `download_file URL DESTINATION [CURL_ARGUMENTS...]` | Run curl with fail-on-HTTP-error, redirects, silent errors, and three retries. Additional timeout/header arguments are explicit. |
| `verify_download URL DESTINATION SHA256 POLICY [CURL_ARGUMENTS...]` | Validate the digest format, apply cache policy, download to `.part`, verify, then rename to the destination. |
| `check_deb_field ARCHIVE FIELD EXPECTED` | Compare one `dpkg-deb --field` result exactly; report archive, field, expected and actual values on failure. |
| `render_template TEMPLATE OUTPUT [NAME VALUE...]` | Render `@NAME@` placeholders with sed, escaping backslash, ampersand and the replacement delimiter in each supplied value. |
| `render_control TEMPLATE PACKAGE_DIR [NAME VALUE...]` | Create `DEBIAN/`, calculate installed size, supply common publisher placeholders and render adapter-specific pairs. |

### Download policies and failure behavior

- `refresh`: always download even when a destination exists.
- `reuse`: verify an existing destination and return success if it matches;
  return failure on mismatch. Download only if it is absent.
- `repair`: reuse matching bytes; download again if cached bytes mismatch.

New downloads always use `DESTINATION.part`. A curl failure or digest mismatch
returns failure before replacing an existing destination. The partial file can
remain for inspection; subsequent curl invocations write it again. This is not
HTTP range resumption. The destination's parent must already exist.

`download_file` itself does not verify, create parent directories, or perform an
atomic rename. `verify_download` performs those verification/rename steps but
also expects the parent to exist. Neither function imposes an upstream-specific
hostname or archive layout; adapters validate selected URLs and artifacts.

### Metadata and finalization order

`render_control` uses `MAINTAINER`, `PACKAGE_VERSION`, `BUILD_INPUTS_SHA256`, and
`PUBLISHER_STREAM`, and supplies `INSTALLED_SIZE` from the staged tree. Architecture,
package name, dependencies, descriptions, and other package-specific placeholders
are explicit additional pairs. Stage the complete payload before rendering.
Keep synchronization before measurement where required, as in GIMP.

Templates remain external `control.in` files. Decisions to omit empty Depends,
Recommends, or optional whole-field lines stay inside the adapter. The renderer
expects trusted template keys and correctly paired arguments; it does not validate
a complete Debian control schema or reject unresolved placeholders. Replacement
values are intended as single-line values; arbitrary multiline substitutions
are not a supported template interface.

`build_deb` does not calculate Installed-Size, render metadata, validate an output
set, or install artifacts into the repository. The adapter finalizes metadata;
the publisher separately validates the complete output set before storage.

## Imported Debian control metadata

Implementation: [rewrite-control.py](../lib/adapter/rewrite-control.py).

```text
python3 "$FRAMEWORK_DIR/lib/adapter/rewrite-control.py" \
    CONTROL_FILE PACKAGE_VERSION INSTALLED_SIZE [FIELD VALUE ...]
```

The command replaces Version, Installed-Size, Maintainer,
X-Build-Inputs-SHA256 and X-Publisher-Stream. The last three values come from the
exported environment. Additional pairs express adapter decisions, such as
USBImager's renamed Package/Depends/Conflicts/Provides/Section or GIMP help's
X-Upstream-Version and matching common-package dependency.

Field matching is case-insensitive. Replacing a field removes its old continuation
lines too. Unrelated fields and their continuation lines are retained, then the
replacement fields are appended. Callers supply valid paired arguments and
values; this utility does not validate payload layout or execute maintainer
scripts. It changes the control file in place.

The duplicated Ghostty and USBImager Python rewriters were removed. The direct
Ghostty continuation-field regression now exercises the shared implementation.
GIMP help retains package identity, dependency, payload, link and maintainer-file
validation locally; generic field rewriting and size calculation moved out.

Do not use rewriting or `build_deb` for byte-preserving redistribution. Today's
redistribute streams preserve upstream control archives and versions and publish
calculated size/provenance through signed indexes. See the
[build and redistribution handoff](build-and-redistribution-handoff.md).

## Shared GitHub release mechanics

Implementation: [github.sh](../lib/adapter/github.sh).

- `fetch_github_release REPOSITORY RELEASE_FILE` requests GitHub's
  `repos/REPOSITORY/releases/latest`, using the GitHub JSON Accept header and
  `private-apt-publisher` User-Agent. It requires draft/prerelease flags to be
  false and assets to be an array of objects.
- `record_github_release_date RELEASE_FILE DESTINATION` writes an available
  `published_at` value. It neither validates the date nor removes an existing
  destination when the date is missing; normal query workspaces start fresh.
- `select_github_asset RELEASE_FILE ASSET_NAME` matches the exact asset name.
  Zero matches produce no stdout and success. One match must have a
  `sha256:` digest with 64 hexadecimal digits and an HTTPS URL without
  whitespace. The asset object is printed as compact JSON. Duplicate matches,
  malformed digests and invalid URLs fail with an asset-specific error.

The adapter decides whether a missing asset means warning and omitted architecture.
It also owns tag parsing and version transformation. This helper uses latest
release metadata, not paginated release history, arbitrary channel selection or
checksum-sidecar discovery. Later adapters needing other release methods may keep
those implementations local.

## Adoption in the original seven adapters

| Adapter | Shared operations and retained policy |
| --- | --- |
| Codex | GitHub mechanics, refresh downloads, template rendering and build; local `rust-v` tag rules, target triples, tar/link/layout validation and Debian tool wrappers. |
| Ghostty | GitHub mechanics, refresh downloads, field checks, metadata rewrite, size and build; local community version conversion and Trixie executable/desktop/terminfo checks. |
| Zed | GitHub mechanics, refresh downloads, rendering and build; local target names, archive layout, dependency map, ELF baseline and updater wrapper. |
| USBImager | Refresh downloads, field checks, rewrite or rendering and build; local amd64 Debian import and arm64 X11 archive policies, integration and dependency choices. |
| Laya | Repairable verified wheel downloads with its 120-second timeout, rendering and build; local PyPI/wheel metadata, RECORD checks, private Click and three-package staging. |
| GIMP 3.2 | Initially reuse-and-verify AppImage/API-document downloads, rendering and build; local extraction, dependency ownership, native ELF patching and eight-package relationships. |
| GIMP help 3.2 | Reuse-and-verify downloads, size, generic rewrite and build; local Debian index selection, language/common consistency and payload/migration-script policy. |

GIMP now has an adapter-local `download-asset` script for advertised mirrors,
headers and retry behavior. It still uses shared download primitives, and the
upstream mirror policy remains local. This later change supersedes the original
direct `verify_download` calls in its build script. Consult current source and
[GIMP notes](gimp-3.2.md) before changing it.

## Shared helper checksum declarations

Each adapter may provide `helper-inputs`, with one path relative to `lib/` per
line. Blank lines and lines beginning with `#` after trimming are ignored. Declare
all used implementation files, including indirect dependencies; the framework
does not discover shell source or Python import dependencies automatically.

The original declarations are:

| Adapters | Declared paths |
| --- | --- |
| Codex, Zed | `adapter/package.sh`, `adapter/github.sh` |
| Ghostty | `adapter/package.sh`, `adapter/rewrite-control.py`, `adapter/github.sh` |
| USBImager, GIMP help 3.2 | `adapter/package.sh`, `adapter/rewrite-control.py` |
| Laya, GIMP 3.2 | `adapter/package.sh` |

[checksum.py](../lib/checksum.py) includes declared paths, file contents, and
executable permission bits alongside adapter inputs, Dockerfile and MAINTAINER.
It rejects duplicate listed names, missing/non-file targets, absolute paths,
parent traversal and symlinked paths. Declarations themselves are adapter inputs.
Adapters without declarations retain the original behavior of excluding shared
helpers. Nondeclared framework files remain excluded under that base rule.

When a used shared helper changes, only declaring streams get a new recipe
fingerprint. Revision allocation still comes from stored package metadata.
Repeated cycles with unchanged inputs reuse revisions, and old artifacts remain.
Moving code into helpers changes affected adapter recipes once. A helper-file
change affects all streams declaring that file, even if only one function changed.
There is no function-level dependency tracking.

Later source-build support also fingerprints selected private build dependencies
and specific worker implementation files. The base declaration rule is therefore
not the entire current checksum contract for rebuild adapters; see
[build dependencies](build-dependencies.md) and current checksum source.

## Verification evidence and host prerequisites

The first attempt ran with missing host tooling. Publication failed without
`dpkg-scanpackages`, USBImager lacked `readelf`, and Zed/GIMP tests were skipped
without their ELF and SquashFS tools. The operator installed:

```bash
sudo apt update
sudo apt install dpkg-dev binutils patchelf squashfs-tools
```

Those packages provide Debian scanning tools, readelf/objdump/ar, patchelf and
SquashFS tools. Other required host tools were already available. See today's
[test instructions](../README.md#local-testing) and
[optional project-local tools](local-tools.md) for a complete environment setup.

With prerequisites installed, tests exposed stale GIMP artifact counts dating
from the combined manual build: 18 total and 11 for one architecture. They were
corrected to 15 total (seven architecture-specific packages twice plus one
Architecture: all API-document package), and eight for one architecture. Help
packages are tested independently. Tests otherwise retained package content,
dependency, metadata, index-size, architecture and revision checks.

The added [helper tests](../tests/test_adapter_helpers.py) cover replacement
escaping, declared versus unrelated helper changes, executable-bit changes,
invalid declaration paths, symlinks, GitHub asset uniqueness/digests/URLs, cache
policies and preservation of an existing destination on failed verification.
The [publisher tests](../tests/test_publisher.py) exercise a shared helper change
that rebuilds only its declaring stream and reuses that revision on another cycle.
Ghostty covers case-insensitive field replacement and continuation preservation.

The completed original verification was:

| Check | Result/evidence retained under ignored `build/` |
| --- | --- |
| Complete offline regression suite | 139 tests passed in 172.336 seconds; `build/test-run-WxNO4l/regression.log` |
| Offline coordinator | `build/logs/adapter-verified-offline.log` records successful completion. |
| Helper and selective-rebuild checks | Five tests passed; `build/logs/adapter-final-targeted.log`. |
| GIMP follow-up | `build/logs/adapter-gimp-final.log` records success after correcting stale counts. |
| Importer follow-up | `build/logs/adapter-importers-final.log` records success. |
| Shell syntax and whitespace | `build/logs/adapter-syntax.log` and `build/logs/adapter-diff.log`; no errors. |

Earlier failed runs remain diagnostic evidence, including missing-tool failures,
a run that had loaded the old Ghostty script path before it was updated, and
runs that loaded stale GIMP assertions before correction. The clean 139-test run
was performed after those corrections. These logs existed when this handoff was
written, but ignored build output is not a durable source-control dependency.

No signing integration, container build, live publication, production migration,
host package installation by the agent, or desktop/runtime acceptance was done
as part of the refactor. The operator performed the requested prerequisite
installation. Later package/deployment documents may record separate verification.
The historical suite result does not certify later repository changes.

## Continuing without the chat

The documentation moves and helper refactor are complete; this conversation
leaves no pending implementation step. Today, use the current grouped adapter
paths and current runner. Preserve other sessions' working-tree edits: the tree
already contained multiple staged and unstaged documentation updates when this
handoff was written. This document does not stage, commit, revert or deploy them.

When changing a helper, inspect its declaring adapters, keep upstream policy
local, update declarations for indirect dependencies, and exercise affected
adapter tests plus checksum/revision coverage. A cross-adapter change warrants
the complete offline suite. Run host coordinators as the host user, redirect
stdout and stderr to named logs, wait for completion, then inspect the results.

```bash
mkdir -p build/logs
timeout 30m bash tests/run.sh --offline > build/logs/adapter-offline.log 2>&1
```

The runner discovers adapter tests explicitly, including hyphenated names. Avoid
substituting recursive unittest discovery for the complete runner. Signing tests
are separate unless intentionally running the full suite. Rebuild images and
validate live publication separately when deployment is requested. Keep useful
verified sources and failure evidence, and never use cleanup of temporary test
data to remove stored repository packages or signing keys.
