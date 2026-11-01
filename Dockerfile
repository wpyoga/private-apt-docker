FROM debian:trixie-slim AS tools

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        apt-utils \
        bash \
        binutils \
        ca-certificates \
        coreutils \
        curl \
        dpkg-dev \
        file \
        gnupg \
        gzip \
        jq \
        patchelf \
        python3 \
        squashfs-tools \
        tar \
        util-linux \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

ENV FRAMEWORK_DIR=/opt/apt-publisher \
    REPO_DIR=/repo \
    GNUPGHOME=/gnupg \
    PACKAGES_DIR=/opt/apt-publisher/packages/repack

VOLUME /repo

ENTRYPOINT ["/opt/apt-publisher/entrypoint.sh"]

WORKDIR /opt/apt-publisher

FROM tools AS publisher-files
# Keep the build recipe available for package fingerprints at runtime.
COPY Dockerfile entrypoint.sh update.sh ./
COPY lib/ ./lib/
COPY packages/ ./packages/
RUN chmod 755 entrypoint.sh update.sh packages/*/*/query packages/*/*/build

# Only dependency declarations enter this stage, so adapter edits reuse APT layers.
FROM tools AS rebuild-tools
ARG TARGET_ARCH=amd64
COPY packages/rebuild/xfce4-terminal/install-build-dependencies /tmp/install-build-dependencies
RUN bash /tmp/install-build-dependencies "$TARGET_ARCH" \
    && rm /tmp/install-build-dependencies
COPY packages/rebuild/xfce4-screensaver/install-build-dependencies /tmp/install-screensaver-dependencies
RUN bash /tmp/install-screensaver-dependencies "$TARGET_ARCH" \
    && rm /tmp/install-screensaver-dependencies
COPY packages/rebuild/libgit2-1.9/install-build-dependencies /tmp/install-libgit2-dependencies
RUN bash /tmp/install-libgit2-dependencies "$TARGET_ARCH" \
    && rm /tmp/install-libgit2-dependencies
ENV XFCE_BUILD_ARCH=$TARGET_ARCH LIBGIT2_BUILD_ARCH=$TARGET_ARCH

FROM rebuild-tools AS rebuild
COPY --from=publisher-files /opt/apt-publisher/ /opt/apt-publisher/

# Keep ordinary docker builds and setup on the repack publisher by default.
FROM publisher-files AS publisher
