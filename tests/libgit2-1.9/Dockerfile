FROM debian:trixie-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential pkgconf ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY packages/ /packages/
RUN apt-get update \
    && apt-get install -y --no-install-recommends /packages/libgit2-1.9_*_amd64.deb /packages/libgit2-dev_*_amd64.deb \
    && rm -rf /var/lib/apt/lists/*
COPY smoke.c /smoke.c
RUN cc /smoke.c -o /smoke $(pkg-config --cflags --libs libgit2) \
    && /smoke
# The experimental development package replaces the normal development package.
RUN apt-get update \
    && apt-get install -y --no-install-recommends /packages/libgit2-experimental1.9_*_amd64.deb /packages/libgit2-experimental-dev_*_amd64.deb \
    && rm -rf /var/lib/apt/lists/*
RUN cc /smoke.c -o /smoke-experimental $(pkg-config --cflags --libs libgit2) \
    && /smoke-experimental
