# Private build dependencies

Runtime dependencies already use Debian control `Depends` and APT. The optional
adapter file `build-dependencies` adds private **build** dependencies. Each line
contains a provider's RELEASE_STREAM, a binary package, and optionally a Debian
version relation and version:

```text
libgit2-1.9 libgit2-dev >= 1.9.1
```

Supported relations are `<<`, `<=`, `=`, `>=`, and `>>`. Blank lines and whole-line
comments are allowed. Without a version constraint, any stored version qualifies.
Use stream identities rather than adapter directory names. Dependencies must be
in the same configured repository group. Package names can be shared by unrelated
streams, but the provider must explicitly declare the requested binary name.

The coordinator validates declarations and processes providers before consumers.
Cycles, unknown providers and invalid declarations block the affected streams;
unrelated streams still run, and publication still happens after the stream loop.
A failed provider can be satisfied by a previous complete stored build meeting
the constraint. Missing dependencies block only the consumer architectures that
cannot be satisfied. A stream finishes its architectures before the next starts.

For each provider and architecture, selection uses Debian version ordering to
choose the newest complete output set meeting every constraint. Architecture: all
outputs can satisfy either architecture. The dependency snapshot includes all
outputs of the selected provider build, including providers needed transitively.
Overlapping binary names between selected providers are rejected. APT resolves
runtime dependencies using this snapshot and the builder's Debian sources.
Missing or conflicting runtime dependencies fail installation rather than being
silently ignored. Only explicitly requested build packages and their APT runtime
dependencies are installed; unrelated outputs such as experimental development
packages are not installed.

The snapshot is a temporary local APT repository built from validated stored
packages under the repository lock, including packages built earlier in the same
cycle. It requires neither public HTTP access nor intermediate signing or
publication. Its `trusted=yes` setting applies only to the copied local snapshot,
whose bytes are checked against the selected SHA256 digests.

Consumer packages record the private packages actually installed in
`X-Private-Build-Dependencies` and a SHA256 of the full installed package list in
`X-Build-Environment-SHA256`. These fields are also available in published indexes.

Dependency versions and artifact hashes participate in the consumer's recipe
checksum. Changing the selected snapshot rebuilds the consumer's current queried
release using the existing revision rules. Previous artifacts remain unchanged.
The fingerprint includes both architectures so separate architecture coordinators
agree on recipe identity. When a missing architecture first becomes available,
that snapshot change can cause one additional consumer revision. Changes to
ordinary Debian dependencies or a base image resolving from unchanged Dockerfile
text retain the existing checksum limitations.

# Running isolated builds

Existing adapters without private build dependencies keep their existing build
path. Adapters declaring dependencies run their build hook in a disposable Docker
container. The host launches Docker; the coordinator has no Docker socket.
Root APT installation takes place only in Docker image layers. Compilation runs
as the configured publisher UID/GID, with only that stream's workspace mounted
writable. Signing keys, repository storage and operator environment secrets are
not mounted or forwarded to the build container.

The host needs Docker with Compose, Bash, jq, flock, realpath, timeout, and access
to this checkout. Run the launcher as the UID/GID configured for the publisher,
with Docker access and permission to write `build/` in the checkout. Identical
ownership avoids root-owned bind-mounted output and keeps signing key permissions
intact. The launcher validates this requirement before starting.

Stop the ordinary rebuild services before replacing them with host launchers:

```sh
docker compose stop rebuild-amd64 rebuild-arm64
bash rebuild.sh amd64 --loop
# Run the second command in a separate terminal or host service:
bash rebuild.sh arm64 --loop
```

The default `--once` runs one complete cycle and returns its status. `--loop`
keeps the existing CHECK_INTERVAL wait after each complete cycle. The repack
service can continue through Compose as before. The shared repository flock still
serializes architecture cycles. Do not run two launchers for one architecture.
There is no change to production data or signing identities from installing this
feature; deployment remains an operator step.

The launcher builds the normal rebuild image first, without private packages.
The host worker derives a temporary image from that exact image ID, adds the
private dependency snapshot, and installs exact selected build package versions.
It then runs the normal `build VERSION ARCH OUTPUT_DIR` hook. Query still runs
in the coordinator. Hooks can retain absolute workspace paths from query;
FRAMEWORK_DIR and ADAPTER_DIR in the worker point to copied framework and adapter
files and must be used as supplied. Build tools and ordinary Debian dependencies
must already be declared in the base toolchain image.

Logs are under `build/workers/ARCH/`: `image-build.log`, `coordinator.log`,
`worker.log`, and each queued job's `build.log`. A failed job retains its request,
selected packages, and log. Successful job contexts are removed; their log and
installed package list are copied into the stream workspace, which follows the
normal cycle retention policy. Temporary worker containers and images are
removed after completion. A job has a 115-minute worker limit and a two-hour
coordinator limit; timeouts fail the stream and preserve evidence.

Run all checks for this feature with one command:

```sh
bash tests/verify-build-dependencies.sh
```

This runs the complete offline suite, the Docker integration test, shell and
Python syntax checks, and `git diff --check`, retaining named logs under
`build/dependency-checks-*/`. It needs local socket access for the offline HTTP
fixtures and Docker access for the integration test. Signing is unchanged and
the separate signing test is not included.

The integration test uses an existing
`private-apt-rebuild-amd64:local` image, creates a fixture library and development
package, installs them in a temporary image, compiles and executes a consumer,
and checks failure retention, retry, metadata and repeat-cycle reuse. Supply a
different base image as its first argument if needed. It uses isolated storage
and signing stubs, never production data or keys. This native runtime test covers
amd64; arm64 dependency selection is covered offline but runtime validation on
arm64 remains separate.

The [diffofdiffs adapter](diffofdiffs.md) uses this mechanism to build against
the private libgit2 packages from a verified upstream release tarball.
Investigate actual feature and bug-fix requirements, including Debian patches,
before increasing a dependency version solely because the upstream version
number is newer.
