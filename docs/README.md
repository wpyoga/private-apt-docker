# Documentation index

Start here when continuing work without the original chats. Current code and
the live contract take precedence over historical examples in dated handoffs.
Each handoff distinguishes implemented behavior, observed checks, limitations,
and proposals. Ignored `build/` logs and downloaded artifacts may no longer be
available; they are evidence, not required project configuration.

## Project and operations

| Document | Read it for |
| --- | --- |
| [Repository README](../README.md) | Setup, configuration, hook contract, deployment, clients and test commands |
| [Development instructions](../AGENTS.md) | Coding philosophy, conventions and verification workflow |
| [Architecture](../ARCHITECTURE.md) | Current control flow, responsibilities, revisions and storage guarantees |
| [Project foundations handoff](project-foundations-handoff.md) | Original requirements, reasoning, rejected alternatives and later superseding decisions |
| [Publisher operations](publisher-operations.md) | Starting a clone, updating, manual cycles, names/tags, repository/key identity changes, diagnostics and recovery |
| [Storage and signing](storage-and-signing.md) | Public/private layout, migration failure, private agents and missing-key diagnostics |
| [Repository/rebuild handoff](repository-and-rebuild-handoff.md) | Grouping, separate signing identities and source-build origins |
| [Rebuild lock incident](rebuild-lock-incident.md) | Blocking lock correction and independent patch failure |

## Framework and build environment

| Document | Read it for |
| --- | --- |
| [Shared adapter refactor](adapter-refactor-handoff.md) | Common mechanics, local policy and helper checksum declarations |
| [Private build dependencies](build-dependencies.md) | Provider ordering, dependency selection and disposable workers |
| [Build/redistribution handoff](build-and-redistribution-handoff.md) | Development history and boundaries of those extensions |
| [Docker dependency cache](docker-build-cache.md) | Image stages, invalidation, refresh and historical tests |
| [Builder image investigation](builder-image-investigation.md) | Considered prebuilt images and compatibility findings |
| [Local Debian tools](local-tools.md) | Project-local tool setup and retained evidence |

## Package guides and investigation history

| Package or topic | Current guide and detailed history |
| --- | --- |
| Codex | [Architecture example](../ARCHITECTURE.md#existing-packaging-examples), [original adapter/stream-config handoff](codex-and-stream-config-handoff.md), and [foundations](project-foundations-handoff.md); implementation in `packages/repack/codex/` |
| Ghostty | [Packaging, operations and history](ghostty.md) |
| GIMP 3.2 | [Current guide](gimp-3.2.md), [original chat handoff](gimp-original-chat-handoff.md), [investigation history](gimp-3.2-investigation-history.md), [packaging/test refactor](gimp-packaging-and-test-refactor-handoff.md) |
| GIMP startup/libraries | [Startup and Debian dependency investigation](gimp-startup-and-dependencies-handoff.md), [AppImage build base](gimp-appimage-build-base.md) |
| GIMP failures | [Extraction memory incident](gimp-extraction-memory-incident.md), [publisher/download incidents](gimp-publisher-incident.md) |
| GIMP help 3.2 | [Current guide](gimp-help-3.2.md), [split/history](gimp-help-split-handoff.md) |
| Thorium streams | [Packaging/investigation](thorium.md), [continuation and memory failure handoff](thorium-handoff.md) |
| Cromite | [Packaging, profile-path correction and validation limits](cromite.md) |
| Zed | [Packaging, libraries and laptop acceptance](zed.md) |
| Laya | [Current guide](laya.md), [requirements and dependency/Click decisions](laya-handoff.md) |
| USBImager | [Current guide](usbimager.md), [implementation and verification handoff](usbimager-handoff.md) |
| xfce4-terminal | [Patches, Debian baseline, build and laptop checks](xfce4-terminal.md) |
| xfce4-screensaver | [Patch, arm64 build correction and remaining checks](xfce4-screensaver.md) |
| libgit2 1.9 | [Current guide](libgit2-1.9.md), [source recipe and build evidence](libgit2-1.9-handoff.md) |
| OpenShell | [Current guide](openshell.md), [byte-preserving redistribution handoff](openshell-redistribution-handoff.md) |
| VirtualBox | [Canceled packaging investigation](virtualbox-investigation-history.md); no adapter is supplied |
| Vim final newlines | [Editor behavior discussed during development](vim-final-newlines.md) |

Before a change, read the relevant guide and inspect the current adapter, tests,
and working tree. Before claiming a bug is fixed or a package is deployable,
check that the cited evidence exercises that behavior at the relevant revision.
Successful static packaging or an old test count is not proof of current desktop
behavior, production deployment, or all architectures.
