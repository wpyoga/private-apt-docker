# Patched xfce4-terminal

The adapter follows the newest xfce4-terminal source in Debian Trixie,
trixie-updates and trixie-security. APT verifies repository metadata and source
checksums. Each architecture starts with a fresh `dpkg-source` extraction, including
Debian's existing patches, then applies the local series without patch fuzz.
There is no persistent upstream Git checkout. Only xfce4-terminal is compiled;
its build dependencies are installed from Debian binary packages.

## Public patches

Commit patches under `packages/rebuild/xfce4-terminal/patches/` and list their filenames,
one per line in application order, in `patches/series`. Blank lines and lines
starting with `#` are ignored. The initial series is intentionally empty.
Do not commit secrets. Adapter file changes allocate a new package revision;
unrelated adapters retain their own recipe checksums.

Versions retain the full Debian source version and append `+local-N`, for example
`1.1.4-1+local-1`. Patch changes increment N through the existing stored-package
revision mechanism. New Debian source versions start a fresh revision history.
Failures identify the package/version/architecture in logs, retain old published
packages, and retry next cycle. Other streams continue. Logs are the alert channel.

## Headless build server

No desktop is required. The initial build image targets an amd64 Docker host,
building amd64 natively and arm64 with Debian cross-development packages.
Separate images are required because the two Xfce development dependency sets
pull in conflicting architecture-specific xfconf packages.
Rootless Docker can run the deployment; configure its normal host prerequisites
first. No Docker socket is mounted inside the publisher.

Use the same checkout, `.env`, and Compose project as the repack publisher.
Set `REPACK_REPO_DIR` and `REBUILD_REPO_DIR` to different absolute output paths;
keep both architectures in `REPO_ARCHITECTURES`. `REPO_DATA_DIR/gnupg` holds the
shared signing key. Run setup once to prepare both outputs and the signing key.

```sh
docker compose up -d --build
```

Compose builds the base publisher first, then the two toolchain images through
its service build contexts. Services are `codex-repo-updater`, `rebuild-amd64`,
and `rebuild-arm64`. The latter two use the same rebuild output and lock, with
one architecture per instance. A busy lock skips a cycle and retries after the
configured interval. Repacks use their separate output and lock.

Adapters are copied into images; rebuild and recreate services after changes.
Compilation runs with the configured host UID/GID. Package dependency installation
occurs only in image layers. No per-package repository setting is needed: parent
directories select adapter membership. The Dockerfile consumes the named build
context supplied by Compose; standalone docker builds must supply that context.

If Debian adds build dependencies, update the adapter Dockerfile and rebuild the
image; failed dependency checks must not be bypassed.

The environment follows Trixie but is not bit-for-bit reproducible: image tags
and dependency versions are not pinned. Native amd64 and cross-compiled arm64 builds of Debian source 1.1.4-1
were validated in the toolchain containers. Both output ELF architectures and
Installed-Size values in package indexes were checked. Desktop runtime behavior
and rootless-daemon deployment remain unverified.

## Laptop

Serve this deployment's repository using the existing web-server instructions.
Add its APT entry with the shared repository Signed-By key, then prefer its package:

```text
Package: xfce4-terminal
Pin: release o=rebuild
Pin-Priority: 990
```

The Origin must match your chosen REPO_NAME. Check `apt-cache policy
xfce4-terminal` before `sudo apt install xfce4-terminal`, especially if you set
APT::Default-Release. The preference keeps the last successful local build
selected while newer Debian source is being rebuilt. Quit existing terminal
processes before testing the new executable. Interactive testing happens on the
laptop; the build server does not need a graphical session.

Rootless Docker itself is not validated by the offline suite. Its UID mapping
can differ from the system daemon: verify bind-mounted files retain the intended
host ownership before using real repository storage. The Compose UID/GID settings
are designed for the existing system-daemon deployment and must not be assumed to
map identically under a rootless daemon.

The arm64 build marks Debian's existing `xfce4-dev-tools (>= 4.18.1)` build
dependency as `:native`, since it executes on the amd64 builder. The adapter
checks that declaration before changing it and fails if Debian changes its
layout. This packaging adjustment is separate from the initially empty local
patch series. Upstream tests are disabled for these cross-builds; desktop runtime
verification remains a laptop check.
