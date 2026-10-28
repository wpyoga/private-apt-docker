# Zed packaging and validation notes

## Source and package layout

The `zed` stream follows the latest stable release of
[zed-industries/zed](https://github.com/zed-industries/zed/releases/latest).
Official `zed-linux-x86_64.tar.gz` and `zed-linux-aarch64.tar.gz` archives map to
Debian amd64 and arm64. GitHub's asset SHA256 digest is required and verified.
The Debian package is an unofficial repackaging for Debian 13 (Trixie).

The adapter expects one fixed `zed.app/` tree containing the CLI, editor,
desktop entry, two icons, license notices, and nine known bundled libraries.
Links, special files, extra payload files, and changed library requirements fail
the build. Architecture and ELF dependency checks never execute target code.
The existing publisher selects Debian revisions and publishes one `zed` package
per architecture; no framework changes are needed.

The retained executables are `/usr/lib/zed/bin/zed` and
`/usr/lib/zed/libexec/zed-editor`. Their relative paths preserve the CLI's editor
discovery. The upstream private-library RPATH is removed with patchelf. No
bundled shared libraries are installed. Desktop files and icons use standard
`/usr/share` locations; upstream license notices are in `/usr/share/doc/zed/`.

## Debian libraries and the libXdmcp compatibility question

The inspected v1.25.3 archives bundle these ordinary shared libraries:

| Upstream library | Debian package |
| --- | --- |
| `libX11-xcb.so.1` | `libx11-xcb1` |
| `libXau.so.6` | `libxau6` |
| `libXdmcp.so.6` | `libxdmcp6` |
| `libxcb.so.1` | `libxcb1` |
| `libxcb-xkb.so.1` | `libxcb-xkb1` |
| `libxkbcommon.so.0` | `libxkbcommon0` |
| `libxkbcommon-x11.so.0` | `libxkbcommon-x11-0` |
| `libstdc++.so.6` | `libstdc++6` |
| `libbsd.so.0` | `libbsd0` |

Only libraries directly required by retained executables contribute to the
generated `Depends`. Debian packages supply their own transitive dependencies.
GLib, ALSA, glibc, and GCC support libraries also come from Debian. Vulkan,
Wayland, font discovery, certificates, and URL opening have explicit runtime
dependencies because ELF `DT_NEEDED` does not describe every runtime load.
Desktop portal packages and a Vulkan driver are recommended; a desktop-specific
portal backend and a working Vulkan-capable GPU remain client requirements.

**Important compatibility note:** in both official architectures, the bundled
chain is `Zed -> libxcb -> libXdmcp -> libbsd`. Debian 13's `libXdmcp.so.6` does
not have a `DT_NEEDED` entry for `libbsd.so.0`. Consequently, `libbsd0` is neither
a direct Zed dependency nor part of this replacement X11 dependency chain.
This is a difference between builds of libXdmcp, not evidence that libbsd is a
Zed-specific library or that it should be bundled independently.

Initial v1.25.3 investigation found all strong imported symbols, including
symbol versions, in the Debian runtime on both architectures. The checks used
the Trixie amd64 host and checksum-verified Debian arm64 packages. The amd64
editor also passed `ldd -r` without bundled libraries and the CLI reported the
expected version. These are ABI and loader checks, **not proof of complete X11
or Wayland behavior**. Using Debian's libXdmcp remains subject to the laptop
desktop test below. Do not silently restore upstream libraries if that test
fails: record the failure and establish which library or build option matters.

The adapter's dependency map rejects unknown SONAMEs. It also rejects retained
binaries requiring GLIBC, GLIBCXX, or CXXABI versions newer than the declared
Trixie baseline. It does not reproduce the investigation's full symbol-provider
comparison on every build; new releases still need desktop validation when
upstream library assumptions change.

## Updates

`/usr/bin/zed` is a small Bash wrapper. It exports
`ZED_UPDATE_EXPLANATION='Update Zed using APT.'` and execs the real CLI, forwarding
arguments and exit status. Both desktop launch actions use `zed` and therefore
the same wrapper. The variable disables automatic checks and makes manual
update checks display the APT explanation. No shell profile or session-wide
environment files are installed, and no updater machine code is patched.

Zed has no system-wide settings layer in this release. Its
`global_settings.json` is per-user, and `auto_update: false` alone does not
disable the manual update action. The unmodified updater can otherwise install
a second copy under `~/.local`, even when the original binary is under `/usr`.
Running internal executables directly bypasses the wrapper's update policy.

## Validation and laptop acceptance

Offline regression tests use small real ELF fixtures for both architectures,
inspect ARM headers without executing them, build real Debian packages, and
check the published `Installed-Size`. They cover release validation, archive
layout and links, dependencies, symbol baseline changes, the updater wrapper,
desktop actions, revision reuse, and later availability of an architecture.
Run them with `python3 -m unittest discover -s tests -p test_zed.py -v`.

Local v1.25.3-1 packages were built from the verified official archives for both
architectures. The amd64 package passed APT installation in an isolated Debian
13 container, `ldd -r` against system libraries, unprivileged `zed --version`,
desktop-file validation, and APT removal. Desktop validation emitted only an
upstream category hint. No arm64 execution or GPU/desktop test has been done.
The local test packages use a generic validation maintainer; publisher builds
use the operator's configured `MAINTAINER`.

Investigation downloads, the matching source checkout, and local validation
outputs belong under ignored `build/zed-investigation/`. Do not use production
repository data or signing keys for these checks.

After installation from the private repository, or using
`sudo apt install ./zed_VERSION_amd64.deb` for a local package, test on the laptop:

1. Run `zed --version` and `ldd -r /usr/lib/zed/libexec/zed-editor`.
2. Open Zed from the desktop menu and the terminal; open a file whose name
   contains spaces and exercise the desktop's New Workspace action.
3. Test X11 and Wayland where available. Check keyboard input, clipboard,
   fonts, file dialogs, URL opening, and rendering. For an X11 launch from a
   Wayland session, use `WAYLAND_DISPLAY='' zed --foreground` with XWayland
   available. This is the pending practical libXdmcp compatibility check.
4. Select Check for Updates and confirm that it displays the APT explanation.
   Check that no second application bundle is created under `~/.local/`.
5. Confirm `apt show zed` reports an installed size and that removal leaves
   personal settings intact.

Publisher container rebuilds and production publication are separate deployment
steps. Offline tests do not establish GUI functionality on the target laptop.
