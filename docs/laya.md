# Laya packages

The `laya` stream follows the latest stable Python release on PyPI, rather than
GitHub's default branch or the repository's separate TypeScript releases. It
repackages the official `laya-VERSION-py3-none-any.whl` without importing its
modules or running an upstream build backend. These are unofficial Debian
packages for Debian Trixie on amd64 and arm64.

| Package | Provides |
| --- | --- |
| `python3-laya` | System Python library, CPU inference dependencies, Pydantic structured results, private Click |
| `laya-cli` | The `laya` command |
| `laya-http` | The `laya-serve` command and HTTP dependencies |

All three packages have architecture `all`. The interface packages depend on
the exact corresponding library version. The publisher stores one copy and
includes it in both architecture indexes. Installing either interface does not
require the other, although APT may install additional libraries through Debian
dependencies' own recommendations.

## Configure clients

First configure this private repository using the normal client setup. Laya's
dependencies also require Debian Forky: Transformers, Tokenizers, Hugging Face
Hub, and optionally Accelerate are not in Trixie. The package scripts do not
modify APT sources or preferences.

Add `/etc/apt/sources.list.d/laya-dependencies.sources`:

```deb822
Types: deb
URIs: https://deb.debian.org/debian
Suites: forky
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
```

Keep existing Trixie, security, updates, backports, and private repository
sources. Add `/etc/apt/preferences.d/laya-dependencies.pref`:

```text
Package: python3-transformers python3-tokenizers python3-huggingface-hub python3-accelerate
Pin: release n=forky
Pin-Priority: 500

Package: *
Pin: release n=forky
Pin-Priority: 100
```

With Trixie's ordinary priority 500, other packages remain preferred from Trixie.
The named exceptions can receive Forky updates. Priority 100 still permits
other Forky-only dependencies: it is a preference rather than an allowlist.
Package-specific exceptions take precedence over the general rule. Identical
general defaults in other preference files are harmless; differing general
defaults use the highest matching priority, while overlapping package-specific
rules use the first matching rule. Review existing preferences when adding this
policy. Do not add Sid or use a blanket `apt -t forky` for this setup.

Then install the desired interfaces:

```sh
sudo apt update
sudo apt install laya-cli
# Optional HTTP interface:
sudo apt install laya-http
```

`python3-laya` recommends Accelerate. Debian's packages also have their own
recommendations, including development libraries from Accelerate/PyTorch; these
can increase installation size. Operators selecting dependencies explicitly can
use `--no-install-recommends` and install `python3-accelerate` separately.

## Click and runtime behavior

Click 8.4.2 is pinned by URL and SHA256 in the adapter and installed with its
distribution metadata under `/usr/lib/laya/vendor/`. The `laya` and `laya-serve`
Python launchers prepend that directory before importing Laya. No system Click
files are replaced and no global Python path configuration is installed.

This satisfies Hub 1.23.0's declared Click requirement within those processes.
Trixie's `python3-click` contains upstream 8.1.8 despite its Debian version
`8.2.0+0.really.8.1.8-1`; it lacks some context-aware help APIs used by Hub's CLI.
An independently launched `hf` command still uses system Click. Applications
importing Laya through system Python also keep their ordinary module search
path; they must configure the vendor path themselves if they need that Click.
Laya's ordinary CLI uses argparse and model downloads use Hub's Python API.

Routing without prediction needs no model download. Prediction downloads model
weights on first use into the invoking user's Hugging Face cache. Packages do
not contain weights, download them during installation, or start a server.

Run `laya-serve` explicitly. Upstream `LAYA_*` environment variables control
binding, authentication, device selection, and preloading. Upstream defaults
include binding to `0.0.0.0:8000` and preloading models; select the desired
settings before starting it. This package provides no systemd unit.

MCP is deferred to a possible separate package. ONNX inference/export, TileLang,
training/evaluation commands, and other framework integrations are not supported
by this initial package set. Their Python modules may exist in the upstream
wheel, but their optional dependencies and extra commands are not installed.

## Validation and maintenance

The build verifies download SHA256, each wheel's RECORD hashes and sizes, pure
Python tags, fixed layout, licenses, module/distribution versions, and selected
entry points and dependency declarations. Unsupported changes fail clearly.
The current recipe accepts Laya's established core, HTTP, and structured-result
requirements; a changed declaration requires an explicit recipe update.

Update the pinned Click manifest deliberately. Adapter files are recipe inputs,
so changing the pin allocates a packaging revision of the current Laya release.
Rebuild the publisher container to deploy adapter changes.

Static inspection of Debian's October 2026 indexes found the required dependency
chain satisfiable using Trixie plus the named Forky packages on amd64 and arm64.
This does not guarantee future Forky compatibility or establish runtime inference
or HTTP compatibility. No installation, APT simulation, or downloaded application
execution is part of this adapter's verification workflow.

Run offline regression tests with `bash tests/run.sh laya`. For verified live
downloads and a local package build, run the host-side coordinator from the
project root:

```sh
bash tests/laya/coordinate.sh all
```

The coordinator writes logs and reusable downloads under
`build/laya-verification/` and packages under its `output/` directory. It uses a
placeholder maintainer for local verification, never sources `.env`, and neither
publishes to production nor uses real signing keys. Its `prepare` and `verify`
modes can also run separately; build staging is removed after successful builds
and retained on failure.

Sources: [Laya](https://github.com/NandhaKishorM/laya),
[PyPI](https://pypi.org/project/laya/),
[Hub's Click requirement](https://github.com/huggingface/huggingface_hub/blob/v1.23.0/setup.py),
[Click](https://pypi.org/project/click/8.4.2/),
[Debian's Click revert](https://bugs.debian.org/1098507),
[APT preferences](https://manpages.debian.org/trixie/apt/apt_preferences.5.en.html).
