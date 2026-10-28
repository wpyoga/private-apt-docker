# Project-local Debian tools

Development tools used only by this project can live under ignored
`build/tools/`, without sudo, Docker, or system package installation. The current
setup targets the Debian 13 (Trixie) amd64 development host. These are host tools;
`readelf` can inspect arm64 binaries without executing them.

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
