# Original GIMP investigation: conversation handoff

This document preserves the initial conversation about packaging GIMP for Debian
13. The investigation continued in this repository after that conversation;
the maintained adapter and newer documents describe the current design. The
original scratch directory and its `gimp-repack/HANDOFF.md` are not present in
the current checkout.

## User's goal and working preferences

The user wanted GIMP 3.2 on Debian 13 as native Debian packages, integrated
with the private APT publisher and capable of replacing Debian's GIMP 3.0.
They proposed extracting the official AppImage and repackaging its contents,
rather than building everything from source or distributing an AppImage
wrapper. They care about third-party plug-in compatibility and Debian's
multiarch layout. They deferred testing third-party plug-ins until the main
application worked.

The user prefers readable, small shell scripts for process and file handling,
with Python used where it is clearer. Explain changes before patching binaries;
inspect library versions and paths instead of assuming compatibility. They
asked that work stay inside the project and that system package installation
not be used for the investigation. Current repository instructions and the
current session's permissions govern future work. The user did not authorize
production publication merely by requesting this documentation.

## Findings from the first investigation

- Debian 13's GIMP package was 3.0.4; the examined upstream AppImage was
  GIMP 3.2.6 for x86-64. Its SHA-256 was
  `79ea41bc9b06f78fda181849a9ca8e42d83f1124dedb756f4d52352e2465010f`.
- GIMP 3.2 uses `3.0` in its system API, shared-library and plug-in paths
  because that is the GIMP 3 API version. Its user profile is versioned
  separately. Debian multiarch paths are a packaging convention; the ELF
  format does not itself require that directory layout.
- The extracted executables were ordinary x86-64 ELF files. Their embedded
  interpreter path was `.//usr/lib64/ld-linux-x86-64.so.2`, relative to the
  working directory. The upstream launcher changed directory before execution.
  The bundled and host loaders were both Debian glibc 2.41, with different
  Debian patch revisions. The kernel loads the ELF interpreter, which resolves
  shared libraries before the program runs.
- Sampled binaries contained 153 `$ORIGIN`-based RUNPATH entries. The upstream
  launcher also preloaded GIMP, babl and GEGL libraries and configured module
  and resource paths. Replacing the interpreter alone does not establish that
  all application resources and plug-ins will work.
- The user agreed to test same-major/minor library replacements as a batch and
  differing versions separately, keeping coupled libraries and modules together.
  Matching versions and SONAMEs are evidence to investigate, not proof of ABI
  compatibility; some pkg-config versions describe APIs or libtool versions.
- In isolated headless experiments, an image test created an image, applied a
  GEGL filter, saved and reopened XCF, and exported and reopened PNG. It passed
  with the baseline, a batch of 65 matching host libraries, the host glibc
  family, then Expat and systemd tested separately, and system Python bindings.
  These were limited experiments, not comprehensive plug-in or GUI tests.
- The first experimental native layout failed because the GExiv2 typelib and
  `gjs` were unavailable. Nine Debian dependency packages were downloaded for
  a local retest; that retest had not happened when the original handoff was
  written. The old staging trees and logs are no longer available here.
  Later work reconsidered example plug-ins and dependencies; use the current
  startup/dependency document for the resulting policy.
- The early proposed split into GIMP, babl and GEGL release streams was an
  investigation idea. It is superseded by the current adapter, which keeps
  babl/GEGL private. Do not reconstruct the earlier staging scheme as the
  current package design.

## Where to continue

Read these maintained records together with [ARCHITECTURE.md](../ARCHITECTURE.md),
[README.md](../README.md), and the repository instructions:

- [GIMP packaging and outstanding validation](gimp-3.2.md): current package
  choices, previous verification, and deferred TIFF-thumbnail investigation.
- [Investigation history](gimp-3.2-investigation-history.md): library-version
  evidence, experimental results, cleanup, and evidence availability.
- [Startup and dependency handoff](gimp-startup-and-dependencies-handoff.md):
  update policy, dependency ownership, example plug-ins, Debian packaging
  comparison, and the separately maintained personal setup recipe.
- [Packaging and test refactor handoff](gimp-packaging-and-test-refactor-handoff.md):
  packaging decisions, historical tests, Docker and disk-space lessons.
- [GIMP help packaging](gimp-help-3.2.md) and [help split handoff](gimp-help-split-handoff.md):
  the independently published manual stream.
- [AppImage build base](gimp-appimage-build-base.md), [extraction memory
  incident](gimp-extraction-memory-incident.md), and [publisher incident](gimp-publisher-incident.md):
  provenance, resource limits, publication failures and recovery context.

The implementation lives under `packages/repack/gimp-3.2/`, with tests under
`tests/gimp-3.2/`. Inspect the working tree, current adapter and tests before
editing. Historical successful tests and deployment reports in the linked
documents must not be presented as new verification; some underlying ignored
build artifacts and logs have been removed.

Original technical references: [GIMP 3.2 release notes](https://www.gimp.org/release-notes/gimp-3.2.html),
[GIMP downloads](https://www.gimp.org/downloads/),
[Linux ELF execution](https://man7.org/linux/man-pages/man2/execve.2.html),
and [dynamic linker search rules](https://man7.org/linux/man-pages/man8/ld.so.8.html).

## Detailed record of this chat, added 2026-11-14

This section records the conversation available in this session. The earlier
sections were already present in an untracked document when this documentation
request began. They include later experimental findings that are not shown in
this chat's execution record. They have been preserved, but should be read with
the linked investigation history rather than treated as actions performed here.
No package build, installation, runtime test or publication was performed during
this documentation update.

### Initial source-build question and resource estimates

The initial question was how much memory and time GIMP 3.2 would need on Debian
13, including building dependencies missing from the distribution. Read-only
inspection on 2026-10-23 found:

| Item | Observed value |
| --- | --- |
| Distribution | Debian 13, Trixie; `/etc/os-release` reported 13.7 |
| CPU | Intel Core i5-8350U, four physical cores, eight threads |
| RAM | 38 GiB total, approximately 25 GiB available |
| Swap | None |
| Initial GIMP availability | Debian 3.0.4; official upstream 3.2.6 AppImage |

The assistant estimated 8 GiB available RAM as a reasonable build target,
16 GiB for headroom, 10–20 GiB disk space, 30–90 minutes compilation with four
to six jobs, and 1–3 hours for a first complete setup. Half a day was suggested
as contingency for dependency problems. These were rough planning estimates,
not measured build results or published minimum requirements. The proposed
source-build order was babl, GEGL, then GIMP, using Debian development packages
for other dependencies where possible.

The official download page identified GIMP 3.2.6 as the stable release and listed
Debian 13 as supported by its AppImage. That led to investigating repackaging
instead of compiling. The initial estimate of 15–30 minutes to wrap an AppImage
in a Debian package applied to the simple wrapper proposal, not to the native
repackaging and compatibility work eventually requested. Do not reuse it as a
measured estimate for the maintained adapter.

### Packaging discussion and decisions

1. The assistant initially proposed a self-contained `gimp-appimage` package
   under `/opt/gimp-appimage`, with a launcher, desktop entry and icon. Updates
   would require a newly generated package.
2. The user asked why not `/usr/lib/gimp/`. The assistant suggested a separate
   `/usr/lib/gimp-appimage/` directory for coexistence, then discussed replacing
   Debian's GIMP with explicit package relationships.
3. The user clarified that 3.2 should replace 3.0 and preserve third-party
   plug-in access to packaged libraries. Coexistence was not the intended goal.
4. The user explicitly chose extracting the AppImage and rebuilding its payload
   into native Debian packages, rather than keeping the AppImage runtime or
   distributing an AppImage launcher inside a `.deb`.
5. Native placement must distinguish plug-in discovery from ELF library lookup.
   The actual layout inspected in the bundle used
   `/usr/lib/x86_64-linux-gnu/gimp/3.0/`, not simply `/usr/lib/gimp/`.
   GIMP shared libraries belong to the corresponding multiarch library layout.
   The `3.0` component denotes the API series, even for application 3.2.
6. Standard plug-ins ship with the application. Third-party plug-ins are a
   separate compatibility question; placing files in familiar directories is
   necessary for some workflows but does not prove binary compatibility.

The assistant briefly recommended a source build for stronger Debian integration.
The user reaffirmed the extracted-binary approach. That is the approach to
preserve; do not silently substitute source builds if repackaging hits a problem.

The initial phrase “not a wrapper” meant not wrapping an intact AppImage.
The current adapter does use a small native environment launcher, as explained
in [the packaging notes](gimp-3.2.md). That launcher runs installed ELF binaries
and supplies private module/library paths; it does not invoke AppRun, FUSE or
the AppImage runtime. This is a later implementation detail, not a reason to
return to the original self-contained wrapper proposal.

### Third-party plug-in compatibility discussion

The possible blockers discussed were:

- Required ELF symbols or ABI versions absent from the selected libraries.
- A plug-in loading an incompatible mixture of bundled and Debian libraries.
- Python modules, native bindings or GI typelibs missing from its environment.
- Plug-in or resource directories missing from the configured search paths.
- Debian package dependencies not correctly satisfied by the replacement
  `gimp` and library packages, even if the executable itself could run.
- GIMP 2.10 plug-ins requiring a GIMP 3 port independently of repackaging.

No incompatibility of a particular GIMP 3 plug-in was demonstrated in this chat.
No general compatibility guarantee was established either. The meaningful test
is discovery plus an actual operation from an identified plug-in, with its
provenance, version and dependency environment recorded.

The user initially selected G’MIC as a representative test. `apt-cache` found
no `gimp-gmic` package in the then-configured Debian repositories. It did find
`gmic` 2.9.4-4.1+b2, which is the standalone command-line application and does
not test the GIMP plug-in interface. Offered either an upstream GIMP 3-compatible
binary or a main-application-first test, the user chose the latter. Third-party
testing was therefore deliberately deferred, not completed or disproved.

The early reply named `~/.config/GIMP/3.2/plug-ins/` as a per-user location.
Do not infer the effective search path solely from that statement: inspect the
profile and GIMP preferences for the version under test. Preserve the existing
profile and use isolated profiles for automated tests.

### Approved experiment and acceptance criteria

The user requested a practical test and subsequently said to implement the plan.
The agreed experiment was:

- Verify the existing AppImage checksum and extract into staging.
- Inspect ELF dependencies, embedded paths, Python bindings and AppRun settings.
- Place executables, plug-ins, data and icons in native Debian locations.
- Prefer compatible Debian libraries; keep necessary additional libraries private
  rather than overwriting unrelated packages' system libraries.
- Give the replacement correct package names, version ordering, dependencies
  and file ownership; split data and library packages where needed.
- Inspect the package payload and simulate installation before installation.
- Test without relying on the original AppImage or extracted source directory.
- Confirm compiled and Python standard plug-ins load; create an image, run a
  bundled filter, save/reopen XCF, and export PNG.
- Check loader/resource errors, desktop integration and clean package removal.
- Deliver packages, repeatable packaging instructions and a report of remaining
  limitations. Report source changes as a blocker instead of silently compiling.

The system had no installed packages matching `gimp*`, `libgimp*` or `gmic*`
at this inspection. An existing GIMP 3.2 user profile was present. Approximately
37 GiB was free on the home filesystem. These are historical observations, not
the state of the current machine or repository deployment.

### Actions actually executed before the directory move

The verified download was:

```text
/home/william/Downloads/GIMP-3.2.6-x86_64.AppImage
SHA256: 79ea41bc9b06f78fda181849a9ca8e42d83f1124dedb756f4d52352e2465010f
```

The hash matched the official download page consulted earlier in the chat.
The file listing reported approximately 233 MiB. Extraction was authorized
through the read-only session's escalation mechanism. The executed commands
created `/home/william/gimp-repack/`, then ran:

```bash
/home/william/Downloads/GIMP-3.2.6-x86_64.AppImage --appimage-extract \
    > /home/william/gimp-repack/extract.log
```

The working directory was `/home/william`, so extraction produced
`/home/william/squashfs-root/`, not a tree inside `gimp-repack/`. Extraction
finished successfully. These are historical paths, not instructions to recreate
work in the whole home directory. Their present existence was not checked for
this documentation task. Current builds use ignored project-local `build/`.

Read-only inspection of AppRun, the directory layout, `file` output and
`readelf -d` established:

- GIMP and console executables were x86-64 ELF binaries with the interpreter
  `.//usr/lib64/ld-linux-x86-64.so.2`. That path explains AppRun's working-directory
  requirement and must be changed for ordinary native execution.
- `gimp`, `gimp-3` and console aliases pointed to their 3.2 binaries.
  The Script-Fu interpreter retained the GIMP 3 API name
  `gimp-script-fu-interpreter-3.0`.
- The main executable had a long `$ORIGIN`-relative RUNPATH spanning bundled
  libraries, module directories and plug-ins, with some build-tree paths.
- AppRun set PATH and XDG data paths, cleared LD_LIBRARY_PATH, and preloaded
  bundled GIMP, babl and GEGL libraries. It changed directory to the bundle
  root and converted existing relative filename arguments to absolute paths.
- AppRun also supplied GIO, GdkPixbuf, GTK, libheif, Ghostscript, GI typelib,
  GJS and other resource/module paths. It dispatched `--gimptool` separately.
  Removing AppRun requires reviewing these functions rather than assuming
  interpreter patching alone replaces them.

At that point `dpkg-deb`, `readelf`, Python 3, GCC, sudo and
`desktop-file-validate` were available; `patchelf` was not found. A graphical
DISPLAY of `:0.0` was set, but no GUI test was run.

An attempted escalation for `sudo -n apt-get install -y patchelf` was interrupted
by the user. No successful installation result was received. The user asked to
install tools themselves and was told `sudo apt install patchelf` was the only
additional requirement identified so far. That was not a complete dependency
list for today's automated adapter: current tests also need SquashFS tools and
the other tools documented in README. Do not assume the interrupted request
installed patchelf; check the environment before resuming.

The user then asked to move work into a dedicated directory, said they would
move the AppImage, and was told where the extraction tree and log were located.
This chat contains no subsequent package-building or image-testing command
before the repository context and documentation request. The later outcomes in
the earlier handoff sections come from existing repository records, not those
commands.

### Current continuation point and documentation verification

The workspace is now `/home/william/Documents/wpyoga/private-apt-docker`.
At the start of this documentation task, the only `git status --short` entry
was the pre-existing untracked `docs/gimp-original-chat-handoff.md`. Its contents
were preserved and this detailed section was appended. No `.env`, keys, stored
packages, adapter inputs or test implementations were changed.

The existing adapter configuration, build hook, staging script, launcher template,
installation coordinator and regression-test entry point were inspected, along
with the architecture, README and historical notes. The current configuration
declares eight packages and the current build hook patches native interpreters
and RUNPATHs. It selectively extracts the bundle as data, unlike the original
scratch command above. Future work should use that maintained implementation.

For resumption, read the maintained packaging notes and outstanding-validation
table first. The next task must be chosen from current needs, not inferred from
an old uncompleted checklist. This documentation request does not authorize
production publication or host package installation. Run relevant checks using
the repository's named-log workflow; use container layers for root installation.

This documentation update checks local link targets and whitespace only. It
does not rerun the historical builds, signing checks, codec tests, third-party
plug-in tests or deployment. Existing reports of success retain their original
dates and evidence limits. The handoff is a technical record, not a verbatim
transcript or an archive of deleted build artifacts.
