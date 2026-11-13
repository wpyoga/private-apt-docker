# GIMP startup, dependency ownership, and Debian customization handoff

Recorded on 2026-11-13 from the 2026-10-27 investigation and implementation,
with current source paths checked against this checkout. This document preserves
the decisions and evidence needed without the original conversation. Historical
test results below were not rerun while writing this document.

Read [maintained GIMP notes](gimp-3.2.md) for the complete application design,
[earlier investigation history](gimp-3.2-investigation-history.md) for library
replacement and codec experiments, and [help packaging notes](gimp-help-3.2.md)
for the now-independent manual stream. This handoff concerns the startup warning,
update policy, dependency placement, example plug-ins, and personal preferences.

## Current state and scope

The agreed changes remain implemented in `packages/repack/gimp-3.2/`:

- APT supplies updates. The system `gimprc` disables background update queries,
  and package release metadata disables the upstream update channel even when
  a pre-existing user profile enables update checks.
- Each binary package declares the external libraries imported by its own ELF
  files, plus explicitly assigned requirements that ELF inspection cannot find.
- JavaScript and Lua goat examples and their extension registration entries are
  omitted. The `gjs` dependency is removed. C, Vala, and Python examples remain.
- MNG support remains and uses Debian's `libmng1`. No ILBM feature is fabricated
  when the upstream AppImage does not contain the corresponding plug-in.
- `gvfs-backends` is suggested for optional remote-file access.
- Welcome-dialog suppression is a personal user setting, not a package default.

The original implementation was verified locally and was not committed,
published, deployed, or installed on the host by that work. Later repository
changes have incorporated and moved its source. This statement is historical;
it does not establish the current production deployment or the user's current
desktop settings. Check those separately before planning an upgrade or rollout.

The old `packages/gimp-3.2/` directory became
`packages/repack/gimp-3.2/`. Its documentation moved out of the adapter into
`docs/gimp-3.2.md`, so general documentation changes do not cause package rebuilds.
At implementation time the adapter built eight application packages and 33
manual packages together. Today the application emits eight packages and
`gimp-help-3.2` independently emits the 33 manuals. The old count of 41 outputs
per architecture must not be used as today's application build expectation.

## Original report and diagnosis

The user reported that the first launch of the repacked GIMP 3.2 succeeded, but
the second launch printed:

```text
gimp_check_updates_callback: loading of https://www.gimp.org/gimp_versions.json failed: The specified location is not supported

Perhaps you are missing GIO backends and need to install GVFS?
```

This is a failure to retrieve upstream release metadata through GIO. It is not
by itself evidence of damaged image data or a corrupt user profile. Having
`libgio-2.0.so.0` available does not guarantee that a remote URI backend is
available. Debian's `gvfs-backends` contains `gvfsd-http`; remote support also
depends on working GIO/GVFS integration in the user's desktop session.

The inspected upstream `app/gimp-update.c` explains the timing: the first launch
after a version upgrade displays the welcome dialog and skips the update query.
A later launch can perform that query. Therefore the first successful launch
did not prove that the HTTPS backend worked. This source explanation is stronger
than the initial suggestion that the background query simply happened later.

An initial troubleshooting suggestion was to install `gvfs gvfs-backends`, quit
GIMP completely, and reopen it. The corresponding desktop-session diagnostic is:

```bash
gio cat https://www.gimp.org/gimp_versions.json
```

There is no recorded result establishing that the user installed those packages
or ran this command. The final solution chosen for the package was to disable
upstream update checks and rely on APT, rather than require remote-file support
just to silence this warning. GVFS remains useful for intentionally opening
remote images.

## APT dependency discussion and final decision

The user's `apt show gimp -a` compared:

| Property | Original repack | Debian package shown by the user |
| --- | --- | --- |
| Version | `3.2.6-1` | `3.0.4-3+deb13u11` |
| Reported Installed-Size | 107 MB | 32.1 MB |
| Download-Size | 38.2 MB | 6,550 kB |
| External dependencies | Mostly behind `gimp-bundled-runtime` | Mostly directly on `gimp` |
| Optional GVFS | Initially omitted | `Suggests: gvfs-backends` |

The old repack's direct dependencies were its matching private runtime, data,
libgimp and typelib packages, plus libheif and its six codecs. The private runtime
package carried a broad collection of external libraries, interpreters and
resources, including requirements belonging to the application itself.

APT installs dependencies transitively. A shorter main-package list does not
reduce the installed dependency set, download size, memory use, or disk usage.
It also does not explain the different application sizes in this comparison:
the upstream builds, versions, payloads and package splits differ. No controlled
size attribution was performed in this work.

The accepted arrangement follows the contents of each binary package:

- `gimp` declares requirements of its executables, plug-ins, scripts and resources.
- `libgimp-3.0-0` declares requirements of its shared libraries.
- `gimp-bundled-runtime` declares requirements of its private Babl/GEGL libraries
  and modules.
- The tool and development packages retain their own relationships and any
  applicable external requirements.
- The same Debian dependency may legitimately appear on several packages.
  Moving everything exclusively to `gimp` would leave independently installable
  libraries without complete requirements.

Debian normally calculates shared-library relationships with `dpkg-shlibdeps`
and adds explicit non-ELF requirements. The comparison consulted Debian's GIMP
and libgimp packages, and Inkscape plus Poppler GLib: both an application and one
of its library dependencies may independently declare Cairo and FreeType.
This repack instead uses a reviewed SONAME map so builds do not depend on which
libraries happen to be installed on the build host.

`Depends` is required for an ordinary installation. APT normally also installs
`Recommends`. It does not normally install `Suggests`; explicit options or local
APT configuration can change those defaults. Consequently Debian's GVFS
suggestion never guaranteed an installed HTTPS backend. A suggestion alone also
does not prove that update checks were disabled; the Debian build rules supplied
that evidence.

Useful client inspection commands are:

```bash
apt show gimp -a
apt show gimp-bundled-runtime
apt-cache depends gimp
apt-cache depends gimp-bundled-runtime
```

## What ELF inspection discovers, and what it cannot discover

The current implementation is in
[inspect-bundle.py](../packages/repack/gimp-3.2/inspect-bundle.py), with the
reviewed [dependency map](../packages/repack/gimp-3.2/runtime-dependencies).

The staged inspector:

1. Reads every regular staged file's ELF magic, skipping symlinks and non-ELF
   resources. It validates ELF64, byte order and target machine without executing
   target code.
2. Uses `readelf --dynamic --wide` to inspect `SONAME` and `NEEDED` entries.
   This includes executables, private libraries, and plug-in/module ELF files.
3. Collects SONAMEs supplied inside the staged package family and recognizes the
   expected architecture loader. Existing exact-version package relationships
   supply internal package dependencies; the generated report covers external
   providers, not a new automatic solver for all internal package relationships.
4. Maps every remaining imported SONAME to an explicit Debian dependency
   expression. Unknown external SONAMEs and conflicting providers fail with an
   error naming the library and offending file.
5. Assigns external requirements to the binary package containing that ELF file.
   Sets deduplicate requirements within each package without removing necessary
   duplication across packages.
6. Adds reviewed non-ELF requirements to their explicitly named package.
7. Writes `WORKSPACE/dependencies-ARCH.json`, mapping package names to dependency
   strings, and `WORKSPACE/elf-ARCH.paths0`, the NUL-separated ELF manifest used
   for path patching. The build adds the external strings to control metadata.

The map has three pipe-separated columns:

```text
# Debian dependency | expected SONAMEs | owner
libmng1|libmng.so.1|auto
libheif1 (>= 1.19.8)|libheif.so.1|auto
python3-gi||gimp
libssl3t64||gimp-bundled-runtime
```

`auto` is valid for linked SONAME rows. A blank SONAME field requires an actual
staged binary-package name, which owns the explicit indirect requirement.
These workspace reports are inspection products, not revision counters or stored
checksum sidecars. The normal embedded recipe checksum and stored packages still
determine publisher revisions.

There are two different dynamic-loading cases:

- A plug-in loaded at runtime is itself an ELF file. Its own `DT_NEEDED` entries
  are discoverable by scanning that file even when the main executable does not
  import those libraries.
- Code can call `dlopen` or `g_module_open` with a name computed at runtime.
  That name need not occur in `DT_NEEDED`, or even as a complete literal string.
  The same limitation applies to GI typelibs, interpreter imports, codec modules,
  external helper programs, fonts and icons. ELF scanning cannot discover these
  requirements completely.

Source and configuration review, known layout validation and explicit map rows
cover the latter cases. The six HEIF codecs, Python GI packages, SVG resources,
fonts and icons are examples. Strings searches can give investigation clues but
are not proof of dependency completeness. Targeted runtime tests complement the
static checks; a successful scan does not establish every feature works.

## Debian packaging investigation

The user requested whole-repository inspection rather than repeated individual
file downloads. Debian's GIMP source package/repository is sufficient for this
comparison because it includes upstream source and the `debian/` packaging tree.
A second upstream clone is not required just to inspect configuration behavior.

The investigation read published rules for `3.0.4-3+deb13u11` and `3.2.6-1`.
The eventual Debian Git checkout was at short commit `bc1f38c`, releasing
`3.2.6-2`. Findings must be attributed to those versions, rather than assumed to
describe every future Debian release. That checkout is no longer available here.

| Debian choice observed | Decision for this AppImage repack |
| --- | --- |
| `-Dcheck-update=no` in both inspected release lines | Reproduce the update policy through runtime/system metadata; do not rebuild GIMP. |
| JavaScript disabled and Lua false | Omit their exact installed goat-example files and registration entries. |
| ILBM disabled | Preserve whatever the official AppImage actually provides instead of copying this feature restriction. |
| MNG explicitly disabled in 3.0.4; no equivalent explicit disable in the inspected 3.2.6 rules | Retain upstream MNG and use the Debian provider. |
| Debian bug-reporting URL, architecture-specific installation paths | Keep existing native repack paths; do not change the compiled bug-report URL. |
| Compiler hardening and temporarily disabled LTO | Skip; reproducing compiler options requires rebuilding. |
| GExiv2 0.16 compatibility and introspection patches | Skip source patches; preserve libraries and typelibs compatible with the actual upstream binaries. |
| Image-loader security and correctness backports | Skip source modification in this task; do not claim an AppImage contains a Debian fix unless separately established. |
| Documentation, test settings and symbol checks | Packaging/build-process context, not runtime settings that can simply be toggled in an existing binary. |

The JS comment described an example being installed without a corresponding
menu button. Lua was described as experimental and disabled upstream by default,
with a similar example/menu issue. These findings concerned the shipped examples;
they did not justify deleting Python support or all developer examples.

The inspected 3.2.6-1 patch list contained:

- `meson-Allow-but-warn-building-with-gexiv2-0.16.patch`;
- `Do-not-require-gexiv2-0.14.patch`, including changing the GIR/VAPI dependency
  identifiers to the 0.16 names;
- `16742.patch`: overflow protection while reading PNGs in ICO;
- `2997.patch`: initialize SGI tables;
- `16753.patch`: buffer-size handling for PSP selections.

The inspected 3.2.6-2 tree additionally listed `CVE-2026-92248.patch` for PSD
thumbnail bounds, `16790.patch` for PVR rectangle bounds, `16971.patch` for 4BPP
TIM loading, `16788.patch` for a gimpressionist preset write, `3014.patch` replacing
unsafe string copies, and `3007.patch` fixing XWD parameter guards. Debian 3.0.4
also carried numerous older security backports; no full patch-porting exercise
was authorized or performed. These lists record what was inspected, not an audit
of the deployed AppImage's security coverage.

## Exact native startup policy

[configure-staging.py](../packages/repack/gimp-3.2/configure-staging.py) runs from
[stage.sh](../packages/repack/gimp-3.2/stage.sh) after copying GIMP data and config.

The system file is installed by `gimp-data` at `/etc/gimp/3.0/gimprc`:

```lisp
# Updates are delivered through APT.
(check-updates no)
```

The helper removes existing active `check-updates` assignments and appends the
new setting, retaining unrelated settings and comments. `gimprc` remains a Debian
conffile; handling an existing locally modified conffile is still an APT/dpkg
installation concern. The staged `/usr/etc/gimp` compatibility link resolves to
the native `/etc/gimp` tree used by the packaged layout.

The package also installs `/usr/share/gimp/3.0/gimp-release` with:

```ini
[package]
check-update = false
```

The helper reads the existing INI metadata, requires `[package]`, preserves other
fields such as `revision`, and sets this boolean. Rewriting through ConfigParser
does not promise byte-for-byte formatting or comment preservation. Upstream
`app/gimp-version.c` reads this package policy; `app/gimp-update.c` checks it along
with the user preference. This second layer prevents an existing profile's
`(check-updates yes)` from restoring upstream automatic checks.

The source inspector requires the expected `gimp-release` and extension metadata
paths. Missing or malformed required metadata must fail visibly rather than be
silently replaced with a guessed layout. No compiler options or binary code are
changed to implement this policy.

## Example plug-ins and retained image formats

The extension directory is:

```text
/usr/lib/MULTIARCH/gimp/3.0/extensions/org.gimp.extension.goat-exercises/
```

`MULTIARCH` is `x86_64-linux-gnu` or `aarch64-linux-gnu`. The staging helper removes
`goat-exercise-gjs.js` and `goat-exercise-lua.lua` if present, and removes those
names from the colon-separated `GIMP::plug-in-path` value in
`org.gimp.extension.goat-exercises.metainfo.xml`. It requires exactly one matching
registration field and leaves the other metadata intact. Removing only a script
would leave a stale registration. The inspected 3.2.6 AppImage contained JS but no
Lua example; fixtures include both so both exclusion paths are exercised.

The dependency audit found no remaining GJS consumer in the retained packaged
scripts/interpreter configuration, so the explicit `gjs` row was removed. This
does not prohibit users from installing their own JS/Lua plug-ins and the
interpreters those plug-ins require.

The MNG executable remains under `gimp/3.0/plug-ins/file-mng/file-mng` and imports
`libmng.so.1`. The external map resolves that import to Debian's `libmng1`; the
upstream external library is not copied into the private runtime. Real build
checks established the retained executable and dependency for both architectures;
they did not execute an MNG encode/decode round trip in this change.

The inspected official 3.2.6 payloads did not contain `file-iff`, the ILBM plug-in.
An enabled format does not always imply a bundled shared library: the inspected
upstream build supports both libiff/libilbm dependencies and a header-based path.
For future artifacts inspect the actual plug-in, linkage and upstream build
rules. Preserve available support; fail deliberately on an unknown external
SONAME instead of guessing a Debian package or silently bundling another library.

## Personal welcome-dialog configuration

The user keeps copy-and-paste setup commands in
`https://github.com/wpyoga/debian-linux-setup.git`. At investigation time all 34
tracked files were read; they were Markdown command recipes, with no existing
GIMP recipe or repository-specific AGENTS.md found. An `apps/gimp.md` file was
created in a clone under `build/debian-linux-setup/`, using that style.

That clone is now absent. The file was not committed or pushed by this work, and
there is no evidence here that it reached the remote repository. The complete
recipe is preserved below so the personal change can be recovered independently
of ignored build data. Add it to the user's setup repository as `apps/gimp.md`
when working on that repository; this documentation task does not recreate or
publish a separate checkout.

Close GIMP completely, then run as the desktop user:

```bash
GIMP_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/GIMP/3.2"
GIMP_CONFIG_FILE="$GIMP_CONFIG_DIR/gimprc"

mkdir -p "$GIMP_CONFIG_DIR"
touch "$GIMP_CONFIG_FILE"

sed -i \
  '/^[[:space:]]*(show-welcome-dialog[[:space:]]/d' \
  "$GIMP_CONFIG_FILE"

printf '\n(show-welcome-dialog no)\n' >> "$GIMP_CONFIG_FILE"
```

The original Markdown recipe also ended its shell block with `exit`, matching
the other personal recipes. That is optional for applying this preference.
The commands preserve unrelated preferences, replace a conflicting active value,
and retain one active suppression setting when repeated. They do not promise
identical whitespace after repeated execution. Do not overwrite the entire
profile with a small generated file. Editing while GIMP is running can lose
changes when GIMP writes preferences on exit.

The system API/resource directory remains `3.0`, whereas the GIMP 3.2 user
profile is `GIMP/3.2`. The normal XDG path above assumes there is no custom
`GIMP3_DIRECTORY` override; honor that override separately if the user's launcher
sets one. Debian GIMP 3.0 profiles use their own version directory.

The setting is `(show-welcome-dialog no)`. The corresponding UI checkbox in the
inspected source was labelled "Show on Start"; the dialog can be reopened through
Help. Upstream `gimp_update_auto_check` deliberately still shows a welcome dialog
on the first launch after an upstream-version upgrade, even when this preference
is disabled. Do not falsify `config-version` to suppress that path: this task did
not change profile migration/version handling. Disabling background network
checks is independent of suppressing normal welcome appearances.

## Historical verification and evidence status

The final implementation work reported these successful checks:

| Check | Historical result and limit |
| --- | --- |
| GIMP adapter regression selection | 18 tests passed; this count included the then-integrated help tests and is not today's expected test count. |
| amd64 and arm64 cached real builds | 41 outputs per architecture, then comprising eight application and 33 help packages. No target ELF execution. |
| Real package/index checks | Versions, architectures, stream/checksum fields, payload ownership, Installed-Size from staged trees, and matching published index values passed. |
| Real startup/example checks | Active update suppression, package policy, JS/Lua exclusion and metadata cleanup, retained C/Vala/Python examples, MNG executable/import and package dependency passed on both architectures. |
| Dependency ownership | Application requirements appeared on `gimp`, library requirements on libgimp/runtime packages, and reviewed indirect requirements remained present. Unknown module SONAMEs failed. |
| Personal recipe | Fresh and existing profiles, conflicting values, XDG override, repeated execution, and unrelated-setting preservation passed. |
| Static checks | Changed Bash scripts passed `bash -n`; Python parsing and both repositories' whitespace checks passed. |
| Recipe identity | A final comparison against the generated Packages entry confirmed that the successful build fingerprint matched the adapter files then present. |

The tests remain represented in
[test_gimp.py](../tests/gimp-3.2/test_gimp.py), including
`test_packages_layout_metadata_dependencies_and_revision_reuse`,
`test_dependency_ownership_includes_loaded_modules_and_explicit_requirements`,
`test_unknown_dependency_in_loaded_module_fails`,
`test_invalid_release_metadata_fails`, and
`test_invalid_extension_metadata_fails`.

No Docker installation, desktop execution, GPG signing integration, host package
installation, production storage access or publication was performed in this
specific startup/dependency change. Earlier amd64 installation/codec experiments
documented elsewhere are separate evidence, not tests of every later recipe.

The following paths were used historically and are absent in the current
checkout. They are an inventory of lost local evidence, not functioning links:

| Former path | Purpose |
| --- | --- |
| `build/gimp-policy-work/` | Batch manifest, implementation/verification scripts, named logs and isolated real builds. |
| `build/gimp-policy-work/real/output/{amd64,arm64}/` | Successful local `3.2.6-1` outputs with validation-only maintainer metadata; not production artifacts. |
| `build/gimp-policy-work/real/dependencies-ARCH.json` | Per-package external dependency reports. |
| `build/gimp-expanded-live/gimp/` | Earlier cached metadata, API docs and staged outputs reused by the runner. |
| `build/gimp-adapter-live/` | Cached official amd64/arm64 AppImages. |
| `build/debian-linux-setup/` | Personal setup clone with uncommitted `apps/gimp.md`. |
| `build/gimp-debian-source/` | Debian source/packaging checkout used for comparison. |
| `build/test-run-IeV9Yd/` and `build/test-run-UhEXos/` | Earlier and final 18-test regression logs. |

No fresh builds were run to replace that evidence during documentation. The
current implementation can be inspected and tested; the old success claims are
historical reports whose primary logs and artifacts are no longer available.

## Runner failures and lessons preserved from the implementation

The user requested one permission request at the start of execution, a top-level
runner coordinating smaller scripts, named logs, cached downloads/build reuse,
and consideration of skipping Docker to avoid extra socket permissions. Docker
was skipped for that work. A durable runner should use finite file-based stages
and make its complete actions reviewable before execution.

The original attempt used a Python loop over `sys.stdin` through a non-TTY
command. It printed readiness, immediately received EOF and exited successfully;
it did not edit files or run checks. A short command yield timeout does not keep
stdin open. The attempt only created the work directory.

A proposed replacement wrapped generated scripts inside nested serialized JSON
and shell quoting. The user rejected it as unreadable and asked for manually
written JSON. The eventual task manifest was a plain JSON file whose named stages
contained command argument arrays. Standalone script files held substantial code.
Do not reconstruct the rejected nested encoding approach.

The first real-build stage attempted hard links to existing cached AppImages and
received `PermissionError: Operation not permitted`. Copying with
`cp --reflink=auto` succeeded and preserved the original cache. A cache file's
readability does not guarantee hard-link permission.

Another validation assertion rejected the literal `(check-updates yes)` anywhere
in the system file, including an upstream comment documenting the default. The
package had the correct active `no` setting. The checker was corrected to ignore
comment lines and require exactly one active `no`; the fixture was strengthened
to start with an active `yes`. Successful real builds were reused rather than
rebuilt for the checker-only correction. Final checks passed afterward.

The environment was read-only during that implementation, so corrections after
an exited batch required additional execution approvals despite the intended
single-request workflow. This is historical environment context, not a current
repository requirement. Use current permissions and existing authorization;
do not seek repeated permission for already-authorized reversible edits.

One final `dpkg-deb --field` read also failed because that command needed a
temporary directory in the read-only environment. The recipe comparison used the
already-generated and validated Packages index instead. Do not infer corrupt
package bytes from that temporary-directory failure.

## Reverification, recovery and next actions

For documentation-only changes, inspect local links and source facts and run
`git diff --check`; package builds and signing tests are unnecessary. For a
subsequent packaging change, run appropriate adapter tests from the project root
with named logs and bounded timeouts, for example:

```bash
mkdir -p build/logs
timeout --kill-after=30s 30m bash tests/run.sh gimp-3.2 \
  > build/logs/gimp-startup-regression.log 2>&1
```

Wait for completion before reading the log. The GIMP download tests now use
loopback sockets, so a restricted environment may need local socket permission
even though they do not contact the internet. See
[local tool setup](local-tools.md) for project-local dependencies if tools are
missing; extract tool packages under ignored build storage instead of installing
them on the host. The historical runner extracted `squashfs-tools` this way.

The maintained [real build checker](../tests/gimp-3.2/check-build.py) accepts a
current application workspace and checks both architecture output directories.
Use today's hooks/configuration and eight-package application set. The removed
historical runner imported manual outputs into that workspace and cannot simply
be recreated with old paths or output counts. Review the
[optional publisher test](../tests/gimp-3.2/test-publisher.sh) and
[help verification options](gimp-help-3.2.md#verification) when live downloads,
signed indexes or container limits are explicitly part of the next task.

Before a real rollout, rebuild the publisher image so it contains the changed
adapter and run the normal isolated/authorized publication workflow. Do not
reuse local validation version `3.2.6-1` as a manually chosen production revision.
Stored packages and their embedded recipe/stream metadata determine the next
revision. Existing conffiles and desktop behavior require installation testing
separate from static packaging checks.

Outstanding work relevant to this conversation is limited to verifying deployment
and actual desktop behavior when requested, and recovering/committing the personal
setup recipe in its own repository if desired. Direct upgrades, third-party
plug-ins, arm64 execution and the deferred TIFF-thumbnail issue retain the limits
documented in the maintained notes. There is no authorized task here to rebuild
GIMP from source or port Debian source patches.

## Primary reference locations used in the investigation

These identify the original source material; their live availability and current
contents were not rechecked while writing this historical handoff.

- [Debian 3.0.4 packaging rules](https://sources.debian.org/src/gimp/3.0.4-3%2Bdeb13u11/debian/rules/)
  and [Debian 3.2.6-1 packaging rules](https://sources.debian.org/src/gimp/3.2.6-1/debian/rules/).
- [Debian GIMP packaging repository](https://salsa.debian.org/gnome-team/extras/gimp)
  (the investigation cloned the older `gnome-team/gimp.git` URL).
- [GIMP 3.2.6 update logic](https://github.com/GNOME/gimp/blob/GIMP_3_2_6/app/gimp-update.c),
  [package release policy reader](https://github.com/GNOME/gimp/blob/GIMP_3_2_6/app/gimp-version.c),
  [GUI preference definition](https://github.com/GNOME/gimp/blob/GIMP_3_2_6/app/config/gimpguiconfig.c),
  and [example installation rules](https://github.com/GNOME/gimp/blob/GIMP_3_2_6/extensions/goat-exercises/meson.build).
- [GIMP configuration manual](https://www.gimp.org/man/gimprc.html).
- [Debian gvfs-backends file list](https://packages.debian.org/trixie/amd64/gvfs-backends/filelist).
- [dpkg-shlibdeps documentation](https://manpages.debian.org/trixie/dpkg-dev/dpkg-shlibdeps.1.en.html)
  and [Debian shared-library policy](https://www.debian.org/doc/debian-policy/ch-sharedlibs.html).
- [Personal setup repository](https://github.com/wpyoga/debian-linux-setup).
