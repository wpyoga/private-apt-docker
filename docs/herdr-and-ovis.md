# Herdr and Ovis packages

## Sources and release streams

| Adapter | Debian package | Source | Method |
| --- | --- | --- | --- |
| `herdr` | `herdr` | [Herdr terminal releases](https://github.com/herdrdev/herdr/releases) | Package the official static binary. |
| `herdr-core` | `herdr-core` | [Core release manifest](https://releases.herdr.dev/core/latest.json) | Package the official archive. |
| `herdr-app` | `herdr-app` | [Desktop release manifest](https://releases.herdr.dev/app/latest.json) | Package the official archive. |
| `ovis-server` | `ovis-server` | [Ovis server releases](https://github.com/devswha/ovis/releases) | Package the compiled server and web files. |
| `ovis` | `ovis-desktop` | [Ovis releases](https://github.com/devswha/ovis/releases) | Preserve the official Debian package bytes. |

All streams support amd64 and arm64. Each stream selects its current stable
release. Missing architectures retain their stored packages. Invalid metadata
fails the stream. Each download must match the upstream SHA256.

The Herdr and Ovis server adapters use the repack repository. A packaging change rebuilds the
current release with a new Debian revision. The Ovis desktop adapter uses the redistribute
repository. Its upstream version, dependencies, maintainer scripts, and package
bytes remain unchanged. The publisher records its import source and checksum.

## Contents and requirements

`herdr` supplies `/usr/bin/herdr`. It is the terminal application. It does not
require `herdr-core`. The current Linux binaries are static. The adapter rejects
an unexpected ELF architecture, interpreter, or shared library dependency.
SSH connections use the recommended `openssh-client` package.

`herdr-core` supplies `/usr/bin/herdr-core` and the `/usr/bin/hc` symbolic link.
It runs terminals for desktop clients. The adapter checks the static binary and
preserves the archive's license and third-party notices. Package installation
does not start, stop, or restart a user's core. After an APT upgrade, an existing
core process can continue to use its old code. Use the upstream restart command
as the intended user when you are ready:

```bash
hc server restart
```

`herdr-app` supplies `/usr/bin/herdr-app`, a desktop entry, and an icon. It requires
`herdr-core` at or above the manifest's `core_min` version. Shared libraries come
from Debian 13. The adapter checks ELF architecture, known linked libraries, and
the Debian 13 glibc limit. It also declares the Vulkan, Wayland, EGL, and XKB
libraries that the application loads at runtime. A desktop session and a working
Vulkan driver are required.

The desktop icon is installed under `/usr/share/icons/`, away from the executable.
The upstream updater requires an icon beside its executable to identify an app
update directory. This package layout prevents it from treating `/usr/bin` as
that directory. Updates to the application use APT. The core's installed files
are also owned by the package manager. Do not run upstream update commands with
sudo to replace these files.

`ovis-desktop` includes Electron, Bun, a private Herdr core, the web interface,
and terminal helpers. It does not require either Herdr package. Its own terminals
are separate from terminals in an existing Herdr installation. The adapter checks
the fixed desktop, web, license, and executable paths without running upstream
code. Upstream maintainer scripts run on client installation. They set the command
alternative, configure the sandbox, and install an AppArmor profile where supported.

`ovis-server` provides the compiled Ovis server, the web interface, and the Rust
terminal helper. It requires `herdr-core`. It does not require Herdr terminal,
Herdr desktop, Ovis desktop, or a separate Bun or Node installation.
The upstream Bun runtime is part of the compiled server.

The adapter selects the latest stable GitHub release. It verifies GitHub's SHA256
for the release manifest, server, web archive, and terminal helper. It also checks
file sizes, hashes, and version against `ovis-server.json`. It uses the GitHub
asset digest to verify this manifest; it does not separately verify the upstream
Ed25519 signature. Missing server architectures retain their stored packages.
A missing common archive or required terminal helper fails the stream.

The adapter rejects unknown shared libraries, unsupported ELF architectures,
web archive links, unsafe paths, and missing web files. Linked glibc requirements
must fit Debian 13. The package includes upstream license notices and the Bun
license notice. These notices were reviewed for Ovis 0.5.9.

`/usr/bin/ovis-server` selects the installed Herdr core. It uses
`$XDG_STATE_HOME/ovis-server`, or `~/.local/state/ovis-server` when that variable
is absent. Set `OVIS_STATE_DIR` to use another state directory. Packaged files
are under `/usr/lib/ovis-server` and `/usr/share/ovis-server`.
The command name does not conflict with the Ovis desktop `ovis` command.

The user service runs `ovis-server serve` directly. It does not use the upstream
update supervisor. Application updates use APT. Package installation does not
enable or start the service. It does not stop or restart an existing Herdr core.

## Installation

1. Configure the [repack and redistribute repositories](../README.md).
2. Install the components that you need.

```bash
# Herdr terminal application:
sudo apt install herdr

# Herdr desktop application and its core:
sudo apt install herdr-app

# Ovis desktop application and its included runtime:
sudo apt install ovis-desktop
```

## Server and browser setup

Run the service commands as the user who will run the coding agents.

1. Install the server package.

```bash
sudo apt install ovis-server
```

2. Reload the user service definitions.

```bash
systemctl --user daemon-reload
```

3. Enable and start the Ovis service.

```bash
systemctl --user enable --now ovis-server
```

The service listens on `127.0.0.1:7317` by default. Optional settings belong in
`~/.config/ovis-server/env`. This file uses systemd EnvironmentFile syntax.
It is not a shell script. For example:

```ini
PORT=7317
OVIS_TELEMETRY=0
```

Keep this file private if it contains a token. Restart the service after a
configuration change or an APT upgrade:

```bash
systemctl --user restart ovis-server
```

To use a laptop browser, start an SSH tunnel on the laptop:

```bash
ssh -L 7317:127.0.0.1:7317 USER@SERVER
```

Then open `http://127.0.0.1:7317` on the laptop. For phone access, configure
Tailscale or Ovis device pairing and relay access through the web interface.
See the [Ovis connection guide](https://github.com/devswha/ovis#your-pcs-anywhere).
A public connection needs authentication and HTTPS. This package does not change
network or Tailscale settings.

On a server, user services normally follow the login session. To keep the user
service running after logout, the operator can enable linger for that user.
This package does not enable it.

A prior user installation under `~/.local/bin` can take precedence over `/usr/bin`.
Check the command path before use. These packages do not remove user installations
or change user configuration.

## Size and verification

The inspected releases are Herdr 0.9.5, Herdr core 0.1.21, Herdr app 0.1.16,
and Ovis 0.5.9. Sizes vary by architecture and release. The upstream Ovis desktop
packages download about 206–218 MB. Their upstream Installed-Size values are about
572–576 MB. The repository index calculates its own payload-size estimate.
Shared Debian dependencies can require additional space.

The local Debian builds have these approximate sizes. MB uses 1,000,000 bytes.
The ranges cover amd64 and arm64.

| Package | Download | Installed files |
| --- | --- | --- |
| `herdr` | 10–11 MB | 28–30 MB |
| `herdr-core` | 3 MB | 8–9 MB |
| `herdr-app` | 35–36 MB | 96–100 MB |
| `ovis-desktop` | 206–218 MB | 572–576 MB |
| `ovis-server` | About 83 MB | About 169 MB |

The Herdr desktop total includes both `herdr-app` and `herdr-core`. Their combined
disk use is about 104–109 MB before shared dependencies.

Run the adapter regression tests from the project root:

```bash
bash tests/run.sh herdr herdr-core herdr-app ovis ovis-server
```

The tests use offline fixtures and real Debian package tools. They check release
selection, checksums, architecture, fixed paths, installed size, and update reuse.
Archive tests reject links and missing notices. Ovis tests check byte preservation
and index size estimates when upstream size metadata is missing or stale.

Real downloads were checked for both architectures. Static package checks do not
prove that desktop graphics, remote connections, or agent sessions work on a client.
Container builds, repository publication, and client runtime checks are separate
steps. No production repository or signing key is used by these checks.

The Ovis server tests also check the release manifest, terminal-helper record,
web archive validation, and required package dependencies. To run the real amd64
server and core with isolated configuration:

```bash
bash tests/ovis-server/test-runtime.sh \
    /absolute/path/to/ovis-server_VERSION_amd64.deb \
    /absolute/path/to/herdr-core_VERSION_amd64.deb
```

This check extracts packages under ignored `build/`. It checks loopback HTTP,
the web page, the Herdr core connection, and disabled application updates.
It installs no host files. The check retains its logs and stops its private core.
The real amd64 check passed with Ovis 0.5.9 and Herdr core 0.1.21.
Arm64 runtime behavior remains untested.
