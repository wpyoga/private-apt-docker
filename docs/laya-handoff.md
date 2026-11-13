# Laya packaging investigation and implementation handoff

Recorded on 2026-11-13 so the original packaging conversation can be deleted.
The original investigation and implementation took place on 2026-10-27. This
document preserves its decisions, evidence, implementation, limitations, and
follow-up work. It does not assert that historical upstream or Debian versions
remain current.

Use [Laya's operator guide](laya.md) for client setup and normal use,
[ARCHITECTURE.md](../ARCHITECTURE.md) for the publisher design, and
[README.md](../README.md) for the current hook contract and deployment. Current
source files take precedence over historical descriptions below.

## State at this handoff

Laya has been implemented and committed. The production adapter is now
[`packages/repack/laya/`](../packages/repack/laya/config); tests remain under
[`tests/laya/`](../tests/laya/test_laya.py). There is no need to recreate the
original adapter or move it back to `packages/laya/`.

The following history was inspected locally:

| Commit | Date | Change relevant to Laya |
| --- | --- | --- |
| `a11cace` | 2026-10-27 | `feat: add laya`; original adapter, tests, coordinator, and documentation |
| `40745dc` | 2026-10-28 | Shared helper refactor; Laya now uses the common package operations |
| `c1d5691` | 2026-10-31 | Repository grouping; adapter moved to `packages/repack/laya/`, with test/coordinator paths updated |

HEAD during this documentation pass was `268ad5d`. Many unrelated documentation
changes were already staged or unstaged. This pass changes only this handoff and
its link from `docs/laya.md`; it does not stage or commit files, alter package
scripts, or change other work.

The original `build/laya-verification/` and `build/laya-dependency-audit/`
directories are absent from this checkout at handoff time. Historical results
and paths are recorded below, but the old binaries and logs are not being
represented as currently available. No fresh package build, test run, upstream
query, or deployment was performed for this documentation-only pass.

## Goal and accepted scope

The maintainer requested a Debian package for
[NandhaKishorM/laya](https://github.com/NandhaKishorM/laya), then selected an
automatically updated adapter for this publisher rather than only a standalone
`.deb`.

The accepted first implementation consists of:

| Binary package | Role |
| --- | --- |
| `python3-laya` | Python library, CPU inference dependencies, Pydantic structured results, and private Click |
| `laya-cli` | The `laya` command |
| `laya-http` | The `laya-serve` command and HTTP dependencies |

All three are `Architecture: all`. Each interface package depends on the exact
corresponding `python3-laya` version. They share stream identity `laya` and one
publisher-assigned Debian version/revision. Architecture-independent payloads
are stored once and indexed for amd64 and arm64.

The maintainer explicitly chose:

- Stable Python releases from PyPI and native Debian dependencies where feasible.
- Click bundled inside Laya, rather than a separate private Click adapter.
- Forky only for additional Debian dependencies; no Sid source in the final
  client policy.
- Repository-wide Forky priority 100 with selected exceptions at 500.
- Documented manual client APT setup, rather than a package modifying sources.
- Library, CLI, and HTTP support, including simple structured-result support and
  an Accelerate recommendation.
- MCP deferred, potentially as a separate `laya-mcp` package later.

During the initial implementation, production code was to stay in
`packages/laya/`, tests in `tests/laya/`, and `lib/` was not to be changed. That
instruction was followed in the original work. The later shared-helper refactor
and repository grouping are already committed repository changes; they are not
unfinished work from this conversation.

## Why CLI-only packaging still needs model dependencies

Laya's components share the Python library. Separate interface packages avoid
requiring every server dependency for every user, but do not remove the
inference stack from a functioning prediction command.

- Plain routing selects which checkpoint would handle the input, without loading
  model weights.
- `--predict`, `--preset`, and question-driven predictions load a model and need
  the inference dependencies.
- PyTorch performs tensor calculations.
- Hugging Face Transformers supplies model architectures and model-loading code.
- Hugging Face Tokenizers converts text into model token IDs.
- Hugging Face Hub downloads model files and maintains the local cache. Its use
  here does not require a hosted inference service.

The Python wheel includes additional optional modules. Their presence is not a
promise that all upstream extras are supported. Only the library and selected
CLI/HTTP entry points are packaged as supported interfaces.

## Historical dependency investigation

The maintainer preferred existing reputable packages over maintaining new recipes
for dependencies already packaged elsewhere. Hugging Face's documented channels
included Python wheels/source and some Conda support; no official Hugging Face
APT repository for these libraries was found in the investigation.

Debian packages were found in Forky and Sid. The October 27 downloaded indexes
showed identical versions in those two suites:

| Package | Inspected version |
| --- | --- |
| `python3-transformers` | `5.12.1-2` |
| `python3-tokenizers` | `0.23.1+dfsg-2.1` |
| `python3-huggingface-hub` | `1.23.0-1` |
| `python3-accelerate` | `1.14.0-3` |

The original three libraries were absent from the inspected Trixie indexes.
Their required `Depends`/`Pre-Depends` closure could be satisfied on amd64 and
arm64 with Trixie plus those three Forky packages. The static dependency walk
visited 318 packages on amd64 and 315 on arm64. These are graph sizes, not counts
of additional packages that would be installed on an existing machine.

This was metadata parsing and version comparison, not an APT solver run. The
initial parser needed corrections for library initialization and `:any`
qualifiers; the final static closure reported no unsatisfied required groups.
It did not prove joint installability against an arbitrary host's installed
packages, all conflicts/breaks, or runtime compatibility.

Important inspected Trixie versions and payload requirements were:

| Dependency | Inspected Trixie version | Relevant requirement |
| --- | --- | --- |
| Python | `3.13.5-1` | Python >= 3.10 |
| PyTorch | `2.6.0+dfsg-7` | Transformers payload >= 2.4; Laya >= 2.0 |
| Safetensors | `0.5.2-1+b1` | Transformers >= 0.4.3; Laya >= 0.4 |
| NumPy | `1:2.2.4+ds-1` | Laya >= 1.20 |
| HTTPX | `0.28.1-1` | Hub >= 0.23, < 1 |
| libc | `2.41-12+deb13u4` | Tokenizers >= 2.34 |
| FastAPI | `0.115.11-4` | Laya HTTP >= 0.110 |
| Uvicorn | `0.32.0-3` | Laya HTTP >= 0.27 |
| Python multipart | `0.0.20-1.1~deb13u1` | Laya HTTP >= 0.0.9; Debian name is `python3-python-multipart` |
| Pydantic | `2.10.6-2` | Structured results >= 2.0 |

The amd64 Tokenizers payload was inspected with `readelf`, without loading it.
Its linked system libraries and required symbol versions fit Trixie's baseline.
The arm64 control metadata was checked, but no arm64 execution was performed.
Downloaded Debian archive digests matched the downloaded index values; this
comparison was not a separate verification of signed repository metadata.

Hub's Python metadata also named `hf-xet`. Inspection found an explicit ordinary
HTTP fallback when Xet is absent, so no Xet dependency was added. Accelerate's
required dependencies fit Trixie plus the already-selected Hub. Its own
recommendations include development libraries, which can increase install size.

### Why the libraries were missing from stable

Package histories showed Transformers first entering unstable in July 2026 and
Tokenizers moving from experimental to unstable in July 2026. Both migrated to
testing in September 2026. Hub entered experimental and unstable in 2025 and
migrated to testing in December 2025.

They were not identified as permanently restricted to testing/unstable. Testing
prepares the next stable release, and eligible packages can ship when it becomes
stable. That does not automatically add new packages to already-released Trixie.
Recheck the trackers and current suites when resuming; this is historical evidence.

## APT policy: accepted choices and rejected alternatives

The initial proposal included both Forky and Sid, package exceptions at higher
priorities, and a general priority of -1. The maintainer preferred a more
conservative Forky-only source and selected package priority 500. The final
policy is documented verbatim in [the client setup guide](laya.md#configure-clients).

The selected exceptions are Transformers, Tokenizers, Hub, and Accelerate at 500;
other Forky packages receive 100. With ordinary Trixie candidates at 500, Trixie
remains preferred for other packages. Giving the whole Forky suite priority 500
would tie Trixie and generally choose newer versions, allowing broad upgrades.

Priority 100 is a soft preference: Forky-only packages remain eligible and an
installed Forky-only package can receive updates. It can therefore admit new
Forky-only dependencies. Priority -1 instead excludes matching versions from
normal candidate selection unless an applicable exception changes the effective
priority. Neither configuration makes cross-suite runtime compatibility automatic.

The maintainer specifically asked about two independent preference files:

- File one gives package A priority 500 and `Package: *` priority 100.
- File two gives package B priority 500 and `Package: *` priority 100.

They compose as intended: A and B each receive 500, and other Forky packages
receive 100. Duplicate general defaults are harmless. General priorities use
the maximum matching value; overlapping package-specific rules use the first
matching specific record. A shared repository default with per-application
exceptions is easier to maintain, but is not required for that example to work.
Existing administrator preferences and default-release settings still matter.

No client APT files were changed in this work. There is no setup package, no
automatic repository import, and no redistribution of the Forky dependency
packages into the private repository.

## Click: investigation, correction, and final decision

Click is Pallets' Python command-line interface library. Debian's package name is
`python3-click`; the package named simply `click` is a different project.

Trixie's inspected version was `8.2.0+0.really.8.1.8-1`. Debian had uploaded an
unfinished 8.2.0 version, then reverted the code to 8.1.8 because of compatibility
failures in other packages. The replacement version sorts above the earlier
upload, allowing APT to install the revert as an upgrade. The word `really` is a
human-readable convention, not special APT syntax. API compatibility must be
assessed against the actual 8.1.8 code. See [Debian bug 1098507](https://bugs.debian.org/1098507).

Hub 1.23.0's embedded metadata requests Click >= 8.4.2, < 9, while its inspected
Debian control file has an unversioned Click dependency. Forky's inspected Click
was 8.3.3, also below that upstream declaration.

The documented reason for 8.4.2 is a Fish completion regression in 8.4.0/8.4.1.
However, that did not establish that 8.1.8 was fully compatible. Further static
inspection found concrete differences:

| Hub CLI call | Click 8.1.8 signature |
| --- | --- |
| `get_metavar(param, ctx=ctx)` | `get_metavar(param)` |
| `make_metavar(ctx=ctx)` | `make_metavar()` |

Hub's CLI help formatting uses those calls. They would raise `TypeError` with
the inspected older signatures. Context-aware support exists in Click 8.2.0;
8.4.2 additionally satisfies Hub's stated minimum and avoids the completion bug.
The earlier suggestion to accept the unversioned Debian dependency for all Hub
features was therefore too broad and was corrected.

Laya itself uses argparse. Its model-loading path calls Hub's `snapshot_download`
Python API rather than the Hub CLI. Inspection did not establish that Laya's
normal inference needs Click 8.4.2, but it also did not justify calling the entire
Hub package compatible with 8.1.8. The maintainer chose to bundle 8.4.2 privately.

### Pin and isolation boundary

The authoritative pin is [`click.json`](../packages/repack/laya/click.json):

```text
Filename: click-8.4.2-py3-none-any.whl
SHA256: e6f9f66136c816745b9d65817da91d61d957fb16e02e4dcd0552553c5a197b76
```

Click and its distribution metadata are installed at `/usr/lib/laya/vendor/`.
The two generated launchers insert this directory at the front of `sys.path`
before importing `laya.cli` or `laya.serve`. No system Click files are replaced.
The private distribution metadata lets normal Python metadata lookup see the
bundled version within those launcher processes.

This does not repair a separately invoked system `hf` command. A program doing
`import laya` through ordinary system Python does not automatically receive the
vendor path either. Do not silently describe the bundle as a global Hub fix.

Changing the Click pin is an adapter recipe change and causes the current Laya
release to receive a new packaging revision. There is no separate Click stream,
revision counter, or per-dependency Debian package in this implementation.

## Current adapter implementation

| File under `packages/repack/laya/` | Responsibility |
| --- | --- |
| `config` | Stream identity and three declared binary names |
| `query` | PyPI discovery, stable version and wheel selection, targets/date/asset metadata |
| `build` | Download coordination, staging, permissions, package dependencies and launchers, control rendering, `.deb` creation |
| `stage.py` | Wheel metadata, requirements, layout, RECORD and entry-point validation; payload staging |
| `click.json` | Pinned private Click download |
| `control.in` | Debian control template |
| `launcher.in` | Private-vendor Python launcher template |
| `copyright.in` | Package copyright summary; full upstream licenses are copied separately |
| `helper-inputs` | Registers `adapter/package.sh` as a recipe helper input |

The original implementation was self-contained. Current `build` sources
`lib/adapter/package.sh` for `verify_download`, `render_control`, and `build_deb`.
That helper calculates Installed-Size in KiB, escapes template replacement
values, and invokes `dpkg-deb --build --root-owner-group -Zgzip`. Laya keeps its
upstream selection, dependency assumptions, staging and validation in its adapter.

### Query and build data flow

1. Query fetches `https://pypi.org/pypi/laya/json` into the workspace downloads.
2. It accepts only a numeric three-part version and exactly one non-yanked
   `laya-VERSION-py3-none-any.whl`. It fails on missing/duplicate assets rather
   than choosing an alternate source, source distribution, or older version.
3. It requires a SHA256 and an HTTPS download URL on `files.pythonhosted.org`.
4. It writes `assets.json`, one `VERSION<TAB>ARCH` row per requested supported
   architecture in `targets.tsv`, and the upload timestamp in `release-date`.
5. The framework assigns the Debian revision. Build checks that its upstream
   component matches the selected release and accepts amd64/arm64 build requests.
6. Build verifies/reuses the Laya and Click downloads, then stages all three
   packages. It never imports wheel modules or runs their build backends.
7. It normalizes directory/file permissions, generates executable interface
   launchers, renders controls, and builds three `_all.deb` outputs. Full licenses
   live under `usr/share/doc/python3-laya/`; interface documentation paths are
   symlinks to that package's documentation.
8. Successful temporary staging is removed; failed staging is left for inspection
   subject to the framework's workspace lifetime. Stored repository artifacts and
   revisions remain the framework's responsibility.

The wheel validator checks fixed project/dist-info roots, canonical relative
paths, duplicate names, file types, required license and module paths, SHA256,
metadata name/version, literal Python requirement `>=3.10`, purelib/tag/version
fields, and every file's RECORD hash/size. It rejects links, special files,
`.pth`, `.pyc`, and `.so` payloads, missing/unrecorded files, mismatched module
versions, or changed selected entry points. RECORD itself must not hash itself.

The currently accepted core requirements are exactly torch >= 2.0.0,
transformers >= 4.48.0, safetensors >= 0.4.0, huggingface-hub >= 0.20.0, and numpy
>= 1.20.0. HTTP and structured declarations are checked separately. These are
explicit recipe assumptions, not a general Python-to-Debian requirement resolver.
An upstream declaration change requires inspection and a deliberate recipe update,
even if the new requirement might already be satisfied on a client.

No model weights, service unit, automatic server startup, client APT configuration,
or unsupported extra commands are installed. CPU PyTorch is supplied by Debian.
Upstream HTTP defaults inspected during the investigation included binding to
`0.0.0.0:8000` and preloading models; administrators must choose runtime settings
before starting `laya-serve`.

## Verification record and how to reproduce

The October 27 implementation completed ten offline tests, shell syntax checks,
whitespace checks, and static inspection of actual locally built package controls
and payloads. Tests use fixture wheels whose modules raise if imported, stubbed
downloads/signing, and real Debian archive/index tools. They cover:

- Required hook context, architecture selection, and version agreement.
- Rejected prereleases, missing/yanked/duplicate assets, malformed metadata,
  invalid digests and URLs, and corrupted Laya/private Click downloads.
- Fixed layouts, metadata/module versions, changed core and HTTP dependencies,
  non-pure wheels, escaping paths, native payloads, links, and malformed RECORDs.
- A valid outer wheel digest with changed bytes that no longer match RECORD.
- Exact interface dependencies, private Click location, licenses, executable
  launchers, package/index Installed-Size, and both architecture indexes.
- Repeated-update byte preservation, maintainer escaping, and recipe/pin revision
  allocation without overwriting stored versions.

The original local outputs were:

```text
python3-laya_0.4.15-1_all.deb
laya-cli_0.4.15-1_all.deb
laya-http_0.4.15-1_all.deb
```

Their maintainer was `Local Verification <verification@localhost>`, not operator
metadata. The inspected Laya wheel SHA256 was
`f51301738464677cb650159684537eb267de47d33f3db4d8897f1502a9570e6e`.
PyPI then supplied 0.4.15 while GitHub main showed 0.4.16; the implementation
correctly followed PyPI. Neither number is asserted to be today's latest release.

Historical evidence paths included `build/laya-verification/logs/run-XDDzgm/`,
`build/test-run-RiizJP/regression.log`, and the earlier static investigation under
`build/laya-dependency-audit/`. They are absent now. The original log record said
ten tests passed; this documentation pass did not rerun them after later refactors.

From the project root, the package regression command remains:

```bash
bash tests/run.sh laya
```

For live downloads and local verification builds, use the host-side coordinator:

```bash
bash tests/laya/coordinate.sh prepare
bash tests/laya/coordinate.sh verify
# Or both phases:
bash tests/laya/coordinate.sh all
```

It establishes context, uses `packages/repack/laya/`, batches commands with
timeouts and named logs, reuses verified downloads, and avoids repeated individual
permission requests where the execution environment grants the coordinator the
needed access. Actual environment permissions still apply.

`prepare` downloads PyPI metadata and the two wheels and lists their archives.
`verify` runs the offline suite, shell syntax and diff checks, then performs a
fresh live query and local build. Thus `verify` needs network access too. The
local output version uses a literal `-1` suffix and the placeholder maintainer;
it is not a replacement for production revision selection. Outputs from multiple
upstream versions can remain in the reusable output directory, so inspect the
filenames and controls rather than assuming every file is from the latest run.

The coordinator never sources `.env`, uses real signing keys, changes APT, installs
packages, or publishes the result. The work intentionally did not complete any
APT simulation, downloaded application execution, real signing test, container
build, prediction test, HTTP request test, or live deployment. Packaging/index
success is not evidence of successful inference or server operation.

## Deferred features and the next investigation

The following availability findings are dated to the original conversation and
must be refreshed before making a packaging decision:

| Feature | Finding and unresolved work |
| --- | --- |
| MCP SDK | Absent from inspected Trixie/Forky indexes. Sid and Ubuntu development had 1.28.1; Laya required >= 2.2.0 and imported the v2 server API. Those packages were insufficient. |
| Third-party MCP | VitexSoftware advertised Trixie `python3-mcp` with Debian version `1:2.0.0-...`; upstream 2.0.0 was still below Laya's requirement. The epoch `1:` does not change the SDK API version. Repository trust, dependency closure and payload compatibility were not audited. |
| ONNX inference | Trixie already had `python3-onnx` 1.17.0 and `python3-onnxruntime` 1.21.0. Inference could be considered separately from export. |
| ONNX export | `python3-onnxscript` 0.2.0 was found in Debian experimental. Compatibility with the selected PyTorch/Laya exporter was not established; experimental was not added to client sources. |
| TileLang | No suitable maintained APT source was found. Upstream wheels/source and GPU toolchain requirements would need separate work. |
| LangChain/LangGraph, LlamaIndex, CrewAI, Agno | No suitable maintained APT source was found in the search. That is not proof that no repository anywhere carries them. |
| Training/evaluation commands | Upstream provides entry points, but these were outside the accepted initial binary package set. |

MCP was explicitly deferred. Revisit it as an independently installable
`laya-mcp` package when a suitable SDK is available, potentially with a dedicated
dependency adapter if Debian still lacks the required version. That is a future
design decision, not a partially implemented adapter to finish automatically.

When resuming implementation or validation:

1. Read current contributor instructions, repository docs, adapter/tests, and the
   working tree before editing. Preserve unrelated sessions' changes.
2. Refresh upstream and Debian facts. Inspect actual required features and Debian
   patches rather than raising floors solely to copy an upstream version string.
3. Review changed wheel metadata, requirements and entry points before relaxing
   validator checks. Keep upstream assumptions in the adapter.
4. Update pins/recipes deliberately; let the publisher choose revisions from
   stored packages. Reuse useful sources and retain failure evidence.
5. Run the relevant offline checks with named logs. Any runtime/container/install
   validation is additional work requiring its own scope; do not claim that it
   happened in this conversation.
6. Rebuild/deploy the repack publisher through the current repository workflow
   only when deployment is requested. Do not use local verification outputs or
   placeholder metadata as evidence of production publication.

## Source references

- [Upstream Laya repository](https://github.com/NandhaKishorM/laya),
  [Python metadata](https://github.com/NandhaKishorM/laya/blob/main/pyproject.toml),
  [CLI](https://github.com/NandhaKishorM/laya/blob/main/laya/cli.py), and
  [MCP implementation](https://github.com/NandhaKishorM/laya/blob/main/laya/mcp/server.py).
- [Laya on PyPI](https://pypi.org/project/laya/) and
  [pinned Click release](https://pypi.org/project/click/8.4.2/).
- [Hub 1.23.0 dependency declaration](https://github.com/huggingface/huggingface_hub/blob/v1.23.0/setup.py),
  [Click 8.1.8 parameter types](https://github.com/pallets/click/blob/8.1.8/src/click/types.py),
  [Click 8.1.8 core](https://github.com/pallets/click/blob/8.1.8/src/click/core.py), and
  [Click 8.2.0 parameter types](https://github.com/pallets/click/blob/8.2.0/src/click/types.py).
- [Debian's Click revert](https://bugs.debian.org/1098507) and
  [APT preferences](https://manpages.debian.org/trixie/apt/apt_preferences.5.en.html).
- [Transformers history](https://tracker.debian.org/pkg/transformers/news/),
  [Tokenizers history](https://tracker.debian.org/pkg/tokenizers/news/), and
  [Hub history](https://tracker.debian.org/pkg/huggingface-hub/news/).
- [Debian ONNX package search](https://packages.debian.org/search?keywords=onnx&searchon=sourcenames),
  [ONNX Script in experimental](https://packages.debian.org/experimental/python3-onnxscript),
  [VitexSoftware repository](https://repo.vitexsoftware.com/), and
  [TileLang installation](https://github.com/tile-ai/tilelang/blob/main/docs/get_started/Installation.md).

Links to upstream `main` and live repository listings can change. Versioned
source links, the pinned manifest, Git history, and the dated observations in
this document explain the original decisions without depending on chat history.
