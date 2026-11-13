# GIMP AppImage extraction memory incident

Recorded on 2026-11-13 from the incident conversation and a static review of the
current checkout. This document preserves that conversation's technical findings,
change, verification and limitations so the chat can be deleted. It supplements
the [maintained GIMP notes](gimp-3.2.md) and
[earlier investigation history](gimp-3.2-investigation-history.md).

## Reported failure

The operator supplied logs from `codex-repo-updater-1`. The `gimp-3.2` stream
selected version `3.2.6-1` for amd64. At that time the application and language
manuals were one family of 41 packages. The downloaded
`/tmp/tmp.UW6PuuJYer/streams/gimp-3.2/gimp-amd64.AppImage` passed SHA256 verification
(`OK`), then Bash reported `Killed` for the `unsquashfs` process (PID 453).
The extraction command used `-no-progress -no-xattrs -processors 1`, an AppImage
offset and an explicit list of GIMP-owned paths. The old build hook reported
the failure at line 67, the end of that multiline command.

The publisher then reported `Build failed for 3.2.6-1 (amd64)` and
`Update failed; continuing with remaining streams`. This was a build failure
after download verification, before staging and Debian package construction.
The stream isolation behaved as intended. The supplied excerpt does not establish
the outcome of other streams or final publication.

## Diagnosis and confidence

The Compose configuration inspected during the incident imposed `mem_limit: 256m`
and `pids_limit: 128`. Unsquashfs defaults allow a 256 MiB data queue and a
256 MiB fragment queue. These are separate from its processor count; limiting
decompression to one processor does not lower those queue limits. See the
[Debian Trixie unsquashfs manual](https://manpages.debian.org/trixie/squashfs-tools/unsquashfs.1.en.html).

An out-of-memory kill was therefore the likely explanation. It was an inference,
not a confirmed kernel diagnosis: no kernel OOM report, cgroup `memory.events`,
peak memory measurement or successful reproduction was obtained in this chat.
`Killed` alone does not identify who sent the signal. The two default queue
limits also do not prove that both queues were fully allocated at the failure.

## Implemented change

The old `packages/gimp-3.2/build` extraction invocation was changed to:

```bash
# Extract data directly. Never execute AppRun, the AppImage runtime, or target ELF.
# Each default cache can grow to 256 MiB, exceeding the container's memory limit.
unsquashfs -no-progress -no-xattrs -processors 1 \
    -data-queue 16 -frag-queue 16 -o "$OFFSET" \
    -d "$SOURCE_DIR" "$ARCHIVE" \
    # The existing explicit extraction path list follows here.
```

This excerpt illustrates the options; the comment standing in for the path list
is not a complete command to execute. The
[current build hook](../packages/repack/gimp-3.2/build) contains the full command.
Both queues are capped at 16 MiB, leaving more space for metadata, decompressor
state and other processes. The caps do not bound total process or container
memory to 32 MiB. No extraction paths, integrity checks, processor selection,
architecture support or framework failure handling were changed by this fix.
The incident fix did not raise the container memory limit.

Adapter files are recipe checksum inputs. Changing this hook can rebuild current
targets at a new publisher revision under the normal stored-package rules; it
does not require manual revision counters or removal of stored packages.

## Verification actually performed during the incident

The original working tree contained untracked `gimp-investigation/`, which was
left alone. The following checks were run before the operator restricted work
to static operations:

- `bash tests/run.sh gimp-3.2` exited successfully. Its detailed log reported
  14 tests, six passing and eight skipped. The eight AppImage tests were skipped
  because the host lacked required `patchelf` and/or SquashFS tools; a direct
  `unsquashfs -help` attempt specifically reported command not found. The six
  passing tests covered the then-combined manual importer, not extraction under
  memory pressure. The runner's overall success must not be interpreted as
  successful GIMP extraction coverage.
- `bash -n packages/gimp-3.2/build` passed.
- `git diff --check` passed.

The historical logs were `build/gimp-memory-logs/tests.log`, `syntax.log`,
`diff-check.log` and `images.log`, with the detailed regression report at
`build/test-run-5CSlhw/regression.log`. These files were absent when this handoff
was written. The results above are transcribed from the conversation's recorded
output, not a fresh reading of surviving logs.

A read-only Docker image listing failed with permission denied on
`/var/run/docker.sock`. An escalation request to inspect local images was
interrupted by the operator, who instructed: **Do static operations**.
No successful Docker inspection, dependency installation, container build,
live extraction, signing test, service restart or deployment was established
by this conversation. Subsequent work in this chat remains static only.

## Current checkout and later changes

On 2026-11-13, static inspection established:

- The adapter now lives at `packages/repack/gimp-3.2/`. Its build hook still uses
  `-data-queue 16 -frag-queue 16` and one processor.
- Help manuals are now a separate `packages/repack/gimp-help-3.2/` stream.
  The application stream declares eight packages. The original combined test
  counts describe the historical suite, not today's stream organization.
- [Compose](../compose.yaml) now gives the repack publisher 512 MiB and 128
  processes. Its comment attributes the increase to Alex's Thorium XZ dictionary
  requirements, not this GIMP incident. Rebuild services override these limits.
- [The isolated GIMP publisher coordinator](../tests/gimp-3.2/test-publisher.sh)
  still explicitly uses `--memory 256m --pids-limit 128`. This is a stricter
  memory test than current repack Compose, rather than a match for its limits.

The cache caps remain useful with the later 512 MiB deployment limit. Their
presence alone does not establish that the complete current build fits either
limit. Several unrelated staged and unstaged documentation changes existed
when this record was written; this task does not commit or reconcile them.

## Remaining validation and recovery context

The outstanding question from this incident is whether the real AppImage
extraction and complete package build succeed under the intended memory limit.
Static inspection cannot answer it. If runtime work is authorized in a future
session, use the maintained adapter tests and isolated publisher coordinator,
redirect output to named logs under ignored `build/`, and retain failure logs
and cgroup evidence. Record the actual architecture, upstream version, image,
memory limit and complete/failed stages. An extraction-only success would not
prove the rest of the build fits the limit.

For a repeated kill, capture the relevant container cgroup memory events and
available kernel OOM evidence before assigning a cause. Inspect any failed source
or staging tree before selectively removing temporary trees for a retry; the
adapter deliberately refuses to reuse existing extraction/staging directories.
Reuse checksum-verified downloads where appropriate. Never remove repository
packages, signing keys or provenance/state to retry this failure.

Adapters are copied into the publisher image. Editing the host checkout does
not update an already running container; deployment requires rebuilding and
recreating the relevant service using the current README instructions. That is
a separate future action, not something performed or verified by this record.
