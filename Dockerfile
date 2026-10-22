FROM debian:trixie-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
  bash ca-certificates curl python3 reprepro gnupg dpkg-dev binutils file tar gzip coreutils \
  && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh update.sh /usr/local/bin/
RUN chmod 755 /usr/local/bin/entrypoint.sh /usr/local/bin/update.sh

ENV REPO_DIR=/repo CHECK_INTERVAL=21600 ARCHES="amd64 arm64" CODENAME=trixie

VOLUME /repo

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

