# Rebuild lock incident and maintenance handoff

This records the rebuild failure conversation from 2026-11-01, including the
requested scope, diagnosis, completed fix, evidence, and follow-up work. The
repository and retained logs were reviewed for this handoff on 2026-11-13.
It is intended to replace the need to retain that conversation.

## Reported symptoms

The operator started services and saw arm64 begin an xfce4-terminal rebuild,
while amd64 immediately reported:

```text
rebuild-arm64-1 | [xfce4-terminal] Querying upstream
rebuild-amd64-1 | Update already running
rebuild-amd64-1 | Update cycle complete
```

The arm64 job downloaded Debian Trixie's `xfce4-terminal` source version
`1.1.4-1`, then attempted local package version `1.1.4-1+local-2`. Importing
`000-shift-enter.patch` succeeded, but applying it failed:

- `terminal-preferences-dialog.c`: the first hunk applied with an offset;
  the second hunk failed.
- `terminal-preferences.c`: the first hunk applied with an offset;
  the second and third hunks failed.
- `terminal-preferences.h`: its hunk failed.
- `terminal-widget.c`: its hunk applied with an offset.

Quilt reported that the patch did not apply. The build hook exited before
compilation, the stream failed, and the framework continued to publication.
The supplied log ended the arm64 cycle with:

```text
[xfce4-terminal] Update failed; continuing with remaining streams
Published signed repository: trixie
Update cycle failed; retry next interval
```

Publication of existing packages did not mean that the requested rebuild had
succeeded. Previously published packages remained available.

The repack publisher was also active in the supplied log. It used separate
repository storage and was able to continue independently of the rebuild lock.

## Scope requested by the operator

The initial proposed work included both the patch and locking. The operator
redirected the investigation to this question: if arm64 fails, why does amd64
never start? After the explanation, the explicit instruction was to fix that
first. The completed work in this conversation therefore changed repository
locking, its regression coverage, and documentation. It did not repair or
revalidate the Shift+Enter patch, rebuild container images, or deploy services.

An attempted extraction of cached source for patch investigation was interrupted
at the approval request before any successful extraction was reported. No patch
repair or successful source build should be inferred from that attempt.

## Root cause: skipping a busy lock looked like success

Both architecture services mount `REBUILD_REPO_DIR` as `/repo`, so they use the
same `/repo/.state/update.lock`. Each service selects one build architecture
through `ARCHES`. Sharing this repository requires serializing the entire
update and publication cycle.

The old locking code in [update.sh](../update.sh) was:

```bash
exec 9>"$REPO_DIR/.state/update.lock"
if ! flock -n 9; then
    echo 'Update already running'
    exit 0
fi
```

`flock -n` returns immediately when another process holds the lock. The script
converted that outcome to exit status zero. In the reported sequence:

1. arm64 acquired the shared lock and began querying and building.
2. amd64 encountered the busy lock and returned without querying or building.
3. [entrypoint.sh](../entrypoint.sh) saw a successful exit, printed
   `Update cycle complete`, and started its `CHECK_INTERVAL` sleep.
4. arm64 later failed and released the lock when its cycle exited.
5. amd64 was already sleeping. Releasing the lock could not wake it because it
   had stopped trying to acquire the lock.

The patch failure did not cause amd64 to skip. The skip happened earlier,
while arm64 still held the lock. Even a successful arm64 build would have left
amd64 asleep until its next interval. Repeated timing collisions could keep
deferring one architecture; the old behavior provided no waiting handoff.

## Implemented behavior

The replacement is:

```bash
exec 9>"$REPO_DIR/.state/update.lock"
echo 'Waiting for repository update lock'
flock 9
```

The default exclusive `flock` blocks until the lock becomes available. There
is no busy-lock success exit. The waiting updater proceeds through its normal
complete cycle after acquisition, including when the previous cycle failed.
Failure of the lock command itself remains an error under `set -Eeuo pipefail`.

The kernel releases locks when the last process holding the corresponding open
file description exits or closes it. The empty lock file can remain. Do not
delete it to try to unblock another updater: replacing the lock file can allow
processes to lock different files and defeat mutual exclusion.

The lock still covers queries, package builds, storage, and publication. Each
entrypoint sleeps for `CHECK_INTERVAL` only after its own update invocation
returns. A waiter stays inside that invocation and does not enter the sleep
because another service is busy. This does not impose a fixed amd64-first order,
a strict alternating schedule, or a maximum wait. A hung lock holder can keep
other updaters waiting and requires investigation.

The message `Waiting for repository update lock` is printed before every lock
attempt, including when acquisition is immediate. Seeing that message alone
does not establish contention or failure.

| File | Change made for this incident |
| --- | --- |
| [update.sh](../update.sh) | Replace the nonblocking skip with a blocking lock |
| [tests/test_publisher.py](../tests/test_publisher.py) | Replace the skip expectation with a wait-and-complete regression |
| [ARCHITECTURE.md](../ARCHITECTURE.md#the-update-cycle) | Document waiting and continuation after the previous updater fails |
| [README.md](../README.md#how-an-update-works) | Describe the shared-storage wait behavior |
| [xfce4-terminal notes](xfce4-terminal.md#headless-build-server) | Explain how the architecture services share the lock and sleep after their own cycles |

The lock implementation entered repository history as commit `cf50a39`,
`fix: arm64 and amd64 now take turns running rebuild`. The blocking lock remains
present in the checkout reviewed on 2026-11-13.

## Verification and its limits

The regression is named
`PublisherTests.test_busy_lock_waits_then_runs_complete_update`. It uses a
temporary repository, fixture adapter, and real kernel locks:

1. The test holds the repository lock through Python's `fcntl.flock`.
2. It starts a real `update.sh` subprocess with output redirected to a log.
3. It requires that the subprocess remain running for one second, with no
   adapter events or generated packages while the lock is held.
4. It releases the lock, waits up to twenty seconds for completion, and requires
   a successful exit.
5. It checks that two fixture packages were stored and that both amd64 and arm64
   indexes contain the fixture package.
6. It kills and reaps an unexpectedly stuck subprocess during test cleanup.

This establishes waiting, exclusion of package work while locked, and completion
after release. It does not launch two real architecture containers or explicitly
make a preceding updater fail; continuation after failure follows from kernel
lock release and the waiting updater's independence from the holder's exit code.
It also does not compile xfce4-terminal or test desktop behavior. Fixture signing
is used in framework tests; no real signing integration test was run for this
locking-only change.

Original verification completed successfully:

- `bash tests/run.sh --framework`: 63 tests passed in 87.480 seconds.
- `bash -n update.sh`: passed.
- `git diff --check`: passed.

The retained local evidence was still present when this handoff was written:

- `build/lock-fix/framework.log`: coordinator result and regression log path.
- `build/test-run-u1DT3U/regression.log`: detailed original 63-test result.
- `build/lock-fix/syntax.log`: empty successful syntax-check output.
- `build/lock-fix/diff-check.log`: empty successful whitespace-check output.

These are ignored local artifacts and may disappear. The count and duration
describe the original run, not a new run of the repository after later changes.
For fresh verification from the project root, run:

```bash
mkdir -p build/lock-fix-review
timeout 30m bash tests/run.sh --framework > build/lock-fix-review/framework.log 2>&1
bash -n update.sh > build/lock-fix-review/syntax.log 2>&1
git diff --check > build/lock-fix-review/diff-check.log 2>&1
```

Inspect each command's exit status and completed log. The framework coordinator
reports the location of its more detailed `build/test-run-*/regression.log`.

## Deployment and operational confirmation

No image build, service recreation, or live deployment was performed in the
lock-fix conversation. The runtime script is copied into images, so a checkout
edit alone does not update existing containers. On the intended deployment,
build the images and then recreate both services after a successful build:

```bash
mkdir -p build/lock-deployment
timeout 30m docker compose build rebuild-amd64 rebuild-arm64 > build/lock-deployment/images.log 2>&1
timeout 5m docker compose up -d --force-recreate rebuild-amd64 rebuild-arm64 > build/lock-deployment/services.log 2>&1
```

Run the second command only if the first succeeds. Service recreation begins
real update cycles for all configured rebuild streams using the configured
storage and signing identity. For experiments, use isolated local repository
data and keys as described in [local testing](../README.md#local-testing).
This documentation task does not establish whether a separate deployment has
already applied the fix.

After allowing a complete cycle, capture a bounded log snapshot to a file:

```bash
docker compose logs --no-color --tail=1000 rebuild-amd64 rebuild-arm64 > build/lock-deployment/cycles.log 2>&1
```

Review that completed snapshot for both services reaching their stream queries
and reporting their actual cycle result. One should wait while the other owns
the repository. After release, the waiting service should begin work without
first sleeping through another interval. If a build fails, confirm the other
service still proceeds after the failed cycle's publication attempt and exit.
Actual package build failures remain visible failures after this lock fix.

## Separate xfce4-terminal patch failure

The supplied log establishes an application failure of the then-current
`000-shift-enter.patch` against Debian source `1.1.4-1`. Several hunks matching
with offsets while others reject indicates source-context differences; the
conversation did not finish comparing the intended patch base with Debian's
source. It did not establish that the problem was arm64-specific. Patch
application precedes architecture compilation and needs review on both paths.

The log also contained an APT cache cleanup permission error and a `dpkg-source`
warning that no acceptable source signature was found. Processing continued
through extraction and reached quilt. Neither message explains why amd64 skipped
its cycle, and neither was investigated or fixed in this conversation. Do not
treat successful publication of old packages as proof that those messages were
resolved.

The repository has evolved since the incident. On 2026-11-13 the Shift+Enter
patch has different contents from the originally reported patch, and the local
series also includes `001-title-bar-tabs.patch`. Later configure work is
documented in [the terminal handoff](xfce4-terminal.md#configure-override-implementation-and-handoff).
The old failure should therefore be treated as historical evidence, not proof
that the current patch still rejects. No fresh patch-application or compilation
check was performed for this documentation handoff.

If the failure recurs, inspect the exact newly selected Debian source version,
its existing Debian patches, and the local series. Preserve the rejected source
tree and logs, compare failed context with the intended changes, then refresh
and verify the patch using the adapter's zero-fuzz policy. Do not force failed
hunks through or weaken layout checks to make the build appear successful.
Reuse verified cached downloads where available. Keep investigation files under
ignored `build/`, and follow current failure-workspace handling in
[the architecture notes](../ARCHITECTURE.md#publication-storage-and-failures).

The repository already had unrelated edits when the lock work began, including
Dockerfile and dependency-layer restructuring. Those changes were preserved.
This handoff also preserves existing staged and unstaged documentation work;
it does not claim that all present changes belong to this incident.
