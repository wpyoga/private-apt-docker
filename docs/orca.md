# Orca (Stably AI)

`packages/repack/orca/` follows the latest stable release of
[stablyai/orca](https://github.com/stablyai/orca/releases/latest). It selects the
exact `orca-ide_VERSION_amd64.deb` and `orca-ide_VERSION_arm64.deb` assets and
verifies GitHub's SHA256 digests. Missing architectures are skipped and retried;
prereleases and AppImage/server assets are not selected.

The package is **orca-ide**, preserving upstream's deliberate distinction from
Debian's `orca` screen reader. The stream identity is `stably-orca`. Upstream
`1.4.258` becomes `1.4.258-1`; packaging changes use the normal stored-package
revision rules. This is unofficial Debian packaging of official Stably AI binaries.

## Packaging decisions

The official 1.4.258 packages contain world-writable Electron executables and
resources, including `/opt/Orca/orca-ide` and `chrome-sandbox`. Upstream's
`postinst` enables the sandbox's setuid bit. Consequently this adapter repacks
rather than redistributes those bytes unchanged. It removes group/other write
permissions and existing special permission bits before building root-owned
packages. Executable bits remain; upstream `postinst` can enable the sandbox
when the client installs the package.

The adapter preserves upstream dependencies, bundled Electron/runtime resources,
desktop entry, icons, CLI shim, and maintainer scripts. It replaces Version,
Maintainer and Installed-Size and adds publisher provenance. Installed-Size is
recalculated from the final staged tree, excluding DEBIAN. The source's MIT notice
is added under `/usr/share/doc/orca-ide/copyright`; upstream Electron/Chromium
notices are retained. Upstream's control field currently says `License: unknown`.

Validation reads the archive without running target code. It checks package name,
version and architecture, fixed executable/CLI/ASAR/desktop/icon/documentation
paths, and the ELF class and machine of the main executable and sandbox helper.
The verified payload has only regular files and directories; links, special
files and unsafe paths are rejected before extraction and permission changes.
Changed upstream layouts require an explicit adapter update.

## Installation and runtime

Rebuild the repack publisher image and complete an update cycle to publish it:

```bash
docker compose up -d --build codex-repo-updater
```

With the [repack APT repository](../README.md) configured on the client:

```bash
sudo apt update
sudo apt install orca-ide
orca-ide
```

Upstream's install script registers `/usr/bin/orca-ide` as a link to
`/opt/Orca/resources/bin/orca-ide`. The desktop entry starts
`/opt/Orca/orca-ide`. The package does not use `/usr/bin/orca`.
The preserved scripts execute on client installation/removal, never during builds.

The 1.4.258 dependency list includes GTK 3, NSS, GBM, libsecret, ALSA, accessibility
libraries, Python 3/GI, xdotool, xclip and Xvfb; `libappindicator3-1` is recommended.
APT remains responsible for resolving these upstream dependencies. Bundled agents,
application settings, authentication and runtime update behavior remain upstream
behavior; this adapter does not rewrite JavaScript or credentials.

## Verification

Official release 1.4.258 was inspected on 2026-11-14. SHA256:

| Architecture | Upstream Debian archive SHA256 |
| --- | --- |
| amd64 | `cc700aa5e15742b1ba2944e9d48a82632611d6e32ac053d1f54bbe81a5ff01ea` |
| arm64 | `c20705a2287e86b15372d62ca9a89632de26206ed506986384cf359272062400` |

Run `bash tests/run.sh orca` for offline fixtures covering both architectures,
permissions, integration preservation, missing/stale Installed-Size and published
index values, revisions/retries, integrity checks and rejected metadata/layouts.
Both official 1.4.258 artifacts were successfully repacked and their resulting
archives checked for root ownership and absence of group/other write or special
permission bits. Installed-Size matched the generated index: 694972 KiB on amd64,
685904 KiB on arm64. All 12 offline tests passed, along with Bash syntax and diff
whitespace checks. The local live builds use a test maintainer and placeholder
recipe checksum; production packages must be built by the publisher.

Live artifact downloads and build logs are retained under ignored
`build/orca-investigation/`. Static builds do not establish successful installation,
GUI/headless launch, agent operation, or compatibility with a particular desktop.
No production publication is performed by these checks.
