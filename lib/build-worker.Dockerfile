# check=skip=InvalidDefaultArgInFrom
# The host worker always supplies its pinned local base image.
ARG BUILD_IMAGE
FROM ${BUILD_IMAGE}
USER root
COPY repository/ /build-repository/
COPY install /build-install
COPY framework/ /framework/
ARG TARGET_ARCH
RUN dpkg --add-architecture "$TARGET_ARCH" \
    && printf '%s\n' 'deb [trusted=yes] file:/build-repository ./' > /etc/apt/sources.list.d/private-build.list \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive bash -Eeuo pipefail -c 'mapfile -t PACKAGES < /build-install; apt-get install -y --no-install-recommends "${PACKAGES[@]}"' \
    && dpkg-query -W -f='${Package}\t${Version}\t${Architecture}\n' > /build-installed-packages \
    && rm /etc/apt/sources.list.d/private-build.list \
    && rm -rf /var/lib/apt/lists/* /build-repository /build-install
ENTRYPOINT ["/bin/bash"]
