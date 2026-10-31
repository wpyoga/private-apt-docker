FROM publisher
ARG TARGET_ARCH=amd64
RUN case "$TARGET_ARCH" in amd64|arm64) ;; *) exit 1 ;; esac \
    && dpkg --add-architecture "$TARGET_ARCH" \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential crossbuild-essential-arm64 debhelper devscripts quilt \
        gtk-doc-tools intltool libxml-perl xfce4-dev-tools \
        "libglib2.0-dev:$TARGET_ARCH" "libgtk-3-dev:$TARGET_ARCH" \
        "libpcre2-dev:$TARGET_ARCH" "libstartup-notification0-dev:$TARGET_ARCH" \
        "libutempter-dev:$TARGET_ARCH" "libvte-2.91-dev:$TARGET_ARCH" \
        "libxfce4ui-2-dev:$TARGET_ARCH" \
    && rm -rf /var/lib/apt/lists/*
ENV XFCE_BUILD_ARCH=$TARGET_ARCH
