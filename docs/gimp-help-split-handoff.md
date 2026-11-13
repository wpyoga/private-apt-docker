# GIMP help stream split: decisions, implementation, and handoff

Recorded on 2026-11-13. This document preserves the GIMP help separation
conversation so it can be deleted. Current behavior is described in
[GIMP help packaging notes](gimp-help-3.2.md); application behavior and deferred
work are in [GIMP packaging notes](gimp-3.2.md) and
[the application investigation history](gimp-3.2-investigation-history.md).
Those documents and the current code take precedence over historical examples
below. The checkout has evolved since the initial implementation.

## User intent and final decisions

The request was to research offline whether GIMP user manuals should be split
from the application and updated on an independent cadence, then implement the
split. The user expressly prohibited online research or attempts to obtain
missing research data. The work in this conversation used local material only.

The user clarified that updates must be automatic: treat help like other
packages, updating when upstream changes or the packaging checksum changes.
An initial suggestion to keep manually updated source pins was rejected.
There is no requirement for a separate timer, operator-maintained manifest, or
manual release process. The ordinary publisher cycle queries both streams;
each stream selects its own upstream version and resolves its own builds.

Split all declared gimp-help language packages and gimp-help-common together.
Keep libgimp-3.0-doc with the application: it is the API reference generated for
the matching application release, rather than the separately released user manual.
Keep the existing language selection explicit; adding a language is a recipe
change. Do not mix independently selected language/common releases.

## Why separation was chosen

Originally the GIMP adapter combined eight application/developer packages with
33 help packages (32 languages plus common). Manual inputs were pinned to
Debian 3.2.0-3, but outputs were numbered after the application, for example
3.2.6-1. X-Upstream-Version retained the actual manual version.

This coupled unrelated changes in both directions. An application release or
recipe edit rebuilt unchanged manuals. A manual pin change altered the entire
adapter checksum and rebuilt current application targets, including AppImage
processing. New manual package versions could also require unnecessary client
downloads, and retained artifacts consumed additional repository storage.
No byte or timing savings were measured during this conversation.

The application's build called help packaging before returning the complete
output set. A manual download or validation failure could therefore prevent
that architecture's application output set from being stored. Separate streams
use the framework's existing failure isolation.

The dependencies support separation: GIMP suggests manuals; each language has
an exact dependency on common help, rather than the application. The manuals
install below /usr/share/gimp/3.0/help/. That API directory name does not mean
these are GIMP 3.0 application packages. This supports separation within the
supported series, not an assertion of compatibility with arbitrary future GIMP
series. The implementation continues to restrict discovery to 3.2.

## Current implementation and interfaces

The application is under packages/repack/gimp-3.2; the help adapter is under
[packages/repack/gimp-help-3.2](../packages/repack/gimp-help-3.2/config), with
RELEASE_STREAM=gimp-help-3.2. The initial split used packages/gimp-help-3.2;
that old path in chat is historical. Adapter discovery and revision management
remain framework responsibilities; no central registry or separate scheduler
was introduced by the split.

The help query downloads Debian sid's main binary-amd64 Packages.xz, then reads
it with help-metadata.py. Using this index does not make the packages amd64-only:
all selected manuals must have Architecture: all. Clients only need the
publisher repository and their normal Debian dependencies, not sid sources.

Discovery requires every declared name, a consistent supported Debian version,
valid SHA256 values, and the expected Debian pool paths. Ambiguous records,
missing packages, mixed releases, unexpected architectures, or changed layouts
fail visibly. It does not silently select alternative payload structures or
move to 3.4. Current code streams package stanzas to bound memory usage and
accepts dotted Debian revisions such as 3.2.0-3.1; both are later improvements
over the initial split.

Query writes help-assets.json, a generated help-assets manifest, and targets.tsv
under WORKSPACE. The manifest is query output, not an operator-maintained recipe
pin. Targets use requested amd64/arm64 rows even though outputs are all packages.
The build validates and repacks the selected Debian archives, caches completed
help outputs within the workspace for the second architecture, and lets the
framework store them once and include them in both architecture indexes.

The importer verifies download hashes and original package identity, version,
architecture, dependencies, and fixed payload layout. It retains licensing and
safe relative links, rejects unsafe payloads and unexpected maintainer files,
and removes the known legacy migration postinst scripts from de/en/fr/sv.
It rewrites publisher metadata and exact common dependencies and recalculates
Installed-Size from the staged payload excluding DEBIAN. See the packaging notes
for the full validation contract and current shared-helper integration.

## Version transition and rebuild semantics

Existing help packages had application-derived versions, so directly publishing
3.2.0-derived versions could leave APT preferring retained 3.2.6 packages.
The implementation uses epoch 1 to make the independent stream upgradeable.
Debian 3.2.0-3 maps to tracked version 1:3.2.0+deb3, initially published as
1:3.2.0+deb3-1. Debian 3.2.0-3.1 maps to 1:3.2.0+deb3.1-1.
X-Upstream-Version preserves the original Debian version.

An upstream version change creates a new target version. A recipe checksum
change rebuilds the current target at the framework-selected next revision.
An unchanged complete target is reused; incomplete builds resume according to
the framework's stored-artifact rules. The epoch is a lasting versioning choice;
do not remove it casually. Old packages remain stored, with no automatic cleanup
or migration. Global checksum inputs can still rebuild multiple streams; the
split isolates application-specific and manual-specific inputs.

## Verification recorded in this conversation

The original combined adapter run first failed because dpkg-scanpackages was
not on PATH; failure evidence was retained under build/test-run-n5XSHe/.
The next run used the existing project-local tool environment described in
[local-tools.md](local-tools.md), without installing or downloading tools.

The successful historical command selected both adapters:

```bash
export FRAMEWORK_DIR="$PWD"
source build/tools/env.sh
timeout 180 bash tests/run.sh gimp-3.2 gimp-help-3.2
```

Its retained detailed log is build/test-run-8zDndm/regression.log. It reported
18 tests: six help tests passed and 12 application tests were skipped. Help
coverage included all-package import into both indexes, unchanged artifact
reuse, missing/stale upstream Installed-Size replacement and index values,
source-version updates, recipe revisions, tampered downloads, and invalid
architecture/dependency/series rejection. Changed shell syntax and diff
whitespace checks also passed at that point.

The application test class skips if any of patchelf, mksquashfs, or unsquashfs
is unavailable. The conversation did not identify which individual tool was
missing at that time; no stronger claim should be inferred from the skip.
A read-only check on 2026-11-13 now finds all three at /usr/bin. This establishes
current availability, not a new test pass or the historical missing tool.

Current help tests additionally cover memory-bounded index parsing, the final
unterminated stanza, dotted Debian revisions, and a captured index covering all
33 production package names. Those tests were inspected for this handoff but
were not rerun for this documentation-only task. Current coverage descriptions
must not be confused with the six-test historical result above.

## Resuming verification and deployment

Run from the project root, as the host user, and redirect both output streams to
named logs. Use a bounded timeout and inspect logs after completion. Select
bash tests/run.sh gimp-3.2 gimp-help-3.2 for the relevant offline suite; activate
the local tool environment if required. Signing tests are separate and need not
run for ordinary adapter-only changes. Consult the current README and packaging
notes for container and live publisher verification commands.

No online discovery check, live publication, container deployment, or desktop
help browsing was performed in this conversation. A generated query URL is
implementation code, not evidence that its current remote data was fetched.
Desktop browsing and actual client upgrade behavior remain separate integration
checks. Later work may have its own evidence in the current packaging notes;
this document does not supersede it.

For future work, preserve the automatic update policy, the single consistent
language/common family, the application/API-reference boundary, and the epoch.
Check the working tree before editing: unrelated staged and unstaged work was
present during this documentation handoff and was left intact. Keep general
handoff documents outside adapter directories so documentation edits do not
unnecessarily alter package recipe checksums.
