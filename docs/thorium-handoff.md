# Thorium continuation handoff

Prepared on 2026-11-13 so the original conversation can be deleted. This is the
decision and incident history for the Thorium work, with enough context to
continue without the chat. [Thorium packaging notes](thorium.md) contain the
package table, all 12 original archive hashes and sizes, integration details,
and the XZ implementation. Read both documents with the current
[architecture](../ARCHITECTURE.md) and [hook contract](../README.md#query-and-build-hooks).
These documents are outside adapter checksum inputs.

## Current state and evidence boundaries

The checkout has two implemented repack streams:

| Stream | Adapter | amd64 outputs | arm64 outputs |
| --- | --- | --- | --- |
| `thorium-browser` | `packages/repack/thorium-browser/` | Default metapackage plus `-sse3`, `-sse4`, `-avx`, `-avx2` | None |
| `thorium-browser-gz83` | `packages/repack/thorium-browser-gz83/` | Default metapackage plus `-sse3`, `-sse4`, `-avx`, `-avx2` | Native `thorium-browser-gz83` |

The latest implementation uses `ar` and the single-threaded XZ CLI to stream
payloads for both validation and extraction. Compose grants the repack publisher
512 MiB; the XZ decoder has a 384 MiB limit. **There is no successful deployed
memory measurement or final runtime test in this conversation.** Do not convert
the historical static checks into a claim that the final build path passed.

The operator ran update cycles separately and reported failures. The existing
packaging notes also preserve a later November operator listing with
`156.0.8078.80-2` packages and tiny metapackages. That listing is an operator
observation recorded in those notes, not a local rerun or proof of the current
memory budget. The original archive inspection covered M138.0.7204.303 and
M156.0.8078.28; those are not hardcoded release pins.

The user explicitly requested static analysis only after an initial attempt to
use Docker. That instruction remains the verification boundary for this work:
no Docker execution, browser execution, client installation, full package builds,
or regression execution was performed after it. The current request is to
document the work, not to deploy or broaden verification.

## User decisions to preserve

1. **Cover the actual release inventory.** The two original SSE3/SSE4 downloads
   were examples, not the complete set or a request to limit support to them.
   The user authorized moving those downloads and fetching more artifacts.
2. **Offer both upstream source families.** Follow Alex313031 stable browser
   releases and collaborator gz83 releases, including beta-labeled releases.
   Do not silently replace one source with the other.
3. **Use exactly two release streams.** An early implementation used ten stream
   directories, one per tier/default. The user explicitly corrected this:
   `thorium-browser` and `thorium-browser-gz83` must each emit multiple packages.
   The extra stream/test directories were removed. Do not reintroduce them.
4. **Keep explicit CPU package names.** SSE3, SSE4, AVX, and AVX2 are the initial
   amd64 tiers. SSE3 and SSE4 are non-AVX options. The user chose AVX as the
   default for the unqualified metapackages after compatibility alternatives
   were discussed. There is no extra unoptimized "vanilla" package in the
   inspected asset set. No automatic CPU detection was requested.
5. **Include gz83 arm64.** Its unqualified name contains the native browser on
   arm64; it is not an x86 alias there. i386 and AVX512 were investigated but
   are outside the initial publisher outputs.
6. **Allow variants to coexist with one profile directory.** Distinct source
   and CPU packages use distinct payload, launcher, desktop, and metadata paths.
   They share Thorium's normal profile unless the user requests a separate one.
   Keep Chromium's normal single-instance behavior; requests may be forwarded to
   an already running browser. Do not remove profile locks, disable sandboxing,
   or force profile downgrade compatibility. This does not promise installation
   of several versions of the exact same Debian package name at once.
7. **Preserve upstream binaries when possible.** The user preferred unchanged
   upstream `.deb` files if they could meet the requirements. All inspected CPU
   variants instead claim the same Debian name and shared installed paths.
   Thus the agreed coexistence requires repacking. Keep binaries/resources
   intact where possible; do not add a source rebuild without a concrete need.
8. **Keep a detailed handoff.** Preserve findings, decisions, failures, useful
   downloads and logs; do not depend on the chat as the only record.

The grouping has one important consequence: an amd64 target requires all four
CPU assets from the same upstream release. Query selects the latest complete
release for each architecture, warning about incomplete candidates. It never
mixes CPU tiers from different upstream versions. A missing complete set retains
stored packages. All outputs at a selected upstream version share the publisher
revision, and the default metapackage depends on the exact matching AVX version.
A failed late CPU build stores none of that build invocation's output set.

## Investigation and implementation history

### Upstream inventory and Debian identity

The initial stable SSE3/SSE4 downloads were moved into
`build/thorium-investigation/downloads/`. Both hashes matched the published
GitHub asset digests. A subsequent complete API snapshot captured 76 Alex
releases and eight gz83 releases, totaling 613 assets. Both fit in a single
100-entry page at that time; production queries paginate for future growth.

All current Debian assets from the two selected releases were downloaded or
reused and verified: five Alex packages and seven gz83 packages. Combined
archive bytes: 2,451,913,272. All 12 declare `Package: thorium-browser`.
The x86 tier is only in the download filename, not the Debian identity.
Renaming the archive cannot change that identity or its installed paths.

Newer entries in Alex's release list were beta announcements referring users to
gz83, with no Debian assets. Some beta-labeled entries have
`prerelease=false`. The selector checks the source's policy, numeric browser
tag, release title, and actual exact asset set; it does not trust `/latest` or
the prerelease flag alone. Historical generic `_amd64.deb` names and the
Chromium-named asset are not fallback candidates.

### Differences between the actual packages

The original examples were insufficient to establish every layout. Full
inspection found the following, documented with paths in `thorium.md`:

- Alex AVX/AVX2 contain an extra arm64 ClearKey library that SSE3/SSE4 omit.
  The validator explicitly permits that known resource path, rather than
  allowing arbitrary foreign executables.
- Alex i386 contains several x86-64 auxiliary binaries; gz83 i386 contains an
  x86-64 `pak`. This supports keeping i386 outside the current build targets.
- gz83 M156 removes Alex M138's old cron/repository/key provisioning machinery,
  adds locale resources and AppArmor integration, and changes some bundled
  library/tool paths. Do not apply all Alex observations to gz83.
- Both sources ship root-owned mode-4755 `chrome-sandbox` helpers. gz83 also
  provides an AppArmor profile that allows user namespaces. Its upstream
  installation registers a single shared profile attached to the original
  executable path. Our repack rewrites the name, attachment, local include, and
  destination separately for each concrete package.

No upstream browser executable or maintainer script was run during inspection.
ELF header checks established machine/class, not instruction-set suitability,
complete dependency resolution, relocation behavior, or a working GUI sandbox.

### Packaging implementation and early regression failures

The first implementation created ten independent streams, then was consolidated
into the two source streams at the user's request. Grouping also changed the
default alias from an unversioned AVX dependency to an exact matching version.
Each CPU gets a separate extraction and staging directory within the stream
workspace; all outputs use the same final version and publisher stream metadata.

Before the static-only restriction, the first test run failed discovery because
multiple test directories used `test_adapter.py` and collided in unittest's
module cache. Unique test module names fixed that. The next run executed 80
cases and ended with nine failures and 30 errors. Recorded issues were:

- Replacement of `/usr/bin/thorium-shell` followed by replacement of its new
  `thorium-browser...` prefix duplicated CPU suffixes in desktop actions.
  Rewriting was changed to one substitution using a command-name map.
- Three negative test methods read fixture attributes before initializing them.
  Their setup was corrected; after consolidation the metapackage-only skip
  branches were no longer applicable and were removed.
- The same replacement-order concern was reviewed for AppArmor paths. Absolute
  shell-icon paths, localized desktop names, gzip manpage rewriting, and strict
  executable ELF checks received further source review.

Later tests were extended for complete CPU sets, resume behavior, XZ imports,
truncated streams, inherited XZ options, and missing archive members. The final
suite was not run here. The current shared fixture has 16 test methods, inherited
by one test class in each of the two stream directories. Its package builder
explicitly creates XZ fixtures using one compressor worker and level 1. Fixture
packages use real Debian tools; they are not the large upstream browser payloads.

### Deployment failure 1: original decoder path

The operator supplied this gz83 failure after the default metapackage was built:

```text
[thorium-browser-gz83] Building thorium-browser-gz83 thorium-browser-gz83-sse3 thorium-browser-gz83-sse4 thorium-browser-gz83-avx thorium-browser-gz83-avx2 156.0.8078.28-1 (amd64)
.../thorium-browser_156.0.8078.28_SSE3.deb.part: OK
dpkg-deb: error: <decompress> subprocess was killed by signal (Killed)
thorium-browser-gz83-sse3: unexpected end of data
ERROR: [thorium-browser-gz83] Build failed for 156.0.8078.28-1 (amd64)
[thorium-browser-gz83] Update failed; continuing with remaining streams
```

`OK` was the download SHA256 check. It did not establish that decompression could
finish within the container limit. The metapackage build line also did not imply
storage/publication of the whole CPU output set. The framework correctly went
on to the Alex stream. Its arm64 warning was expected because that source has no
configured arm64 target.

Compose initially allowed 256 MiB. Inspection found 256 MiB LZMA2 dictionaries
in Alex M138 payloads, and 8 MiB in gz83 M156 payloads. The first fix raised the
container limit to 512 MiB, limited dpkg to one worker during both validation
and extraction, and added archive/exit-status context to premature-EOF errors.
Those edits received static verification only.

### Deployment failure 2: one dpkg worker still buffered large blocks

The operator then supplied this Alex failure with the new diagnostic:

```text
[thorium-browser] Building thorium-browser thorium-browser-sse3 thorium-browser-sse4 thorium-browser-avx thorium-browser-avx2 138.0.7204.303-1 (amd64)
.../thorium-browser_138.0.7204.303_SSE3.deb.part: OK
dpkg-deb: error: <decompress> subprocess was killed by signal (Killed)
thorium-browser-sse3: Cannot parse Debian payload .../thorium-browser_138.0.7204.303_SSE3.deb: unexpected end of data; dpkg-deb exit status 2
ERROR: [thorium-browser] Build failed for 138.0.7204.303-1 (amd64)
[thorium-browser] Update failed; continuing with remaining streams
```

This showed that the earlier fix was insufficient; it did not prove which
container limit was active or provide a cgroup OOM counter. Static source review
found that dpkg still calls liblzma's multithreaded decoder API with one worker.
The API's buffer allowance is separate from worker count. The Alex SSE3 first
block header specifies 160,034,194 compressed bytes and 783,994,880 uncompressed
bytes, about 748 MiB. A threaded decoder retaining this output block can exceed
512 MiB before counting the 256 MiB dictionary.

The successor fix uses the `payload-tar` reader in both adapters. It checks exact
ar membership/order, streams `data.tar.xz` through XZ's true one-thread CLI
decoder, clears inherited `XZ_DEFAULTS`/`XZ_OPT`, and caps decoder memory at
384 MiB. dpkg now handles only small control archives. Tar handles validated
payload extraction with `--no-same-owner --same-permissions`, preserving the
sandbox mode. Validation drains remaining reader output before waiting so tar
padding cannot block the producer or hide the final XZ status/checksum result.

The reader requires `debian-binary`, `control.tar.xz`, `data.tar.xz` in order.
All 12 downloaded archives matched that layout. A changed archive format must
fail clearly instead of being guessed. The existing image already supplies
`ar` through binutils, plus xz and GNU tar; no Dockerfile dependency was added.
The latest reader's full decompression, real build, peak memory, and deployed
success were not verified here. A decoder memory cap is not a total cgroup cap.

## Current implementation map

Paths below are relative to each adapter directory under `packages/repack/`.
The two copies are intentionally self-contained so upstream assumptions remain
out of publisher helpers and participate in each stream's recipe checksum.

| File | Responsibility |
| --- | --- |
| `config` | Stream identity and per-architecture binary output names |
| `settings` | Upstream repository and whether beta releases are allowed |
| `query` | Fetch and validate paginated release JSON with curl/jq |
| `select-release.py` | Select exact complete asset sets and write workspace metadata |
| `build` | Build default alias or verify, validate, extract, stage, and package each output |
| `payload-tar` | Check fixed ar layout and emit the decoded payload tar stream with bounded XZ memory |
| `stage.py` | Validate paths/types/ELFs/sandbox metadata; relocate payload and rewrite desktop/AppArmor/manpage integration |
| `alias.in`, `control.in` | Default launcher and exact-version AVX metapackage metadata |
| `launcher.in` | Shared-profile browser launch, flags-file handling, class and desktop identity |
| `postinst.in`, `prerm.in`, `postrm.in` | Per-package alternatives, desktop-cache and AppArmor lifecycle |
| `copyright.in` | Source and embedded-license pointers; upstream license resources are retained |
| `helper-inputs` | Fingerprint `adapter/package.sh` and `adapter/rewrite-control.py` from `lib/` |

Normal framework context is required: `FRAMEWORK_DIR`, `ADAPTER_DIR`, `WORKSPACE`,
`PUBLISHER_STREAM`, `ARCHES`, and the build metadata supplied by the publisher.
Query writes `targets.tsv` as `VERSION<TAB>ARCH` rows and `assets.json` keyed by
architecture, with a `version`, `published_at`, and an `assets` map keyed by
binary package name. An asset has `name`, `url`, and `sha256`. The default amd64
metapackage has no upstream asset of its own. Build checks the selected upstream
version against its assigned final version and expects upstream control version
`VERSION-1`; upstream Debian revision changes require explicit review.

Only `config` and `settings` should differ between the current two common recipe
copies. Change both when editing common behavior. The existing framework handles
output-set validation, revision allocation, immutable storage, signing, and
indexes. Do not add a CPU registry, revision counter, checksum sidecar, automatic
retirement, stored-package cleanup, or notification mechanism for this work.

The framework has since gained `packages/redistribute/` and `.state/imports`
provenance. An earlier chat explanation that unchanged imports were impossible
because of embedded publisher fields is now historical. Unchanged Thorium CPU
artifacts still cannot supply the chosen distinct package identities/paths;
that is why these adapters remain in `packages/repack/`.

## Evidence to retain

The durable package notes contain every original archive hash/size, upstream
source links, and findings; deleting ignored build data would remove the raw
evidence and reusable downloads. Keep useful sources and failure evidence while
pending issues remain. Do not put large archives, keys, or operator `.env` data
into documentation or fixtures.

| Location | Meaning and verification boundary |
| --- | --- |
| `build/thorium-investigation/downloads/` | All 12 verified upstream `.deb` archives, including out-of-scope AVX512/i386 |
| `build/thorium-investigation/releases/alex.json`, `gz83.json` | Original complete release API snapshots |
| `build/thorium-investigation/releases/all-assets.tsv`, `selected-debs.json` | Full asset inventory and selected Debian inputs |
| `build/thorium-investigation/inspection/summary.json` | All package fields, script hashes, and ELF header results |
| `build/thorium-investigation/inspection/ASSET_NAME_WITHOUT_DEB/` | Extracted control/text evidence and complete `payload.json` |
| `build/thorium-investigation/logs/download-batch.log` and per-archive `.download.log` files | Successful source download/hash verification |
| `build/thorium-investigation/logs/inspection-all-elf.log` | Completed static inspection of every regular payload file's ELF header |
| `build/thorium-implementation/logs/upstream-static-validation.log` | Nine supported payloads accepted by the earlier validator; predates the final streaming reader |
| `build/test-run-QTK1nm/regression.log` | First test discovery failure |
| `build/test-run-4Grdko/regression.log` | 80-test run with nine failures and 30 errors; not a passing suite |
| `build/thorium-implementation/logs/final-static-checks.log` | Superseded ten-stream layout's source checks |
| `build/thorium-implementation/logs/two-stream-static-checks.log` | Two-stream consolidation's syntax/config/output-list checks |
| `build/thorium-implementation/logs/xz-memory-static-checks.log` | First, insufficient one-worker fix's static checks |
| `build/thorium-implementation/logs/xz-streaming-static-checks.log` | Final reader's static checks; explicitly no decompression, builds or memory benchmark |
| `build/thorium-implementation/logs/xz-archive-members.log` | All 12 archives' ar membership, inspected without decompression |
| `build/thorium-implementation/logs/docker-info.log` | Initial Docker access denied; not a container test result |

The download and inspection helper scripts under the investigation directory are
temporary investigation tooling. They are not production hooks. Logs and older
helper scripts can contain paths from before the repack-group move; adapt those
paths deliberately before reusing a command. The original twelve downloads were
reused throughout the work. No production keys or stored packages were used as
test fixtures. Retain current failure-workspace evidence according to the
framework's present policy in `ARCHITECTURE.md`; do not assume an old `/tmp`
workspace from a pasted log still exists after a container replacement.

## Ordered continuation work

1. Read current instructions, inspect the working tree, and preserve unrelated
   staged/unstaged work. Consult these notes and the actual adapter code before
   assuming that old command paths or verification claims are current.
2. Continue with static checks while that restriction applies. The final decoder
   syntax and duplicate-source checks are evidence of source consistency only.
   No container or browser test should be inferred from them.
3. Once package-building verification is authorized, run
   `bash tests/run.sh thorium-browser thorium-browser-gz83` from the project root
   in a bounded batch with a named log. Review failures after completion. The
   final suite needs execution; it must not be advertised as passing based on
   the corrected source or the earlier failed run. Signing tests are unnecessary
   unless signing changes or the full suite is intentionally selected.
4. Verify the new decoder and extraction path against the retained real sources.
   Start with Alex SSE3 because it has the large single block, then the other
   supported artifacts. Check output sizes, complete output sets, root-owned
   setuid sandbox metadata, independent paths, shared stream/revision fields,
   exact AVX dependencies, and Installed-Size in both `.deb` and Packages index.
   Do not execute target browser binaries to perform these package checks.
5. When runtime verification is authorized, measure peak memory for the whole
   validation/extraction/build process under the actual 512 MiB cgroup budget.
   Keep failure logs and verified sources; remove obsolete staging copies only
   after their diagnostic value is exhausted. Do not simply keep raising the
   limit based on a single killed-child message.
6. Validate Debian Trixie dependencies/SONAMEs and real coinstallation/removal in
   isolation. Check AppArmor profile load/unload and preservation of setuid
   permissions; an `apparmor_parser` error is currently tolerated by the script,
   so a successful install alone does not prove a loaded profile. Use disposable
   profiles for browser smoke tests, then assess shared-profile forwarding and
   cross-version compatibility. Do not use production browser profiles or keys.
7. Deployment is separate. Adapters are copied into the image, so a restart alone
   does not apply new code or memory limits. Rebuild and recreate the repack
   service when explicitly undertaking that deployment. The current Compose
   file also contains rebuild and redistribution services, so target the repack
   service rather than copying an older unqualified all-service command.

Example future deployment command, not executed by this handoff:

```sh
docker compose up -d --build --force-recreate codex-repo-updater
```

For a future OOM diagnosis, inspect the actual running container, not just YAML:

```sh
docker inspect --format '{{.HostConfig.Memory}} {{.State.OOMKilled}}' \
    "$(docker compose ps -q codex-repo-updater)"
docker compose exec -T codex-repo-updater cat /sys/fs/cgroup/memory.max
docker compose exec -T codex-repo-updater cat /sys/fs/cgroup/memory.events
```

The intended 512 MiB limit is 536870912 bytes. On cgroup v2, `memory.events`
provides OOM counters; collect before/after values for the incident. A false
container-level `OOMKilled` flag does not exclude an OOM-killed child while the
publisher itself stays alive. Kernel/cgroup information was not supplied with
either original failure, so those incidents remain memory-pressure diagnoses
supported by the compression layout and decoder source, not confirmed OOM audits.

Future fixture runs and deployment should continue to finish one stream before
the next, retain complete stored artifacts, and preserve old by-hash indexes.
The user's static-only constraint is a deliberate outstanding verification limit,
not permission to declare the final implementation production-validated.
