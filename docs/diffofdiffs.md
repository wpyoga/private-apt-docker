# diffofdiffs

`packages/rebuild/diffofdiffs/` builds the official
[diffofdiffs](https://github.com/ctrliq/diffofdiffs) source release into one Debian
package named `diffofdiffs` for amd64 and arm64. The reviewed version is
[v1.1.0](https://github.com/ctrliq/diffofdiffs/releases/tag/v1.1.0), commit
`0ee3188313eb76722387b81d8852da207926ff77`.

Query checks GitHub's latest stable release. It fails clearly when that tag is
not the reviewed version; it does not silently fall back to an older release.
Review a new release and update `source.json` to advance this stream. Packaging
changes rebuild the current reviewed release using normal publisher revisions.

Production downloads the release tarball; it never clones the repository or
uses local checkouts under `temp/`. Upstream has no release checksum asset.
The adapter independently reconstructs Git blob/tree hashes from every archive
file and its executable bit, comparing the root tree with the reviewed tree
in `source.json`. This verifies the source contents against the selected release
without a Git checkout. It also validates VERSION and rejects unexpected roots,
duplicate paths, path traversal, links and special files before extraction.
The verified archive's SHA256 is recorded in the per-stream workspace and
checked again before compilation. These hashes establish integrity against the
reviewed source; they are not an upstream detached signature.

The private build dependency is `libgit2-dev >= 1.9.1`, supplied by the
`libgit2-1.9` stream. The upstream minimum fixes relative paths in nested Git
alternate object stores, as described in its README and covered by its
`gitread-alternates-recursive` test. The inspected Trixie package
`1.9.0+ds-2+deb13u1` lacks that fix. No newer compiler or Python version is introduced.
Use the [host rebuild launcher](build-dependencies.md#running-isolated-builds)
for dependency-enabled builds. The base toolchain image does not install its
own private outputs; isolated consumer images install the selected packages.

The adapter uses upstream Makefile staging with `DESTDIR` and `prefix=/usr`,
Debian hardening flags, native gcc on amd64 and the existing arm64 cross compiler.
It checks the ELF machine and normal `libgit2.so.1.9` linkage without executing
target binaries. `dpkg-shlibdeps` derives shared-library dependencies; an explicit
`libgit2-1.9 (>= 1.9.1)` additionally preserves the correctness requirement which
symbol versions alone cannot express. Python embeds HTML assets at build time;
neither Python nor the Git CLI is a runtime dependency.

The package installs `/usr/bin/diffofdiffs` and documentation under
`/usr/share/doc/diffofdiffs`, including README, GUIDE, LICENSE, NOTICE, third-party
licensing and bundled-header notices. There is no wrapper, desktop integration
or bundled shared library. Installed-Size is calculated from the final staged
payload and tested in both the package and published indexes.

Run all verification for this adapter with one host command:

```sh
bash tests/diffofdiffs/verify.sh
```

It runs offline adapter regressions, downloads/reuses the verified release
tarball, builds both architectures through isolated framework workers, checks
indexes and repeat-cycle reuse, and installs the native package in a Docker image.
The native check exercises version output, patch comparison, standalone HTML and
read-only Git tree mode, then runs upstream's complete normal `make check` suite,
including nested alternates. It requires existing architecture rebuild images
and verified libgit2 outputs under `build/libgit2-1.9/{amd64,arm64}/output`.
No production repository or signing key is used.

The v1.1.0 test runner calls `kill -l XFSZ`, which Dash rejects on Trixie.
The installation test prefixes the two Makefile runner commands with Bash.
Its inner `sh -c` resource-limit wrappers remain unchanged. This is confined to
the disposable test source tree; packaged application sources are unmodified.

Final artifacts are exported to `build/diffofdiffs/ARCH/output/`; named logs live
under `build/diffofdiffs/logs/`. Native installation and execution cover amd64.
Arm64 compilation, ELF inspection and dependency metadata are checked without
target execution; arm64 hardware validation remains separate. These checks do
not deploy or publish to the live repository.

## Verified build and continuation

On 2026-11-14, `bash tests/diffofdiffs/verify.sh` completed successfully with all
eight planned checks: offline adapter regressions, both architecture build/index
and reuse checks, native installation smoke tests, upstream's normal regression
suite, Bash syntax, Python syntax and diff checks. The upstream suite used the
test-only Bash workaround described above. The private dependency was the rebuilt
libgit2 `1.9.7+ds-1+local-1`.

The resulting files are:

- `build/diffofdiffs/amd64/output/diffofdiffs_1.1.0-1_amd64.deb`
- `build/diffofdiffs/arm64/output/diffofdiffs_1.1.0-1_arm64.deb`

The downloaded release tarball's SHA256 was
`1a249b89da49a0790c3589405cdd4be3d8d10dbbac5ad6fe36e90c70998ee91b`.
`build/diffofdiffs/logs/verification.log` records the overall successful run;
the other named logs preserve build, installation and upstream test details.
These ignored artifacts may need regeneration in another checkout.

Live APT publication was not performed or verified by this work. Deployment uses
the host rebuild launcher and existing signing configuration; follow the linked
build-dependency deployment guide. Arm64 installation and runtime checks on real
hardware remain unverified. Current code and fresh verification take precedence
over this dated result after later changes.
