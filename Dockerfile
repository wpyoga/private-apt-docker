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
        jq \
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
    GNUPGHOME=/gnupg \
    PACKAGES_DIR=/opt/apt-publisher/packages

VOLUME /repo

ENTRYPOINT ["/opt/apt-publisher/entrypoint.sh"]
