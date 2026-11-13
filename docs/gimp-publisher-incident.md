# GIMP publisher failures, verification, and mirror/version decisions

Prepared on 2026-11-13 so the original conversation can be deleted. This records
what failed, what changed, how the fixes were verified on 2026-10-28/29, and the
later discussion about simplifying downloads. It distinguishes observations,
likely causes, implemented behavior, and recommendations that remain unimplemented.

Read this with the [application packaging notes](gimp-3.2.md),
[help packaging notes](gimp-help-3.2.md), current
[architecture](../ARCHITECTURE.md), and [hook contract](../README.md#query-and-build-hooks).
The application notes retain the separate native packaging and deferred
TIFF-thumbnail investigation; this incident did not resolve those runtime topics.

## Current state and important changes since the incident

- Both adapters now live under `packages/repack/`: `gimp-3.2` for the application
  and API documentation, and `gimp-help-3.2` for the independent user manuals.
  The older conversation and retained logs use `packages/gimp-3.2` and
  `packages/gimp-help-3.2`; those were the paths at the time.
- The help query streams Debian's package index and accepts dotted Debian
  revisions, including the observed `3.2.0-3.1`.
- The application downloader still implements explicit advertised-mirror
  fallback. Removing it in favor of the upstream redirector was recommended
  later, but was not implemented or newly tested in this conversation.
- Compose currently grants the repack publisher **512 MiB** and 128 processes.
  The later increase supports Thorium's XZ decoder; see the
  [Thorium handoff](thorium-handoff.md). The GIMP live test still explicitly uses
  **256 MiB** and 128 processes, the production settings during this incident.
- Signing/socket isolation and repository grouping evolved afterward. The
  historical GIMP test does not establish compatibility with every later
  framework change. Current operational requirements are documented in the
  [storage/signing guide](storage-and-signing.md).

No adapter or framework behavior was changed while preparing this document.
The operator reported that the fixes worked after deployment. That report is
separate from the isolated test results below.

## Failures and diagnosis

### 1. Interrupted GIMP downloads

The first operator log reached the GIMP `3.2.6-3` amd64 build, then reported:

```text
curl: (56) Recv failure: Connection reset by peer
ERROR: [gimp-3.2] Build failed for 3.2.6-3 (amd64)
```

A later attempt produced four curl error-56 messages, including
`SSL_ERROR_SYSCALL` and OpenSSL `unexpected eof while reading`, before failing
that stream. These indicate an interrupted transfer. They do not identify
whether the originating server, a mirror, a proxy, or another network component
caused the interruption. No controlled reproduction established the precise TLS
cause; describing a particular mirror as conclusively broken would overstate
the evidence.

The shared downloader already used `--retry 3`, but curl's default retry
conditions did not cover this receive error. Enabling `--retry-all-errors`
allowed retries. Four subsequent errors were consistent with one initial
attempt plus three retries all failing; enabling retries did not prove that a
live transfer would succeed or that each attempt selected a different mirror.

Header inspection from the test image showed `download.gimp.org` issuing a 302
redirect, advertising alternative mirrors through `Link` headers, and selecting
`mirror.freedif.org` in that observation. The amd64 AppImage then returned HTTP
200 with a Content-Length of 243,476,984 bytes. This was a point-in-time routing
observation, not a hardcoded mirror choice or an availability guarantee.

The application fix added retries for receive errors and explicit fallback to
advertised mirrors. Both real AppImages subsequently downloaded and passed their
published SHA256 checks in the isolated live tests. The original TLS EOF did not
recur there. Injected failures separately verified retry and fallback behavior.

### 2. Help query killed under the memory limit

The original help query ended with:

```text
query: line 9: ... Killed python3 "$ADAPTER_DIR/help-metadata.py" query
```

It decompressed the entire Debian sid `Packages.xz` index into one string, then
split that string into a list of package records. The index and its copies could
exceed the container's 256 MiB budget. This was the likely reason for the kill;
no retained host/kernel OOM report confirmed that original process's cause.

`package_records()` in the help metadata helper now iterates through the XZ
stream and yields one stanza at a time. The selector retains only the requested
help records. It also handles a final stanza without a terminating blank line.

The regression creates an index exceeding 200 MiB after decompression and runs
the query with a 128 MiB address-space limit (`RLIMIT_AS`). That verifies the
streaming improvement. A process address-space limit is a different constraint
from Docker's cgroup limit; the later container runs tested the latter as well.

### 3. All 33 help packages reported missing

After streaming discovery was introduced, the query stopped being killed but
reported every declared help package as missing. Downloading the actual sid
index reproduced this failure with query exit status 1.

All 33 packages were present at **`3.2.0-3.1`**. The selection expression was:

```text
3\.2\.\d+-[0-9]+
```

It allowed only integer Debian revisions, silently skipped every `-3.1` record,
and then reported the selected set as incomplete. This was a selection bug, not
proof that Debian lacked the manuals or that a mirror was incompletely synced.

The corrected expression is:

```text
3\.2\.\d+-[0-9A-Za-z.+~]+
```

This preserves the upstream `3.2.x` stream restriction while allowing Debian
revision characters. Architecture `all`, checksums, fixed pool filenames, the
complete declared name set, and a consistent version remain mandatory.

## Debian version rules and our version mapping

[Debian Policy, Version](https://www.debian.org/doc/debian-policy/ch-controlfields.html#version)
defines `[epoch:]upstream_version[-debian_revision]`:

| Component | Rules relevant here |
| --- | --- |
| `epoch` | Optional unsigned integer; omitted means zero |
| `upstream_version` | Mandatory; alphanumerics and `.`, `+`, `-`, `~`; should begin with a digit |
| `debian_revision` | Optional; alphanumerics and `+`, `.`, `~` |

The last hyphen separates the Debian revision. Upstream hyphens require a Debian
revision to be present. A revision ending in a period and number conventionally
identifies a source non-maintainer upload. Binary non-maintainer uploads commonly
use `+bNUMBER`; stable updates and backports use other valid revision suffixes.

The following examples were checked with `dpkg --validate-version`:

```text
3.2.0-3.1
1:3.2.0+deb3.1-1
3.2.0-3+deb13u1
3.2.0-3~bpo13+1
3.2.0-3+b1
```

The help adapter intentionally selects a narrower subset than every possible
Debian version: stable upstream `3.2.NUMBER` followed by a Debian revision. It
does not automatically follow `3.4`, prerelease upstream versions, or upstream
epoch changes. No further character expansion was needed for the observed
revision problem after the fix. The framework also invokes
`dpkg --validate-version` on selected target versions; stream policy and Debian
syntax validation are separate responsibilities.

For this repack stream, Debian `3.2.0-3.1` becomes tracked version
`1:3.2.0+deb3.1`; the publisher appends its own revision, initially producing
`1:3.2.0+deb3.1-1`. The epoch upgrades older manuals that had been numbered after
the GIMP application. `X-Upstream-Version` preserves `3.2.0-3.1`, and each language
package depends on the exact repackaged `gimp-help-common` version. The test
checks upgrade ordering from `1:3.2.0+deb3-1` using `dpkg --compare-versions`.

The operator's failed application version `3.2.6-3` and the isolated test's
`3.2.6-1` differ because publisher revisions derive from each repository's
stored history. The fresh test repository began at revision 1. This was not an
instruction to downgrade or reset production revision history.

## Implemented download behavior

The application's build hook calls
[`download-asset`](../packages/repack/gimp-3.2/download-asset) for both AppImages
and the matching generated API documentation archive. It:

1. Validates the expected SHA256. An existing complete destination is reused only
   after verification; a corrupt cached destination fails the `reuse` policy.
2. Starts with the official `download.gimp.org` URL and follows redirects.
3. Uses the shared downloader's three retries plus `--retry-all-errors`, a
   30-second connection timeout, and a low-speed threshold of 1,024 bytes/second
   over 60 seconds. These are connection/stall controls, not a total-transfer
   deadline; the live coordinator provides an overall timeout.
4. Writes to `DESTINATION.part`, logs the effective endpoint, and records response
   headers in `DESTINATION.headers`. Only a matching digest permits renaming the
   partial file to the complete destination.
5. After primary failure, copies the headers to `DESTINATION.headers.failed`,
   extracts distinct HTTPS `Link` targets advertising `rel=duplicate`, and tries
   up to three in advertised order. Each attempt uses the same retry and digest
   requirements. Failed verification never promotes the file to the cache.
6. Returns failure if no attempted source provides the expected bytes. The
   framework keeps stored packages and continues other streams.

There can be up to four URLs, each with one attempt and three curl retries;
there is no guarantee of a different effective endpoint on every retry. The
helper applies to the application assets, not every query/download in the project.
For example, the help query still invokes its own `curl --retry 3` for the index.

## Upstream mirror services and the proposed simplification

The service already used by the adapter, `https://download.gimp.org/`, performs
automatic mirror selection. [GIMP's mirror administration guide](https://developer.gimp.org/core/maintainer/accounts/mirror/)
says it uses Mirrorbits, geographic routing, health checks, and automatic removal
of down mirrors. An older
[GIMP mirror policy announcement](https://www.gimp.org/news/2021/10/06/official-mirror-policy/)
also describes automatic rotation through redirects. Legacy `/mirror/` URLs do
not establish a need to change the current official artifact URLs.

The comment naming MirrorBrain in our downloader is historical terminology;
GIMP's current documented infrastructure is Mirrorbits. The actual helper parses
HTTP `Link` headers and does not invoke either service's software directly.

[Mirrorbits](https://github.com/videolabs/mirrorbits) advertises per-file mirror
inventories, size/checksum controls, and health monitoring. These let a redirector
avoid unavailable or incomplete copies. Health information can lag a failure;
selection also cannot guarantee that a particular client's subsequent transfer
will complete. Once redirected, the client downloads from the mirror directly.
A retry through the original URL may select the same mirror again.

For repository synchronization, Debian's
[ftpsync guidance](https://www.debian.org/mirror/ftpmirror.en.html) uses controlled
publication order, while [APT by-hash](https://manpages.debian.org/trixie/apt/sources.list.5.en.html)
fetches indexes through content-addressed URLs to avoid metadata races. By-hash
protects index consistency; it does not repair an interrupted AppImage transfer.
Our publisher already retains old by-hash indexes for clients.

The later recommendation was to simplify downloads by relying on GIMP's official
redirector, retaining bounded retries, timeouts, digest verification, and the
normal next-cycle retry after failure. That would remove client-side mirror-list
parsing at the cost of losing explicit immediate alternate-mirror selection.
**This recommendation remains unimplemented.** The successful live results below
were obtained with custom fallback present; they do not verify its removal.
No request to change that behavior followed the discussion before this
documentation handoff.

If that simplification is undertaken, remove the header-list fallback and its
mirror-selection fixtures, retain real-curl recovery/exhaustion/integrity tests,
update both packaging guides, and rerun appropriate adapter/live checks. Do not
weaken checksums or mix manual versions to tolerate an incomplete mirror sync.

## Why the original tests passed

The offline publisher fixtures replace curl with a program that copies a local
file. They exercise packaging and integrity rejection, but cannot reveal TLS
failures, real curl retry behavior, upstream routing, or network availability.

Help import fixtures also reduce the configuration to three synthetic packages
and generate a matching index. Their versions originally used integer revisions
such as `3.2.0-3` and `3.2.0-4`. Consequently, the fixtures satisfied the same
assumption as the faulty selector and never tested Debian's dotted revision.
The memory regression initially retained that simplified metadata, so passing
it established bounded memory use without establishing live release selection.

The earlier statement that both production issues were fixed based only on
those passing tests was too strong. The subsequent tests added independent
metadata and actual curl behavior, then exercised the complete upstream sets in
limited containers. Passing offline tests remains distinct from a live build.

## Added coverage and historical results

- `tests/gimp-help-3.2/test_gimp_help.py`: large streamed index under a process
  memory limit; a final unterminated record; non-maintainer revision import and
  upgrade ordering; dependencies rewritten to the new common version; and the
  production query/configuration against all 33 captured Debian records.
- `tests/gimp-help-3.2/fixtures/Packages`: unmodified help-package stanzas captured
  from Debian sid on 2026-10-28, with provenance in its adjacent README. This is
  a tracked fixture; later upstream changes do not silently alter the test.
- `tests/gimp-3.2/test_download.py`, `DownloadTests`: real curl against a local
  HTTP server injecting TCP resets. Covers recovery, all four attempts failing,
  and a successful transfer whose bytes still fail the checksum. This is not a
  TLS EOF reproducer; it exercises receive-error handling without live upstream.
- `MirrorTests` in that file: controlled curl responses test primary failure,
  advertised-mirror order/deduplication, a corrupt first mirror, and exhaustion
  after three alternatives. These fixtures test fallback policy rather than
  real mirror uptime.

The final selected adapter suites passed **27 tests in 59.319 seconds**. Earlier
19- and 24-test results reflected smaller suites, not extra evidence for the
final behavior. Shell syntax and Git whitespace checks also passed.

### Live builds with the production limits of the time

The host-side coordinator built the publisher image and ran a non-root container
with `--init`, host UID/GID, `--memory 256m`, `--pids-limit 128`, all capabilities
dropped, and `no-new-privileges`. It used only isolated `build/` storage and a
throwaway signing key. It did not install packages on the host, use operator
keys, or modify/start the deployed service.

The inspected successful build container had Memory=268,435,456 bytes,
MemorySwap=536,870,912 bytes, PidsLimit=128, exit status 0, and OOMKilled=false.
The swap setting was Docker's effective configuration, not an explicitly
swap-disabled test. Both successful-build and repeat-run cgroup records reported
zero OOM kills. The build's peak process count was 11.

| Recorded result | Value |
| --- | --- |
| Application upstream/version in the fresh test repository | `3.2.6-1` |
| Help upstream/version in that repository | `3.2.0-3.1` / `1:3.2.0+deb3.1-1` |
| Application ELF objects validated | 260 amd64; 214 arm64 |
| Application outputs | Eight per architecture; seven architecture-specific plus one `all` API documentation package |
| Help outputs | 33 architecture-independent packages, stored once |
| Total stored packages | 48: 14 architecture-specific application packages + one API documentation package + 33 manuals |
| Published entries | 41 in each architecture index |
| Build-run `memory.peak` | 272,949,248 bytes |
| Repeat-run `memory.peak` | 268,816,384 bytes |

The raw memory peaks slightly exceed the configured hard-limit value. They are
reported as recorded cgroup accounting data; do not replace them with a claim
that observed peak accounting stayed below 256 MiB. `memory.events` showed limit
reclaim activity (`max`) but `oom` and `oom_kill` were zero in the saved successful
records. These measurements do not establish that all future releases fit that
budget or that no swap was used.

All 33 real help packages downloaded, validated, and built in the initial
limited run. The final application build reused verified amd64 downloads, built
both application architectures with the final recipe, reused the stored help
packages, generated both indexes, and verified the signed InRelease file.
The repeat check ran the actual `update.sh` runner with only these two adapters
and checked every stored `.deb` against a pre-run checksum manifest. All 48
package byte sequences remained unchanged. The final signature was also verified.

The checker compared Installed-Size with the final staged trees excluding
`DEBIAN/`, checked positive sizes and their published index values, compared
dependencies and publisher metadata, checked archive ownership, and inspected
container settings and OOM status. It did not execute arm64 binaries or establish
GUI, plug-in, codec, or help-browser behavior. Separate runtime-test boundaries
remain in the application packaging notes.

### Test-coordinator failures corrected during the investigation

These were test infrastructure mistakes, not additional production adapter bugs:

1. The first worker omitted the empty `repo/pool/` directory normally created by
   production before storage. The amd64 outputs built, but storage failed with
   `find: '/test/repo/pool': No such file or directory`. The worker now creates it.
2. Editing the bind-mounted worker while Bash was still reading it caused a
   later syntax error in that run. The host coordinator now copies the worker
   into the context before launching the container. Do not edit that active copy.
3. The first metadata checker treated Debian field names as case-sensitive.
   `X-Build-Inputs-SHA256` in control metadata appeared as
   `X-Build-Inputs-Sha256` after index generation. The checker now normalizes
   names to lowercase. The underlying build and publication had succeeded.
4. Real-curl local-server tests initially failed because the agent sandbox denied
   socket creation. The tests passed with the required local-socket permission;
   that restriction was separate from application networking.

Old logs retain these failures. Their presence does not negate the later
successful builds, and a checker/coordinator failure must not be attributed to
production without examining its actual cause.

## Evidence retained outside Git

The following paths were inspected while writing this document. They are local,
ignored build evidence, not portable prerequisites or current upstream pins.
The essential findings and numbers are preserved above even if those files are
later cleaned up.

| Local path | Contents |
| --- | --- |
| `build/gimp-failure-audit/live-query.log` | Real index reproducing the all-packages-missing selection failure |
| `build/gimp-failure-audit/Packages.xz` and `index-records.log` | Downloaded index and extracted help stanzas |
| `build/gimp-failure-audit/gimp-download-headers.log` | Redirect, advertised alternatives, effective endpoint and HTTP response |
| `build/gimp-failure-audit/final-regression.log` | Coordinator's final selected-suite result |
| `build/test-run-Wl1stW/regression.log` | Detailed 27-test result |
| `build/gimp-failure-audit/repeat-live-test.log` | Successful image, publisher, and verification coordinator stages |
| `build/gimp-production-limits/first-run/` | Initial test-directory and worker-read failures |
| `build/gimp-production-limits/successful-build/` | Final application build log, container inspection, cgroup statistics and corrected checker result |
| `build/gimp-production-limits/publisher.log` | Repeat cycle, signatures and stored-package checksum checks |
| `build/gimp-production-limits/container.json` | Repeat container's actual settings and exit state |
| `build/gimp-production-limits/verification.log`, `memory.events`, `memory.peak`, `pids.peak` | Final metadata/resource check evidence |
| `build/gimp-production-limits/final-signature.log` | Successful final InRelease signature verification |
| `build/gimp-production-limits/before-resume.sha256` | Test-only package checksum manifest for the repeat check |

The checksum manifest is a test assertion, not a revision counter or production
checksum sidecar. The context's `repo/` contains isolated stored test packages;
`gnupg/` contains only its throwaway key. Never copy a real operator key there or
commit any keyring. Verified upstream downloads and staged trees remain in
`workspaces/`. Redundant completed help-cache and help-output copies were removed
after verification; stored test packages, useful sources, stages and failure logs
were preserved. Do not blindly delete stored repositories or keyrings as cleanup.

## Continuing without the conversation

For offline verification from the project root:

```bash
bash tests/run.sh gimp-help-3.2 gimp-3.2
```

The selected suites use real Debian tools and no upstream network, but the curl
reset tests need permission to open a loopback socket. Use the README's current
host-tool requirements. Signing tests are separate unless intentionally running
the full suite or changing signing behavior.

The live entry point remains:

```bash
bash tests/gimp-3.2/test-publisher.sh
```

It defaults to both architectures. `ARCHES=amd64` restricts selection;
`GIMP_PUBLISHER_CONTEXT` can reuse a host-owned context beneath this checkout's
`build/`. It builds image `private-apt-gimp-publisher-test:local`, retains named
logs, uses a 20-minute image-build limit, 90-minute publisher limit, and five-minute
verification limit, and inspects/removes its stopped container. Failed or timed-out
runs retain their workspaces for diagnosis.

Before a new live run, inspect the coordinator and worker against today's
framework. The coordinator still hardcodes 256 MiB and the checker asserts that
value, while current Compose uses 512 MiB. It overrides the image entrypoint and
runs its own GPG setup; it does not duplicate today's private `/run/user/UID`
tmpfs/agent lifecycle. The original success must not be presented as a new test
of those later signing changes. If the goal is exact current-production parity,
align those test settings deliberately and update the checker before rerunning.
No such new live run was performed for this documentation task.

Reusing a completed context skips matching stored outputs. A failed build with
an extraction or staging tree can intentionally refuse reuse: inspect the error,
preserve evidence and verified downloads, and remove only confirmed superseded
temporary trees before retrying. Keep stored packages and keys. A retained
historical context can also outgrow the checker's fixed 41-entry/current-stage
assumptions when new versions accumulate; use a fresh isolated context or update
the test's expectations for that purpose rather than removing package history.

To diagnose a new failure, identify the stream and stage first. For download
errors, preserve the exact URL, redirect/effective endpoint, response headers,
transfer error, expected checksum, and verification result. Do not infer missing
releases from a failed download. For help selection, inspect actual package
versions and the full declared set before changing the stream restriction. For
a killed process, collect container limits, exit/OOM state and cgroup events;
a shell `Killed` message alone does not prove OOM. For a checker failure, compare
its assumption with package/index semantics before rebuilding valid artifacts.

Applying future code changes requires rebuilding and recreating the repack
publisher, since adapters are copied into the image. The current README owns the
exact deployment command; the service remains `codex-repo-updater`. The earlier
operator confirmation establishes that the incident fixes worked at the time,
not that any subsequently proposed simplification has been deployed.
