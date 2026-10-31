# Patched xfce4-screensaver

The `packages/rebuild/xfce4-screensaver/` adapter follows the newest Debian
Trixie source from trixie, trixie-updates and trixie-security. APT verifies signed
repository metadata and source checksums. The initial verified source packaging
is [4.18.4-1](https://packages.debian.org/source/trixie/xfce4-screensaver).
It builds the single `xfce4-screensaver` binary package for amd64 and arm64,
retaining Debian dependencies, PAM configuration, autostart and D-Bus integration.

Put your patches under `packages/rebuild/xfce4-screensaver/patches/` and list their
filenames in `patches/series`, one per line in application order. The series is
initially empty. Blank lines and comments starting with `#` are ignored.
Each build extracts a fresh Debian source tree and applies the series with quilt
and zero fuzz. Patch changes allocate a new stored-package revision, for example
`4.18.4-1+local-1`; subsequent Debian source releases start their own history.

The adapter enables maintainer mode to regenerate files affected by patches.
It expects Debian rules without a custom configure override and fails if one
appears. For arm64 it marks the existing `xfce4-dev-tools` dependency `:native`
because this tool runs on the amd64 builder. Missing dependencies or changed
source layouts fail the stream while keeping previously published packages.

Both existing rebuild toolchain images include the screensaver dependencies.
After adding your patch and series entry, rebuild and recreate the services:

```sh
docker compose up -d --build --force-recreate rebuild-amd64 rebuild-arm64
```

Use the existing rebuild repository and key. Clients can prefer the local build
with this APT preference and then install `xfce4-screensaver`:

```text
Package: xfce4-screensaver
Pin: release o=rebuild
Pin-Priority: 990
```

Offline regression tests check source versions, both architecture build paths,
patch handling, fixed integration paths, and recalculated Installed-Size in the
package and APT index. Real source compilation, installation, screen locking and
resume behavior require separate validation; no desktop behavior is established
by fixture tests. See [terminal deployment notes](xfce4-terminal.md) for the
shared toolchain, host ownership and signing setup.
