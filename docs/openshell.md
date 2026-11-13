# OpenShell redistribution

For the complete investigation, decisions, implementation map, verified artifact
hashes, actual test failure and deployment handoff, read
[OpenShell and redistribution history](openshell-redistribution-handoff.md).

The `packages/redistribute/openshell` adapter follows the latest stable release from
[NVIDIA/OpenShell](https://github.com/NVIDIA/OpenShell/releases). It selects one
official Debian asset per requested architecture, amd64 or arm64, and verifies its
GitHub release SHA256. Prerelease, development and Snap assets are excluded.
The upstream Debian revision, maintainer, dependencies and package bytes are retained.

## Architecture and contents

The official single `openshell` package includes:

- `/usr/bin/openshell`: command-line client.
- `/usr/bin/openshell-gateway`: gateway daemon.
- `/usr/bin/openshell-prover`: standalone policy verification.
- `/usr/libexec/openshell/openshell-driver-vm`: VM compute helper.
- `/usr/lib/systemd/user/openshell-gateway.service`: user service.

The gateway manages sandbox lifecycle through a compute driver. A trusted supervisor
mediates requests from the isolated agent. Sandbox and supervisor runtime images
remain managed by OpenShell and the selected runtime; this repository distributes
the official Debian package. See the [upstream architecture](https://github.com/NVIDIA/OpenShell/blob/main/docs/about/architecture.mdx).

The importer checks these fixed paths, the license, ELF class and machine identity
without executing upstream code. Maintainer scripts are preserved and can run on
client installation.

## Installation

Configure the [redistribute repository](../README.md#unchanged-package-redistribution),
then install and activate it as the intended user:

```bash
sudo apt update
sudo apt install openshell
systemctl --user daemon-reload
systemctl --user enable --now openshell-gateway
openshell gateway add https://127.0.0.1:17670 --local --name openshell
openshell status
```

Prepare a supported runtime first. Upstream documents Docker Engine 28+, Podman 5.x
with a user socket and cgroups v2, or KVM for Linux MicroVMs. The package does not
install Docker automatically. The gateway reads `~/.config/openshell/gateway.toml`
and optionally `gateway.env`. Enabling linger is an operator decision. See
[upstream requirements](https://github.com/NVIDIA/OpenShell/blob/main/docs/about/installation.mdx).

## Provenance and verification

Import provenance lives under `REPO_DIR/.state/imports/` and is exposed through the
signed Packages index. Back up these records along with the packages. Recipe changes
cause revalidation, without changing package versions or replacing upstream bytes.

OpenShell 0.1.8-1 omits Installed-Size. The publisher estimates logical payload size
in KiB for the index, including when upstream size metadata is missing or stale.
The package's own control archive remains unchanged.

Offline fixtures cover both architectures, byte preservation, index metadata,
size estimation, layout/ELF checks, corruption, retries and asset changes.
Offline success does not establish that the gateway or sandbox works on a client.
