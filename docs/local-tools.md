# Project-local Debian tools

Development tools used only by this project can live under ignored
`build/tools/`, without sudo, Docker, or system package installation. The current
setup targets the Debian 13 (Trixie) amd64 development host. These are host tools;
`readelf` can inspect arm64 binaries without executing them.

This arrangement was explicitly chosen because these tools were needed by this
project and the operator did not want a system installation for unrelated
projects or repeated Docker requests for ordinary inspection and regression
checks. Keep activation scoped to a subshell; do not add it to a shell profile.
The USBImager work and original verification evidence are preserved in the
[USBImager handoff](usbimager-handoff.md).

The USBImager and framework checks need `dpkg-scanpackages` from `dpkg-dev` and
`readelf`, `objdump`, and `ar` from `binutils`. `apt-ftparchive` from `apt-utils`
is also required for publication tests and is already installed on this host.

## Download and extract

Run from the project root as your normal user. APT uses the host's configured
repositories and verifies downloads against its package indexes. This downloads
and extracts packages; it does not run maintainer scripts or register packages
in the system package database.

```bash
mkdir -p build/tools/downloads build/tools/root build/tools/logs
(
    cd build/tools/downloads
    timeout 120s apt-get download \
        dpkg-dev libdpkg-perl \
        binutils binutils-common binutils-x86-64-linux-gnu \
        libbinutils libctf0 libctf-nobfd0 libgprofng0 libsframe1 make
) > build/tools/logs/download.log 2>&1

for PACKAGE_FILE in build/tools/downloads/*.deb; do
    dpkg-deb --extract "$PACKAGE_FILE" build/tools/root
done > build/tools/logs/extract.log 2>&1
```

`libdpkg-perl` supplies the Perl modules used by `dpkg-scanpackages`; the extra
binutils packages supply its commands and shared libraries. `make` is a missing
dependency of `dpkg-dev`. This setup reuses the host's Perl, libc, libgcc,
libstdc++, libjansson, zlib, zstd, tar, bzip2, xz, and patch. It is not a complete
standalone Debian environment. Recheck dependencies on a different host.

The verified local versions are dpkg-dev/libdpkg-perl 1.22.22, binutils and its
libraries 2.44-3, and make 4.4.1-2. Repeating the download command selects the
versions currently available in the host's APT indexes. Retain useful downloaded
packages and logs; avoid mixing old and new binutils library sets when updating.

## Use for a command

Create the ignored activation file once:

```bash
cat > build/tools/env.sh <<'EOF'
# Source after setting FRAMEWORK_DIR to the project root.
: "${FRAMEWORK_DIR:?FRAMEWORK_DIR must point to the project root}"
export PATH="$FRAMEWORK_DIR/build/tools/root/usr/bin:$PATH"
export PERL5LIB="$FRAMEWORK_DIR/build/tools/root/usr/share/perl5${PERL5LIB:+:$PERL5LIB}"
export LD_LIBRARY_PATH="$FRAMEWORK_DIR/build/tools/root/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
EOF
```

Activate it inside a subshell so other projects and your parent shell keep their
existing environment:

```bash
(
    export FRAMEWORK_DIR="$PWD"
    source build/tools/env.sh
    timeout 5m bash tests/run.sh --framework
) > build/tools/logs/framework.log 2>&1
```

Wait for the command to finish, then inspect the log. The runner reports the
separate detailed regression log. Use the same subshell for an adapter selector
such as `bash tests/run.sh usbimager`. Other adapters can need additional tools;
see the README's test requirements. This setup does not change the publisher
container or the dependencies installed by its Dockerfile.

## Retained local setup and evidence

The original setup downloaded eleven Debian archives into
`build/tools/downloads/` and extracted them into `build/tools/root/`. The
activation file is `build/tools/env.sh`. None of these paths is tracked by Git;
the commands above recreate the setup after a checkout or deletion of `build/`.
No package was installed into the system database and no package maintainer
script was executed during extraction.

The original verification ran `dpkg-scanpackages`, `readelf`, `objdump`, `ar`,
`make`, and a Perl `Dpkg` module import successfully. It also generated an index
from the downloaded USBImager Debian package and inspected its real ELF metadata.
With these tools enabled, the then-current framework suite passed all 46 tests.
After the architecture-specific package tests were added, it passed 51 tests.
These are historical October 28, 2026 results, not counts for the current suite.

Retained logs under `build/tools/logs/` are:

| File | Purpose |
| --- | --- |
| `download.log` | Original restricted-network download failure |
| `download-retry.log` | Successful Debian downloads |
| `extract.log` | Package extraction output |
| `verify.log` | Resolved command paths and tool versions |
| `package-tools.log` | Real package indexing and ELF inspection |
| `Packages` | Index generated for the tool verification |
| `framework.log` | Original framework test coordinator output |

The download failure was DNS/network access in the restricted environment; the
same download completed with permitted network access. Extraction and verification
ran as the host user. A future download failure does not imply that Docker or
root installation is needed. Obtain network permission for downloads when the
execution environment requires it.

This directory supplies the listed commands, not every tool for every adapter.
For example, it does not add GTK development libraries, a compiler, patchelf,
SquashFS tools, or desktop test facilities. Consult the current README before
selecting broader tests. The installed local tools were found again during the
November 13, 2026 documentation handoff; that inspection did not reinstall them
or rerun their original regression suite.
