# GIMP help 3.2 packaging and validation notes

## Source and release selection

The `gimp-help-3.2` stream imports precompiled user manuals from Debian sid's
[package index](https://deb.debian.org/debian/dists/sid/main/binary-amd64/Packages.xz).
It is independent of the GIMP application stream and its API documentation.
Clients do not need a sid APT source.

The adapter declares 32 language packages and `gimp-help-common` in
[its configuration](../packages/gimp-help-3.2/config). Each query requires the
complete declared set at one consistent Debian version. Accepted versions have
the form `3.2.NUMBER-REVISION`, with a Debian revision containing letters,
digits, periods, plus signs, or tildes. This includes non-maintainer uploads
such as `3.2.0-3.1`, tracked as `1:3.2.0+deb3.1`. Missing packages,
conflicting records, mixed versions, unexpected architectures, invalid SHA256
values, and changed download paths fail discovery. A newer GIMP series requires
a separate adapter.

Although discovery reads the amd64 index, every selected package must declare
`Architecture: all`. The framework stores each package once and includes it in
both amd64 and arm64 indexes. The build reuses its completed packages within the
cycle when processing the other architecture.

## Versions and installation

Debian source version `3.2.0-3` becomes tracked version `1:3.2.0+deb3`; the
publisher adds its recipe revision, producing `1:3.2.0+deb3-1` initially.
The epoch permits upgrades from manuals previously numbered after the GIMP
application. `X-Upstream-Version` records the original Debian version.

A new manual source revision triggers an independent update. A help recipe
change rebuilds the current manuals without rebuilding GIMP. Existing repository
packages remain stored.

After publication, install a language with `sudo apt install gimp-help-en`, or
select another declared language package. Each language depends on the exact
repackaged version of `gimp-help-common`. The GIMP application only suggests
manuals; `libgimp-3.0-doc` contains the separate API reference.

## Import validation

The build verifies each download against the selected index SHA256 and checks
package name, original version, architecture, and dependencies. Language
packages must depend only on the matching common package; the common package
must have no Depends value.

Manuals retain their data, licensing notices, and safe relative payload links.
Regular payload files must live under the expected GIMP help, documentation,
doc-base, or lintian directories. ELF files, special file types, absolute links,
and links escaping the staging tree are rejected. The common copyright notice
and language help directory are required.

The importer removes the known legacy post-install migration scripts from the
German, English, French, and Swedish packages. Other unexpected maintainer files
fail validation. Upstream scripts are not executed while repackaging.

The importer rewrites version, maintainer, publisher fields, and the exact common
package dependency. It recalculates `Installed-Size` from the final staged tree,
excluding `DEBIAN/`, even when upstream supplied a value.

## Verification

Run the offline adapter regression tests from the project root:

```bash
bash tests/run.sh gimp-help-3.2
```

The fixtures exercise imports, version selection and source updates, independent
recipe rebuilds, revision reuse, changed downloads, unexpected dependencies or
architectures, dotted non-maintainer revisions, and rejection of a newer release
series. A captured Debian index also checks the production query hook against
all 33 names in the actual adapter configuration. They check missing and
stale upstream `Installed-Size`, its published index value, and inclusion in both
architecture indexes. Import fixtures use a reduced language set; they do not establish
live availability of all declared translations or in-application help browsing.

Container rebuilds, live publication, and desktop help browsing are separate
verification steps.


For live downloads, both architectures, all declared help packages, and signed
index generation in the publisher image, run:

```bash
bash tests/gimp-3.2/test-publisher.sh
```

This optional coordinator uses the Compose limits (256 MiB memory and 128
processes), dropped capabilities, and the host UID/GID. It uses isolated storage
and a throwaway signing key under `build/`, retaining logs, downloaded sources,
packages, and cgroup statistics. `ARCHES=amd64` selects only amd64. It does not
start the deployed service or use operator `.env` settings. Completed stored
packages can be reused with `GIMP_PUBLISHER_CONTEXT=/absolute/path/to/context`.
Failed extraction or staging trees must be inspected before removing them for a
retry; the adapter deliberately refuses to reuse them.
