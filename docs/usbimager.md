# USBImager packaging

The `usbimager` release stream follows the newest numbered stable release in
[upstream's binary checksum manifest](https://gitlab.com/bztsrc/usbimager/-/raw/binaries/sha256checksums.txt).
Versions are compared numerically, so 1.0.10 follows 1.0.9. Query selects that
release first, then emits targets only for its available requested architectures;
it does not fall back to an older release for a missing architecture. Unexpected
manifest data or failed downloads fail the stream.

| Architecture | Debian package | Official upstream artifact |
| --- | --- | --- |
| amd64 | `usbimager-gtk` | `usbimager_VERSION-amd64.deb` |
| arm64 | `usbimager-x11` | `usbimager_VERSION_uf-aarch64-linux-x11.zip` |

Both use the full read/write interface and provide the virtual package
`usbimager`. They conflict with each other and the original `usbimager` package
because they share the executable, icons, manual, and desktop paths. This is
unofficial Debian packaging of upstream binaries. Install the concrete variant
with `sudo apt install usbimager-gtk` on amd64 or `usbimager-x11` on arm64.
The adapter directory and persistent publisher stream remain `usbimager`.

The amd64 importer checks upstream package identity and preserves its application
files and control metadata, including any maintainer scripts, without executing
upstream code during the build. It rewrites the name, publisher fields, version,
maintainer, conflicts, virtual provision, and dependencies. The upstream 1.0.10
package declares only `udisks2`; this repack also declares its direct GTK 3,
GLib/GIO/GObject, libudisks2, and libc dependencies using Debian Trixie names.
Both variants target Debian 13 and require libc6 >= 2.41. The adapter validates
ELF architecture, known shared-library requirements, absence of custom library
search paths, and the Trixie GLIBC symbol baseline without target execution.

The arm64 archive has exactly `bin/usbimager` and the reviewed `share/` desktop,
icon, and manual files at its root. It is staged under `/usr`, with no search for
alternative archive roots. Embedded GNU Unifont avoids an external X11 font
requirement; its notices and OFL license are installed alongside the application
copyright. Archives containing links, special files, or unexpected paths fail.
Final permissions grant no setuid/setgid or device access privileges.

The GTK build uses udisks2 for disk access. The X11 build accesses devices
directly and needs appropriate device permissions or an explicitly privileged
launch. Installation does not add users to the `disk` group or change device
permissions. The upstream desktop launch command remains `/usr/bin/usbimager`.
An X11 display (or XWayland) is needed for the arm64 interface.

SHA256 verification uses the official manifest served over HTTPS, not an
independent signature. A manifest/artifact update race fails digest verification
and is retried next cycle. Upstream may replace binaries without changing their
version. Remote hashes do not participate in recipe change detection; such a
replacement alone does not rebuild an already-complete version. A reviewed
recipe change triggers the framework's next revision of current targets.

`Installed-Size` is recalculated from the final staged tree for both packages,
including when the imported size is absent or stale. Offline tests cover both
architectures, package/index metadata, required files, digest/metadata/layout
failures, selection, and repeat updates. Run `bash tests/run.sh usbimager` with
binutils and the standard publisher test tools; see [local tools](local-tools.md).

Arm64 compatibility is an exercise: there is no current arm64 consumer. Neither
offline tests nor ELF inspection establish desktop usability or actual USB disk
operations. Real desktop and disk-write verification remain separate from
packaging checks. Rebuild the publisher image to deploy the adapter; this change
does not deploy or publish live packages.
