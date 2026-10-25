FROM debian:trixie-slim

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
        python3 \
        tar \
        util-linux \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/apt-publisher
# Keep the build recipe available for package fingerprints at runtime.
COPY Dockerfile entrypoint.sh update.sh ./
COPY lib/ ./lib/
COPY packages/ ./packages/
RUN chmod 755 entrypoint.sh update.sh packages/*/query packages/*/build

ENV FRAMEWORK_DIR=/opt/apt-publisher \
    REPO_DIR=/repo \
    CHECK_INTERVAL=21600 \
    ARCHES="amd64 arm64" \
    CODENAME=trixie

VOLUME /repo

ENTRYPOINT ["/opt/apt-publisher/entrypoint.sh"]
