# Working on this repository

Read [ARCHITECTURE.md](ARCHITECTURE.md) for the design and its rationale. Use
[README.md](README.md) for configuration, deployment, and the exact hook contract.
Before editing, inspect the relevant scripts, adapter, and tests; check the working
tree for changes from the user or another session.

## Philosophy and style

- Make the code understandable to an average high-school student. Favor explicit
  steps, descriptive names, and small functions over compact or clever code.
- Separate logical blocks with blank lines. Break long commands and conditions
  across lines. Do not separate every statement mechanically.
- Repetition is acceptable. Introduce a shared helper when it makes its callers
  easier to understand, rather than solely to eliminate duplication.
- Use Bash for process coordination and file operations, and jq for simple JSON
  operations. Keep Python when structured bookkeeping, metadata processing, or
  dates are clearer there. Avoid substantial inline Python inside shell scripts.
- Shell variables, including locals, and configuration keys use `UPPER_CASE`.
  Functions use descriptive lowercase names. Python uses normal Python naming.
- Executable Bash scripts use `#!/bin/bash` and `set -Eeuo pipefail`. Quote
  expansions and positional arguments; use arrays for command argument lists.
  Intentional word splitting of architecture/package lists is already part of
  the framework; do not introduce general unquoted path handling.
- Require supplied context early, for example:

  ```bash
  : "${WORKSPACE:?WORKSPACE must be set and non-empty}"
  ```

  Use exported `FRAMEWORK_DIR`, `ADAPTER_DIR`, and `WORKSPACE`. Do not infer paths
  from `$0`, `BASH_SOURCE`, or chains of fallback environment variables.
- Put substantial generated text in an external template. Control templates are
  normally named `control.in`, use `@VARNAME@` placeholders, and are rendered with
  common tools such as sed. Escape human-entered replacement values. Do not add
  gettext/envsubst for this purpose.
- Explain reasons in comments where needed. Keep errors concrete: name the
  stream, version, architecture, file, or field that failed.

## Design rules to preserve

- `.env` contains operator settings, including `MAINTAINER` and `REPO_NAME`;
  `.env.example` documents them. Missing required settings fail early.
- Discover adapters by listing `packages/`. Each directory follows one release
  stream, identified by `RELEASE_STREAM` in its data-only config. There is no
  central package registry. Different streams may publish the same Debian name.
- Keep amd64/arm64 selection. Finish one stream before starting the next. Keep
  the kernel `flock` and wait `CHECK_INTERVAL` after the complete cycle.
- Queries select current releases for their stream. Packaging changes rebuild
  the current targets, not historical upstream versions.
- Derive revisions from stored packages and their embedded checksum/stream
  metadata. Do not add revision counters, checksum sidecars, or `revision-env`.
  Preserve existing artifacts and resume incomplete builds at their revision.
- Adapters own their upstream query and packaging method. Expect a fixed layout
  and validate it. Fail with a useful error when it changes; do not search for
  alternative roots or silently adapt to a different artifact structure.
- A failed stream must not stop the others. Inactivity checks only warn. Keep
  stored versions and old by-hash indexes; there is no automatic retirement,
  migration, cleanup, or external notification mechanism.

## Working on adapters and the framework

For a new adapter, follow the workflow in
[ARCHITECTURE.md](ARCHITECTURE.md#adding-or-changing-an-adapter). Read the existing
adapter closest to its packaging method, but do not assume every package should
copy that method. Verify the upstream release source, checksums, architecture
mapping, dependency requirements, and expected layout.

Every binary package must include `Installed-Size` in its control metadata so
APT can estimate disk usage. Calculate it in KiB from the final staged package
tree, excluding `DEBIAN/`, before building the `.deb`. Recalculate it for imported
packages too; do not trust an upstream value after repackaging. `dpkg-deb --build`
does not generate this field. Cover the field and its published index value in
adapter tests, including missing or stale upstream metadata for importers.

Put reusable framework behavior in `lib/` only when it belongs to the publisher.
Keep upstream-specific assumptions inside the adapter. Update documentation when
changing the hook contract or design decisions.

Adapter files are checksum inputs, including comments and documentation. Keep
general developer documentation outside `packages/` to avoid unnecessary package
revisions. Temporary files belong under ignored `build/`; manual local data uses
`build/local/repo` and `build/local/gnupg`. Do not use production data or keys for
tests, or copy operator secrets into documentation or fixtures.

## Verification

Run checks appropriate to the change from the project root:

```bash
python3 -m unittest discover -s tests -v
bash tests/test-signed-repo.sh
# Or run both:
bash tests/run.sh
```

The regression suite uses offline fixtures and real Debian package tools. Add
meaningful coverage for changed release selection, validation, or packaging
behavior; avoid tests that merely mirror formatting or implementation details.
The signing test uses a throwaway key and isolated APT state, and may need local
socket permission for GPG. Test entry points establish their own context.

Check changed shell scripts with `bash -n` and run `git diff --check`.
Documentation-only edits need link and factual checks, not package builds or
signing tests. Report what was checked and any remaining limitation. Container
builds and live deployment are separate from offline verification; do them when
they are part of the requested task.
