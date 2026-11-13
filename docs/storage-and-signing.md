# Repository storage and GPG agent operations

This guide preserves the storage and signing decisions, the migration incident,
and the operational steps discussed on 2026-10-31. It was checked against the
repository on 2026-11-13. The [README](../README.md#repository-storage-and-serving)
owns deployment instructions; [ARCHITECTURE.md](../ARCHITECTURE.md#configuration-and-ownership)
explains the design. This guide adds troubleshooting and historical context so
neither operation nor maintenance depends on the original chat.

## Public outputs and private signing state

The original example layout put each keyring beside its repository:

```text
/srv/apt/repack/repo/
/srv/apt/repack/gnupg/
/srv/apt/rebuild/repo/
/srv/apt/rebuild/gnupg/
```

Serving one `repo/` directory worked, but serving `/srv/apt` to expose both
repositories under one domain would also put private keyrings under the web
root. Filesystem permissions alone were not the desired separation. The chosen
layout makes `/srv/apt` the public document root and keeps signing state elsewhere:

```text
/srv/apt/
├── repack/                       # pool/, dists/, .state/
├── rebuild/                      # pool/, dists/, .state/
└── redistribute/                 # added after the original migration

/var/lib/apt-publisher/gnupg/
├── repack/                       # private keyring
├── rebuild/                      # private keyring
└── redistribute/                 # independent private keyring
```

The corresponding settings in `.env.example` are:

```dotenv
REPACK_REPO_DIR=/srv/apt/repack
REBUILD_REPO_DIR=/srv/apt/rebuild
REDISTRIBUTE_REPO_DIR=/srv/apt/redistribute

REPACK_GNUPG_DIR=/var/lib/apt-publisher/gnupg/repack
REBUILD_GNUPG_DIR=/var/lib/apt-publisher/gnupg/rebuild
REDISTRIBUTE_GNUPG_DIR=/var/lib/apt-publisher/gnupg/redistribute
```

Host paths remain independently configurable. Each service sees its repository
as `/repo` and its keyring as `/gnupg`; relocating host storage does not require
changing publisher or adapter paths. Setup gives outputs mode 0755 and keyring
directories mode 0700, owned by the configured publisher UID/GID. Caddy needs
read access to outputs and traversal access through their parents, and no access
to private keyrings. Never place keyring backups beneath the web root.

Caddy's root is `/srv/apt`, as shown in the README. The APT base URLs end in
`/repack/`, `/rebuild/`, or `/redistribute/`. Each repository has its own signing
identity. A client source entry must pair its URL with that repository's exported
public key through `signed-by`. Changing a storage path does not require changing
keys; changing a URL requires updating the client source entry.

Repository outputs also contain publisher state, including `.state/`. The change
separates secret signing material from the document root; it does not create a
filtered export containing only `pool/` and `dists/`. Preserve repository state
when moving or backing up an output.

## Containers, images, keys, and agents

One checkout and one Compose project can run several containers. At the time of
the original incident there were three services. The current configuration has
four:

| Compose service | Adapter group | Persistent output and keyring |
| --- | --- | --- |
| `codex-repo-updater` | `packages/repack/` | Repack |
| `rebuild-amd64` | `packages/rebuild/` | Rebuild, amd64 build selection |
| `rebuild-arm64` | `packages/rebuild/` | Rebuild, arm64 build selection |
| `redistribute` | `packages/redistribute/` | Redistribute |

An image is a template for containers. Sharing an image, checkout, `.env`, or
Compose project does not make these services one container. The two rebuild
services deliberately mount the same output and keyring. The repository lock
serializes their cycles. They use the same stored signing key but separate agent
processes and socket files. Repack and redistribute have their own keyrings.

A socket is the local communication endpoint through which GPG asks an agent to
use a secret key. If the socket lives in a bind-mounted keyring, another container
or a host command with access to that path can potentially reach the same agent.
Sharing stored key files and sharing a running agent are separate choices.

## What failed during the directory migration

After moving storage, both repack and rebuild logged:

```text
gpg: problem with fast path key listing: No such file or directory - ignored
gpg: error reading key: No secret key
Update cycle failed; retry next interval
```

The operator confirmed that the expected public key databases, private key files,
revocation certificates, trust databases, and `S.gpg-agent*` entries were present
at the new host paths. File presence alone did not establish that the running
agent was reading those paths, or that the containers had refreshed their mounts.
A private key filename uses a keygrip, which need not equal its signing
fingerprint; a different filename is not itself evidence of the wrong key.

Stopping the publishers, stopping the agents for the moved keyrings, and
recreating the containers resolved the failure. The operator confirmed recovery.
The exact process IDs and agent home directories were not recorded before the
recovery. A stale agent using the old directory was the leading explanation;
refreshing old container bind mounts was also a relevant possibility. Because
both were addressed together, the recovery did not isolate one cause conclusively.
The fast-path warning by itself is not a complete diagnosis of missing keys.

The operator then stopped the containers and observed an agent still running.
The previous setup implementation invoked `sudo -u REPO_USER gpg` on the host.
GPG can start an agent automatically, and that host agent can outlive setup and
the publisher containers. This was a real lifecycle gap in setup.

### Interpreting the other messages

The old nonblocking lock implementation printed `Update already running` when
one rebuild service found the other holding the repository lock. It returned
success after skipping that cycle, so its entrypoint then printed `Update cycle
complete`. That pair of messages did not demonstrate successful signing.

The current code has changed since that incident: `update.sh` prints
`Waiting for repository update lock` and uses blocking `flock`. A waiting builder
runs its own complete cycle after acquiring the lock. Do not diagnose the current
lock behavior from the old log excerpt.

## The implemented lifecycle fix

All application GPG operations now run in containers, including setup:

1. `codex-repo-setup.sh` validates configuration and builds
   `private-apt-publisher:local` directly. It cannot depend on Compose yet because
   Compose requires the UID/GID and key fingerprints setup is preparing.
2. Setup creates or reuses the host publisher account and directories. Its
   `run_signing_gpg` function runs GPG in temporary containers with the publisher
   UID/GID, `--rm`, `--init`, no network, dropped capabilities, and no new
   privileges. Key inspection, generation, selection, and public export all use
   this path. Setup never invokes host GPG.
3. Every publisher and setup container gets a private tmpfs at `/run/user/UID`,
   owned by that UID/GID with mode 0700. Persistent keys remain mounted at
   `/gnupg`; runtime sockets live in the private tmpfs.
4. `lib/gnupg.sh` calls `gpgconf --create-socketdir`, then verifies that the
   selected socket directory is `/run/user/UID/gnupg` or beneath it. A nondefault
   GPG home such as `/gnupg` needs this creation step. Startup fails if GnuPG
   selects the persistent keyring or an unexpected runtime directory instead.
5. `entrypoint.sh` prepares the socket directory and launches its container's
   agent before entering the update loop. The two rebuild agents can use the same
   persistent keys without reaching each other's socket.
6. Agents remain in the container's process namespace and die with that
   container. Temporary setup containers also stop their agents when their GPG
   command exits and the container terminates. An agent can stay alive between
   update cycles inside a running publisher; that is expected.

GnuPG may add a `d.*` subdirectory under the runtime `gnupg/` directory. Use
`gpgconf --list-dirs agent-socket` to discover the actual socket path rather than
hardcoding the suffix. The existing keyrings and fingerprints are preserved.
There is no key rotation, keyring synchronization, revision reset, or automatic
storage migration in this change.

The application guarantee concerns publisher and setup agents. Docker and host
administration commands still run on the host. Tests may deliberately start a
throwaway host agent and clean it up; they do not use production keys. Existing
agents started by older setup versions require a one-time shutdown.

## Migration and deployment

Use the [storage migration checklist](../README.md#moving-existing-storage) for
moving existing repositories. The ordering matters:

1. Stop every publisher and manual update job using the affected storage. Stop
   Caddy too if it already serves a directory containing private keyrings.
2. Back up complete outputs and keyrings outside the web root. Record the
   existing fingerprints and ownership from the operator configuration.
3. Stop old host agents while the old keyring paths are still known. Use
   `gpgconf --homedir PATH --kill gpg-agent` as the publisher account. If storage
   was already moved, use the current paths first; inspect remaining processes
   if an agent survives. Do not generate replacement keys to fix a path problem.
4. Move the complete keyrings outside `/srv/apt`, preserving ownership and
   permissions. Move complete repository outputs, including hidden files,
   `.state/`, old versions, and by-hash indexes. When flattening
   `/srv/apt/repack/repo` into `/srv/apt/repack`, check for destination conflicts
   before moving contents. Apply the same treatment to rebuild where needed.
5. Update the directory settings in `.env`, keeping signing fingerprints and
   publisher UID/GID. Verify that `/srv/apt` contains no private keyring copies.
6. Update Caddy's document root and recreate publishers so Docker refreshes their
   bind mounts. Update client source URLs where necessary, retaining their
   existing trusted public keys.

For an existing deployment already using the new host paths, apply the agent
fix with the following one-time sequence. Replace the example account with
`REPO_USER` and adjust custom paths. Include redistribute when that service has
an existing keyring and agent:

```sh
docker compose stop

sudo -u aptrepo gpgconf \
    --homedir /var/lib/apt-publisher/gnupg/repack --kill gpg-agent
sudo -u aptrepo gpgconf \
    --homedir /var/lib/apt-publisher/gnupg/rebuild --kill gpg-agent
sudo -u aptrepo gpgconf \
    --homedir /var/lib/apt-publisher/gnupg/redistribute --kill gpg-agent

docker compose up -d --build --force-recreate
```

These host `gpgconf` commands are a migration cleanup, not the ongoing setup
workflow. They stop existing agents without deleting keys. A Compose restart
alone does not update bind mounts, image contents, or new tmpfs settings; recreate
the containers. Setup does not need to be rerun to adopt agent isolation.

## Diagnosing another missing-key failure

First distinguish a stale mount, wrong fingerprint, inaccessible key files, and
an agent connection problem. Run these commands from the project root as the
host user with Docker access. They collect metadata, not private key contents:

```sh
mkdir -p build/gpg-diagnostics

for SERVICE in codex-repo-updater rebuild-amd64 rebuild-arm64 redistribute; do
    docker compose exec -T "$SERVICE" bash -c '
        id
        printf "GNUPGHOME=%s\nGPG_KEY=%s\n" "$GNUPGHOME" "$GPG_KEY"
        ls -ld /gnupg /gnupg/private-keys-v1.d
        ls -l /gnupg/private-keys-v1.d
        gpgconf --list-dirs socketdir agent-socket
        gpg-connect-agent --no-autostart "GETINFO pid" /bye
        gpg --batch --list-keys "$GPG_KEY"
        gpg --batch --list-secret-keys "$GPG_KEY"
    ' > "build/gpg-diagnostics/$SERVICE.log" 2>&1
done

docker compose ps -a > build/gpg-diagnostics/containers.log 2>&1
```

For the current configuration, expect the configured UID/GID, `GNUPGHOME=/gnupg`,
the correct repository fingerprint, and a socket beneath `/run/user/UID/gnupg/`.
A failure to exec a stopped service is recorded in that service's log. Listing
keys can start an agent, so the preceding `--no-autostart` check records whether
one was already reachable. Check the resulting logs after the commands finish.

Inspect Docker's actual mounts for one affected service:

```sh
CONTAINER_ID=$(docker compose ps -q codex-repo-updater)
: "${CONTAINER_ID:?Repack container is not running}"
docker inspect --format '{{json .Mounts}}' "$CONTAINER_ID" \
    > build/gpg-diagnostics/repack-mounts.json 2>&1
docker top "$CONTAINER_ID" -eo pid,ppid,comm,args \
    > build/gpg-diagnostics/repack-processes.log 2>&1
```

Verify that `/gnupg` points to the intended host keyring and that the runtime
mount is private to the container. If the mount source is stale, stop and recreate
that service. If ownership is wrong, restore the configured publisher UID/GID and
keyring directory mode 0700; do not make private keys world-readable. If the
fingerprint is wrong, select the existing intended key rather than replacing it.
If startup reports the socket-directory validation error, check the Compose tmpfs
mount and deployed image before changing key material.

### Host-visible processes and unsuccessful `pkill`

A container process appears in the host's process list because the host can see
processes in descendant PID namespaces. Host visibility alone does not establish
that an agent was started outside Docker. Compare its host PID with
`docker top CONTAINER`, or inspect its PID namespace and cgroup. If an identified
agent remains after all containers that could own it have stopped, investigate
host setup or another host GPG client.

`sudo pkill gpg-agent` normally sends `SIGTERM`. GPG's agent handles `SIGTERM` by
waiting for current requests to finish. GnuPG documents a forced shutdown after
three `SIGTERM` signals and immediate shutdown for `SIGINT`. Root can deliver a
signal without changing the program's signal handling. Prefer the keyring-specific
`gpgconf --homedir PATH --kill gpg-agent` command for a controlled shutdown.

The exact `pkill` command, exit status, and process state were not captured during
the original incident, so waiting requests remain an explanation rather than a
confirmed diagnosis. A new PID indicates a replacement process. A zombie has
already exited and awaits its parent's collection of its exit status. An
`Operation not permitted` error needs separate investigation of permissions and
namespaces; it is not explained by GPG waiting for requests.

References: [Linux PID namespaces](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html),
[GPG agent startup](https://gnupg.org/documentation/manuals/gnupg26/gpg-agent.1.html),
[GPG agent signals](https://www.gnupg.org/documentation/manuals/gnupg/Agent-Signals.html),
and [gpgconf socket directories](https://gnupg.org/documentation/manuals/gnupg26/gpgconf.1.html).

## Verification and evidence

The implementation was checked on 2026-10-31 with:

- `bash tests/run.sh --framework`: 63 tests passed at that revision, including
  setup using fake Docker commands and rejection of host GPG invocations.
- `bash tests/test-signed-repo.sh`: real signing and isolated APT version selection
  passed. The initial sandbox run could not start GPG's agent; rerunning with
  local socket permission passed. This was a test-environment restriction.
- `bash tests/test-container-gpg.sh`: the publisher image built, throwaway key
  generation ran in a temporary container, and two real publisher containers
  signed using separate agents with the same stored keyring. Stopping the first
  preserved the second agent and its ability to sign. Stopping the second removed
  its host-visible agent PID. An unused `S.gpg-agent` file in the persistent
  keyring remained untouched, and no socket files were created there.
- Compose rendering confirmed private tmpfs mounts, configured UID/GID, and init
  for the three services then present. Shell syntax, local documentation links,
  and `git diff --check` also passed.

Useful historical logs, when retained in the local checkout, are under
`build/container-agent-checks/`, `build/test-run-PUdnko/regression.log`, and
`build/container-gpg-RWFMlV/{build,isolation}.log`. These ignored files are evidence,
not required configuration or committed artifacts. Their temporary test keys are
unrelated to operator keys. The test commands above reproduce the checks without
those directories or the chat. Current test counts can differ as features evolve.

The original Docker check used host UID/GID with the system Docker daemon. It did
not establish rootless-daemon ownership behavior or constitute a live deployment
of the entire repository. The operator confirmed the migration recovery, but
there was no later confirmation in this chat that the final isolation change was
deployed on the production server.

For this documentation update, recheck local links, shell examples, and statements
against the current scripts. Documentation-only changes do not require rerunning
package builds, signing tests, or the Docker integration test. Keep this guide
outside `packages/` so documentation changes do not alter adapter recipe checksums.
