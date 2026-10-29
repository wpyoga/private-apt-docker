# Debian package index fixture

`Packages` contains the 33 unmodified `gimp-help-*` stanzas captured from
<https://deb.debian.org/debian/dists/sid/main/binary-amd64/Packages.xz>
on 2026-10-28. They describe Debian version `3.2.0-3.1`.

The production query regression uses the actual adapter configuration and query
hook with these records. It verifies all declared names and the dotted Debian
revision without fetching the large manual archives. Synthetic package fixtures
separately exercise imports, dependencies, version upgrades, and payload checks.
