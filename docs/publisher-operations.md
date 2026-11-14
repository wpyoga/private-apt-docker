# Publisher operations and recovery

Checked against the repository on 2026-11-14. This guide supplies the practical
answers from the original publisher conversation using today's multi-repository
configuration. [README](../README.md) owns the complete setup and hook contract;
[storage and signing](storage-and-signing.md) covers agent isolation and migration
diagnostics. Commands below are procedures for the operator, not actions executed
by the documentation update. Run them from the checkout root.

## Starting a newly cloned server

Install Docker with Compose and ensure the operator can use the daemon and sudo.
Current setup uses GnuPG inside containers rather than requiring host GPG for
normal key operations. For a new configuration:

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env`. Set `MAINTAINER`, repack `REPO_NAME`, `REPO_DESCRIPTION`, and the
signing-key creation settings. Set three independent output directories and
three independent signing directories. The example places outputs beneath
`/srv/apt` and private signing state beneath `/var/lib/apt-publisher/gnupg`.
Keep signing directories outside the served tree.

For an existing installation, keep its selected keys, paths, and UID/GID rather
than copying a new example over working settings. Configure the matching
`REPACK_GPG_KEY`, `REBUILD_GPG_KEY`, and `REDISTRIBUTE_GPG_KEY` fingerprints when
selecting existing keyrings. Setup selects an existing primary key if present;
it creates one if the keyring is empty. Multiple keys require explicit selection.
Never point an existing deployment at an empty keyring as a substitute for
restoring its key.

Run setup, then build/start services. Keep named logs and inspect them after each
command completes:

```bash
mkdir -p build/operations
./codex-repo-setup.sh > build/operations/setup.log 2>&1
```

After successful setup:

```bash
docker compose up -d --build > build/operations/start.log 2>&1
docker compose ps > build/operations/status.log 2>&1
docker compose logs --no-color --tail 200 > build/operations/publisher.log 2>&1
```

Do not continue past a failed command without inspecting its log. Setup builds
the base image directly, prepares the account/directories and independent keys,
writes fingerprints and UID/GID to `.env`, and exports `repack-pubkey.asc`,
`rebuild-pubkey.asc`, and `redistribute-pubkey.asc`. It does not start the loops.

The four services are `codex-repo-updater`, `rebuild-amd64`, `rebuild-arm64`, and
`redistribute`. Rebuild services currently expect an amd64 server with the
declared arm64 cross-build toolchain; this is not a claim of validated rootless
Docker support. Private build-dependency consumers additionally use the
[host worker workflow](build-dependencies.md), not just an ordinary direct build.

Containers start a cycle immediately, then wait the configured interval after
completion. A running container is not proof that the latest cycle succeeded:
the loop logs failures and retries later. Inspect completion/failure messages.

## Updating code or configuration

Adapter and framework files are copied into images. A checkout edit is not live
inside an existing container. After updating code, build the affected services
and recreate them. For a normal whole-project update:

```bash
docker compose build > build/operations/image-build.log 2>&1
```

After the build succeeds:

```bash
docker compose up -d > build/operations/recreate.log 2>&1
```

An environment-only change needs container recreation, not an image build.
`docker compose restart` restarts the same container configuration and does not
load a changed `.env`. Use `up -d --force-recreate` when explicitly refreshing
configuration. Images retain their cached dependency layers where applicable;
see [Docker build cache](docker-build-cache.md) before forcing a broad refresh.
Do not rerun setup merely to deploy updated package scripts.

## Running an update now

For an already running service, execute the existing single-cycle entry point.
For repacks:

```bash
mkdir -p build/operations
docker compose exec -T codex-repo-updater \
    bash /opt/apt-publisher/update.sh \
    > build/operations/manual-update.log 2>&1
```

Wait for command completion, then inspect the log and exit status. The same
repository lock applies; the command waits if another cycle owns it. The scheduled
loop remains a separate process and keeps its existing wait. This command checks
the service's whole adapter group, not just one package, and is not a dedicated
emergency-update feature. Substitute a rebuild or redistribution service only
when that group is intended; worker-dependent builds need their documented
coordinator/worker environment.

## Image tags and names

In `docker build -t apt-publisher:local .`, `-t` names/tags the resulting image,
and `.` is its build context. A custom tag is not an APT requirement. A stable
reference lets Compose and setup select the intended image without copying a
generated image ID after each build.

Current setup and the ordinary publisher service use
`private-apt-publisher:local`; rebuild images are architecture-specific. If
changing an image reference, update both the producer and consumers. Merely
adding another image tag does not change APT metadata, stream IDs, signatures,
or the name of an installed Debian package.

These other names have separate purposes:

| Name or setting | What it identifies |
| --- | --- |
| Git checkout directory / GitHub repository | Source location |
| Compose service such as `codex-repo-updater` | A running workload |
| `REPO_NAME` / Compose repository overrides | APT Origin and Label |
| `CODENAME` | APT suite/codename and `dists/` directory |
| `RELEASE_STREAM` | Persistent publisher stream identity |
| `BINARY_PACKAGES` and architecture-specific lists | Debian output identities |
| `*_REPO_DIR` | Host output storage; the web server chooses its URL |
| `*_GPG_KEY` | The signing key's fingerprint |
| GPG user ID / `GPG_KEY_NAME` | Human-readable key identity / setup creation input |

## Renaming the APT repository

To change the repack repository's display identity, edit `REPO_NAME` in `.env`.
Optionally edit `REPO_DESCRIPTION`. Recreate the repack service:

```bash
docker compose up -d --force-recreate codex-repo-updater \
    > build/operations/rename-repository.log 2>&1
```

Its first cycle publishes the new Origin and Label after processing its streams.
This does not require rebuilding the image or generating a new signing key.
Rebuild and redistribution currently set their own names (`rebuild` and
`redistribute`) in Compose; changing global `REPO_NAME` alone does not rename
them. Alter their explicit overrides if that is the intended change.

On clients, run `sudo apt update`, inspect the expected identity change, and
accept it when prompted. Review APT preferences that match the old Origin/Label.
A display-name change does not itself change the base URL or `CODENAME`. Moving
the web endpoint or distribution is a separate client-source change.

## Renaming the displayed name on an existing GPG key

A key has one or more user IDs, usually a name and email. Add the desired user ID
and make it primary; the fingerprint and signing key remain the same. This is
different from key rotation. `GPG_KEY_NAME` controls creation in setup and does
not modify a stored key when changed in `.env`.

For a running repack container, read the selected fingerprint from the trusted
operator configuration and use the container's existing keyring and private agent:

```bash
source ./.env
SERVICE=codex-repo-updater
FINGERPRINT="$REPACK_GPG_KEY"
NEW_UID="New Repository Name <repo@example.com>"
mkdir -p build/operations

docker compose exec -T "$SERVICE" gpg --batch \
    --quick-add-uid "$FINGERPRINT" "$NEW_UID" \
    > build/operations/key-add-uid.log 2>&1
```

After that succeeds:

```bash
docker compose exec -T "$SERVICE" gpg --batch \
    --quick-set-primary-uid "$FINGERPRINT" "$NEW_UID" \
    > build/operations/key-primary-uid.log 2>&1
docker compose exec -T "$SERVICE" gpg --batch \
    --list-secret-keys --fingerprint "$FINGERPRINT" \
    > build/operations/key-identity.log 2>&1
```

Choose `rebuild-amd64` with `REBUILD_GPG_KEY`, or `redistribute` with
`REDISTRIBUTE_GPG_KEY`, for the other identities. The two rebuild containers
share one stored key. These commands assume normal unattended signing works.
If the desired user ID already exists, inspect the listing and set it primary
without adding it again. The old ID can remain; if it is obsolete, explicitly
revoke that user ID with `--quick-revoke-uid FINGERPRINT OLD_UID`. This is not
`--revoke-key` or deletion of the secret key.

Export the updated public identity, checking command success before distributing
the file:

```bash
docker compose exec -T "$SERVICE" gpg --batch --armor --export "$FINGERPRINT" \
    > repack-pubkey.asc 2> build/operations/key-export.log
```

Use the matching export filename for another repository. Clients can import the
updated public export to see the new user ID; their existing key still verifies
signatures. Keep the fingerprint settings unchanged. Update `GPG_KEY_NAME` only
if its future creation default should also change.

The old conversation's `sudo -u ... gpg --homedir ...` examples predate container
agent isolation. Use the container procedures above for routine maintenance;
host GPG can create an agent outside the intended lifecycle. These commands have
been checked against the current configuration and
[GnuPG's key-management interface](https://gnupg.org/documentation/manuals/gnupg/OpenPGP-Key-Management.html),
but this documentation task did not rename an operator key.

## Diagnosing a failed or apparently idle publisher

Capture finite diagnostics, then inspect the files:

```bash
mkdir -p build/operations
docker compose ps > build/operations/status.log 2>&1
docker compose logs --no-color --tail 300 > build/operations/publisher.log 2>&1
```

Use this table to choose the relevant next check rather than deleting state or
bumping a revision manually:

| Symptom | Meaning and next check |
| --- | --- |
| Missing required setting before startup | Compare `.env` with `.env.example`; distinguish input settings from setup-generated outputs. |
| `Waiting for repository update lock` | Another updater may hold the lock. Inspect the other service; an empty lock file proves nothing. Never delete the lock file to bypass a live lock. |
| `Already stored` | Matching current output is complete. Verify whether code was rebuilt into the image and whether the expected files/settings are checksum inputs. |
| No current asset for an architecture | Query omitted that architecture; existing packages are retained. Check the adapter's exact stream and upstream asset policy. |
| Download checksum failure | Do not bypass verification. Check the selected upstream metadata and any retained partial download; use the adapter's documented retry policy. |
| Unexpected path, version, or architecture | The adapter's fixed expectations were violated. Inspect the artifact before deliberately changing the recipe. |
| Build failed for one stream | Other streams and publication are still attempted. Find the stream's first real error, not just the cycle's final summary. |
| Activity cannot be assessed / inactive stream | Monitoring warning, not automatic retirement. Check `release-date` and that stream's threshold. |
| `No secret key` or GPG socket error | Follow the mount, ownership, fingerprint, and private-socket checks in the storage/signing guide. Do not generate a replacement key as the first fix. |
| Container exited or killed, incomplete build log | Inspect Docker state and resource limits; read the relevant package incident guide. A killed process alone does not prove an out-of-memory event. |
| Client sees the old package | Check successful signed publication, the served path, `sudo apt update`, `apt-cache policy PACKAGE`, architecture and client pins. |

When a cycle fails, current `update.sh` logs
`Failed update workspace retained: PATH`. Inspect/copy useful evidence before
replacing the container. A later failed cycle for the same builder identity
removes the previous failure workspace; a successful retry leaves previous
failure evidence available. Workspaces normally live in container temporary
storage, separate from stored repository packages.

Completed artifacts are preserved. A partial repack/rebuild resumes at the
revision embedded in its successful artifacts; a completely failed build retries
the same next revision. Signing failure preserves old live indexes and allows
already stored artifacts to be published next time. Redistribution additionally
requires matching `.state/imports` records; current-target missing provenance can
be recovered by revalidation, while historical missing records need operator
recovery. Do not discard that directory.

The memory and integration failures of individual packages have more precise
diagnoses and tests than this general table. Use [the documentation index](README.md)
to find their handoffs and preserve the distinction between confirmed causes,
leading explanations, static inspection and actual runtime tests.

## Backup and restore boundaries

Back up each complete repository output, including `pool/`, `dists/`, by-hash
indexes, and `.state/`. Back up each independent private keyring, operator `.env`,
and relevant web-server/client configuration separately. Public `.asc` exports
alone cannot restore secret signing capability. Keep all private backups outside
the served root. Runtime agent sockets are not portable backup state.

For a consistent filesystem backup, stop all writers: all four Compose services
and any manual coordinators or host workers using the same outputs. Wait for
their exit before taking a filesystem snapshot or copying files with ownership
and permissions preserved. Stopping only one rebuild service leaves another
possible writer. Account for any manual metadata/cleanup operation too.

For restoration:

1. Keep publishers stopped. Restore complete outputs and corresponding private
   keyrings into the intended host paths, retaining the old fingerprints.
2. Restore/configure `.env`, preserving repository identities and intended UID/GID.
   Restore file ownership for that account and mode 0700 for private keyring
   directories. Keep all private keys outside the web root.
3. Compare the selected key fingerprints and public exports with the backup
   records. If the old secret key is unavailable, a new key is a separate trust
   migration requiring client updates, not an equivalent restore.
4. Verify that redistribution `.state/imports` accompanies its package files.
   Use current storage-migration instructions for any older layouts.
5. Recreate the publishers with their correct mounts. Inspect key access and the
   first publication, then check a client update and package candidate. Rebuild
   images only if source changes require it; restoring data alone does not change
   an image.

Preserving artifacts also preserves repack/rebuild revision history. Starting
with an empty pool loses that history and can produce versions clients will not
consider newer. Do not delete old packages to force a rebuild; fix the recipe or
recover the intended history. The
[manual removal procedure](../README.md#removing-older-package-versions) is a
separate operator action with explicit selection and publication steps, not
automatic temporary-file cleanup.

## References and verification limits

- [Compose up and recreation](https://docs.docker.com/reference/cli/docker/compose/up/)
- [Compose exec](https://docs.docker.com/reference/cli/docker/compose/exec/)
- [APT update and package selection](https://manpages.debian.org/trixie/apt/apt-get.8.en.html)
- [Storage/agent incident evidence](storage-and-signing.md)
- [Current testing commands](../README.md#local-testing)

The commands were reviewed against current scripts and service names. No new
server setup, container restart, key edit, backup, restore, client installation,
or runtime check was executed to write this guide. The
[foundations handoff](project-foundations-handoff.md#documentation-verification-on-2026-11-14)
records the documentation audit and its logs. Local log files are optional
evidence, not configuration.
