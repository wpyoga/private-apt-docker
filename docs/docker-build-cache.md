# Docker dependency caching: design and implementation handoff

Recorded on 2026-11-13 to preserve the dependency-caching conversation so it can
be deleted. The original implementation is committed as `86b6123`
(`fix: make use as much of docker layer caching as possible`). This document
separates that implementation and its recorded checks from subsequent repository
changes inspected when writing this handoff.

## Original problem and decision

The maintainer reported that modifying a package caused slow Docker builds that
installed many dependencies again. They asked whether dependencies could be
installed before copying adapters, whether that would miss new dependencies,
whether a change signal could trigger installation, and whether a Debian builder
container with dependencies already installed would be preferable.

The agreed implementation installs dependencies in reusable Docker stages before
copying the framework and adapters into the final images. Dependency declarations
are themselves the change signal. There is no separate flag, revision counter,
manual timestamp, or central dependency registry to keep synchronized.

The maintainer authorized implementation and planned to try the resulting images.
The original work changed the build definitions and documentation, ran local
checks, and left actual image builds and deployment for the maintainer. No Docker
build timing or measured speedup was established by that work.

This uses locally built Debian toolchain images defined by this checkout. It does
not require publishing or maintaining a separate builder image in a registry.
The later [prebuilt builder-image investigation](builder-image-investigation.md)
records alternative images and the maintainer's explicit decision against
publishing our own builder image. That later investigation did not replace the
local stage design described here.

## Why dependencies were installed again

The original root [Dockerfile](../Dockerfile) already installed publisher tools
before copying `packages/`. Its APT layer could therefore survive adapter edits.
The expensive invalidation happened in the source-build images:

```text
Root publisher image:
  Debian → install publisher tools → copy framework and every adapter

Old xfce4-terminal Dockerfile:
  FROM publisher → install architecture-specific build dependencies
```

[Compose](../compose.yaml) supplied the completed publisher service image as a
named additional build context. The adapter Dockerfile began with
`FROM publisher`. Editing any copied adapter changed that base image, making the
following dependency installation depend on changed inputs. Docker could still
reuse earlier publisher-tool layers; the symptom did not establish that every
layer was rebuilt from scratch.

The solution removes the completed publisher image from the ancestry of the
build-dependency installation stage. Merely moving a `COPY` within the old
adapter Dockerfile would not remove the already-copied adapters from its base.

## Implemented files and compatibility

Commit `86b6123` changed these files:

| File | Change |
| --- | --- |
| [Dockerfile](../Dockerfile) | Introduced shared tools, publisher-file, rebuild-toolchain, and final image stages |
| [compose.yaml](../compose.yaml) | Selected the root `rebuild` target and `TARGET_ARCH` for both rebuild services; removed publisher service build contexts |
| `packages/rebuild/xfce4-terminal/Dockerfile` | Removed the old adapter Dockerfile based on the completed publisher image |
| [Terminal dependency installer](../packages/rebuild/xfce4-terminal/install-build-dependencies) | Moved the existing dependency list into an adapter-owned script, with early architecture validation |
| [ARCHITECTURE.md](../ARCHITECTURE.md), [README.md](../README.md), [terminal notes](xfce4-terminal.md) | Explained build targets, dependency refreshes, and recipe-checksum effects |

The default final target remains `publisher`. Existing plain `docker build .`
commands, including setup's publisher build, continue to select the repack image.
Compose no longer needs `build.additional_contexts` service references for this
relationship. Builds should use modern Docker with BuildKit so unused stages
are skipped when selecting the default publisher target.

The shared tools stage supplies the existing entrypoint, working directory,
repository volume, and framework environment. Both final targets inherit those
settings. Compose still supplies each service's runtime repository group,
architecture selection, UID/GID, storage, and signing configuration.

## Current stage graph

At handoff time, the root Dockerfile has this dependency graph:

```text
debian:trixie-slim
└── tools: install common publisher tools; set shared image configuration
    ├── publisher-files: copy Dockerfile, entrypoint, update script, lib/, packages/
    │   └── publisher: default final target
    └── rebuild-tools: TARGET_ARCH=amd64 or arm64
        ├── copy and run terminal dependency installer
        ├── copy and run screensaver dependency installer
        ├── copy and run libgit2 dependency installer
        └── rebuild: copy /opt/apt-publisher/ from publisher-files
```

Although `publisher-files` appears before `rebuild-tools` in the Dockerfile,
`rebuild-tools` starts from `tools`, so the stages are separate branches. Its
installation steps do not inherit the adapter copies. The final `rebuild` image
combines the toolchain with the completed publisher files using `COPY --from`.
The final copy preserves the executable modes established in `publisher-files`.

The original implementation installed only terminal dependencies. Later commits
`8ef0683` and `c305f98` added screensaver and libgit2 installers respectively.
Their current order matters: the screensaver installer relies on shared compiler,
Debian packaging, and Xfce tools installed by the terminal installer.

Current dependency declarations are:

- [xfce4-terminal/install-build-dependencies](../packages/rebuild/xfce4-terminal/install-build-dependencies).
- [xfce4-screensaver/install-build-dependencies](../packages/rebuild/xfce4-screensaver/install-build-dependencies).
- [libgit2-1.9/install-build-dependencies](../packages/rebuild/libgit2-1.9/install-build-dependencies).

Each receives the target architecture as its first argument and rejects missing
or unsupported values before package installation. Target development packages
use architecture qualifiers. The Xfce toolchain currently builds amd64 natively
and arm64 through an amd64-hosted cross compiler; `TARGET_ARCH` does not select a
native Docker execution platform. The two target environments stay separate
because their Xfce development packages can pull conflicting architecture-specific
xfconf packages.

No additional Compose service or registry push was introduced for the tools stage.
The current Compose file also has a redistribution service that uses the default
publisher image. That service was added after the original cache change.

## What invalidates which layers

Reuse assumes the same Docker builder still has the necessary cache entries.

| Changed input | Expected effect |
| --- | --- |
| Adapter patch, query/build script, template, or other ordinary adapter file | Recopy publisher files and update the final images; reuse rebuild dependency layers |
| Framework files in `lib/`, `entrypoint.sh`, or `update.sh` | Update publisher-file layers and final image contents; reuse dependency layers |
| Terminal dependency installer | Rerun terminal installation and subsequent screensaver/libgit2 steps for each target being built |
| Screensaver dependency installer | Reuse terminal layers; rerun screensaver and subsequent libgit2 steps |
| libgit2 dependency installer | Reuse earlier installers; rerun libgit2 installation |
| Shared publisher-tool installation command | Rebuild common tools and dependent branches |
| `TARGET_ARCH` | Select a different toolchain cache branch; each architecture can reuse its own previous results |
| Base image resolving to changed contents | Rebuild dependent layers when the changed base is used |
| Cache disabled, pruned, or unavailable on a different builder | Dependency installation can run again despite unchanged source files |

The root Dockerfile is copied into `publisher-files` for package fingerprints.
Editing its text changes that copy, but does not by itself invalidate an earlier
installation instruction whose own inputs and ancestor layers are unchanged.
An edit to the actual shared install command or an ancestor does invalidate it.

A changed dependency installer is copied before its APT step, so its content
change automatically triggers that step. Even a comment change counts as a file
change. There is no need to touch a separate signaling file.

## New dependencies and upstream changes

There are three distinct dependency mechanisms:

1. **Ordinary build tools and Debian development libraries.** Declare them in the
   relevant `install-build-dependencies` script. Rebuild the affected images.
   A new adapter needing additional tools also needs explicit Dockerfile wiring
   for its installer; directory discovery alone does not install tools.
2. **Dependencies introduced by an upstream source release.** Docker cannot
   discover a remote change from unchanged local build inputs. Query/build can
   encounter a new `Build-Depends` requirement while the old toolchain is cached.
   Keep `dpkg-buildpackage` dependency checks enabled, investigate the actual
   requirement, update the installer, and rebuild. Check Debian patches and the
   feature requirement before raising version floors.
3. **Private packages built by another repository stream.** The later optional
   `build-dependencies` declarations select stored provider packages and use a
   host worker to install them in disposable images. See
   [private build dependencies](build-dependencies.md). These declarations are
   separate from the scripts that prepare the ordinary Debian toolchain.

Runtime `Depends` in the published package describes what clients install. It
is not a Docker build-dependency manifest. Changing runtime metadata does not
instruct the builder to install corresponding development libraries.

The local image build does not automatically run `apt-get build-dep` against
each newly queried release, nor does a cache hit refresh Debian's package lists.
The installer combines `apt-get update` and installation within one Docker `RUN`
invocation and removes lists before completing that layer.

## Building, inspecting the cache, and refreshing

Run from the project root with the normal operator settings established. Image
build commands below install packages inside image layers and do not start the
publisher services. Keep logs under ignored `build/` and inspect them only after
the command completes or reaches its bounded timeout.

Build both toolchain images with visible cache decisions saved to a log:

```bash
mkdir -p build/docker-cache-checks
timeout --kill-after=30s 45m \
    docker compose --progress plain build rebuild-amd64 rebuild-arm64 \
    > build/docker-cache-checks/first-build.log 2>&1
```

Repeat the same build into `repeat-build.log`; dependency steps should report
`CACHED` when the cache remains available. After a real adapter edit, build again
into `adapter-edit.log`: the publisher-file copies should change while the
installation layers remain cached. An installer edit should rerun that installer
and later layers. Do not edit production recipes solely to demonstrate caching:
adapter contents participate in package revision selection.

Standalone image builds can select the target explicitly:

```bash
timeout --kill-after=30s 45m \
    docker build --progress=plain --target rebuild --build-arg TARGET_ARCH=amd64 \
    -t private-apt-rebuild-amd64:local . \
    > build/docker-cache-checks/standalone-amd64.log 2>&1
```

Use `TARGET_ARCH=arm64` and the arm64 image tag for the cross toolchain. No named
publisher build context is needed. The first build after restructuring may need
to populate the new dependency layers before ordinary edits become cheaper.

To deliberately refresh base images and installed Debian packages even with
unchanged declarations:

```bash
timeout --kill-after=30s 45m \
    docker compose --progress plain build --pull --no-cache \
    > build/docker-cache-checks/refresh.log 2>&1
```

`--pull` checks for updated base images; `--no-cache` forces installation steps to
run. This is an explicit refresh, not the normal path for adapter edits. APT cache
mounts were discussed as a possible later speed improvement for unavoidable
reinstallation, but none was added by this implementation. Current installers
remove APT lists and do not define BuildKit APT download cache mounts.

For the original direct Compose deployment, the maintainer's test command was
`docker compose up -d --build`. It builds images and starts/recreates services,
which then begin repository update cycles. If images were built separately,
`docker compose up -d` applies them. Restarting an existing container alone does
not copy changed checkout files into its image.

For streams using private build dependencies, follow the current
[isolated-build deployment instructions](build-dependencies.md#running-isolated-builds)
instead of blindly starting ordinary rebuild services alongside host launchers.
The launcher itself builds the normal Compose toolchain image, so it benefits
from these same cached dependency layers.

## Docker caching versus package revisions

Docker cache selection and Debian package revision selection are independent.
[lib/checksum.py](../lib/checksum.py) fingerprints adapter files, declared helpers,
the root Dockerfile text, and `MAINTAINER`. The framework uses matching metadata
from stored packages to choose or resume revisions for current queried targets.
It preserves existing artifacts; no revision counters were added here.

The root Dockerfile change therefore caused an expected one-time recipe change
for repack/rebuild targets. A later patch edit is local to its adapter's recipe,
even though all adapter files are copied into each final image. Byte-preserving
redistribution has its own provenance rules and does not allocate these revisions.

Important limits remain: unchanged Dockerfile text does not fingerprint the
resolved base image or the versions APT installs. Installer contents are included
in their owning adapter's checksum, but are not automatically included in every
other adapter's checksum merely because the installer contributes to the shared
toolchain. A forced image refresh can therefore change the build environment
without automatically allocating new revisions for every consumer. Private
provider snapshots have additional checksum handling described in the private
build-dependency documentation. This cache change did not redesign those rules.

## Verification recorded during the original implementation

The original local results were:

| Check | Recorded outcome |
| --- | --- |
| `bash tests/run.sh --framework` | Passed all 63 tests in that checkout |
| Compose configuration validation | Passed with fixture settings after operator values were absent in the initial attempt |
| `bash -n` on the new terminal installer | Passed |
| Dependency-list comparison | Confirmed the moved list matched the removed adapter Dockerfile |
| Missing/unsupported architecture arguments | Confirmed early failures |
| `git diff --check` | Passed |
| `bash tests/run.sh xfce4-terminal` | Three tests passed; the package-build test failed because the host lacked `quilt` |
| Real Docker image build, cache-hit demonstration, deployment, speed measurement | Not performed in that implementation |

The original Xfce failure was exit 127 with `quilt: command not found` while
applying the adapter's existing patches. The toolchain dependency list still
contained `quilt`; this was a host-side regression-test limitation. The current
terminal tests now stub quilt and test additional behavior, so that historical
failure is not a claim about the current suite.

Retained local evidence, if the ignored build directory has not been cleaned:

```text
build/cache-layout-checks/framework.log
build/cache-layout-checks/compose-config.log
build/cache-layout-checks/compose-config-fixture.log
build/cache-layout-checks/bash-syntax.log
build/cache-layout-checks/dependency-validation.log
build/cache-layout-checks/diff-check.log
build/cache-layout-checks/xfce4-terminal.log
build/cache-layout-checks/xfce4-terminal-diagnostic.log
build/test-run-xefiwi/regression.log
build/test-run-rvl2Ch/regression.log
```

Those logs are development evidence, not permanent repository artifacts. The
results above preserve the findings if the logs are later removed. Later adapter
notes can contain separate successful package or container builds; those do not
retroactively establish a measured cache speedup for this implementation.

This handoff adds documentation only. It does not build or deploy images, run
package/signing tests, change dependency declarations, or touch production data
and keys. Before further implementation, inspect the current working tree and
use [ARCHITECTURE.md](../ARCHITECTURE.md), [README.md](../README.md), and
[AGENTS.md](../AGENTS.md) as the maintained design, operator contract, and
contributor instructions.
