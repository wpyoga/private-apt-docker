# libgit2 1.9 source rebuild

`packages/rebuild/libgit2-1.9/` follows stable 1.9.x releases packaged in
Debian sid. The reference packaging checkout is Debian's
[libgit2 repository](https://salsa.debian.org/debian/libgit2); the inspected
source revision is `1.9.7+ds-1` (upstream 1.9.7). Local checkouts under `temp/`
are investigation material and are not build inputs.

Query reads signed Debian source indexes through APT, selects the highest
stable `1.9.x+ds` source version, and downloads its descriptor and source
archives through APT's checksum verification. If sid no longer contains a
qualifying source, it emits no targets and retains stored packages. It never
switches to libgit2 2.x. Publisher versions retain the source revision, for
example `1.9.7+ds-1+local-1`.

The adapter rebuilds Debian's four static/shared, normal/experimental CMake
configurations against Trixie's dependencies. It retains Debian's symbols,
OpenSSL, SSH, GSSAPI, PCRE2, llhttp, licensing and multiarch layout. It adapts
the known debhelper 14 control file to Trixie's compat 13 and explicitly restores
the runtime dependency substitutions. Changed package names or compat versions
fail for review. Upstream test execution is disabled during cross builds;
offline publisher tests do not establish full libgit2 runtime correctness.

Outputs for amd64 and arm64 are:

- `libgit2-1.9`: normal shared library, SONAME `libgit2.so.1.9`.
- `libgit2-dev`: normal headers, static library, CMake and pkg-config metadata.
- `libgit2-experimental1.9`: Debian's separate SHA-256-enabled shared library.
- `libgit2-experimental-dev`: experimental development files and compatibility links.
- `libgit2-fixtures`: architecture-independent upstream test resources.

The two development packages conflict by Debian's design. Normal and
experimental shared libraries use separate filenames and symbol versions.
Every final package gets freshly calculated Installed-Size and publisher
metadata; exact development/runtime version dependencies remain intact.

Run `bash tests/run.sh libgit2-1.9` for offline selection, backport, layout,
size/index, architecture and repeat-update tests. Actual builds use the project's
`rebuild` Docker target with `TARGET_ARCH=amd64` or `arm64`; containers writing
host workspaces must use the host UID/GID. The toolchain includes target
development dependencies and an arm64 cross compiler. This follows the existing
amd64-server requirement.

Run `bash tests/libgit2-1.9/test-install.sh build/libgit2-1.9/amd64/output`
as the host user to check clean Trixie installation, normal and experimental
development package replacement, compilation through pkg-config and bare Git
repository creation. Installation and compilation happen in Docker image layers.
This native runtime check covers amd64; arm64 packages need static checks and
separate runtime validation on arm64 hardware.

The 1.9.7 validation outputs live under ignored
`build/libgit2-1.9/amd64/output` and `build/libgit2-1.9/arm64/output`, with named
logs under `build/libgit2-1.9/logs`. The native Docker installation check confirms
both variants report 1.9.7 and create a bare repository. Offline verification
covers nine adapter tests and 65 framework tests. Signed live publication needs
the operator's configured rebuild key; these local build and installation checks
do not publish packages.

Both architecture builds passed checks for package versions, exact development
dependencies, Installed-Size in packages and generated indexes, ELF machine types,
SONAMEs and host ownership. Source downloads, build logs and final packages are
retained; successful temporary extraction and staging trees are removed.

Rebuild and recreate the two rebuild services to deploy the adapter. Clients
using the rebuild repository can then run `sudo apt install libgit2-1.9`, or
`sudo apt install libgit2-dev` to compile against it. Live publication uses the
existing repository lock, signing key and revision rules.
