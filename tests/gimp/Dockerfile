FROM debian:trixie-slim AS base
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        desktop-file-utils xvfb xauth dbus-x11
ENV HOME=/test/profile \
    GIMP3_DIRECTORY=/test/profile \
    XDG_CACHE_HOME=/test/cache \
    TMPDIR=/test/tmp \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /test

FROM base AS clean
COPY debs/ /test/debs/
COPY smoke.py smoke.sh audit.py /test/
RUN apt-get --simulate install /test/debs/*.deb \
    && apt-get install -y --no-install-recommends /test/debs/*.deb \
    && dpkg --audit \
    && python3 /test/audit.py
COPY sdk-test.c /test/
RUN apt-get install -y --no-install-recommends build-essential \
        libbabl-dev libgegl-dev \
    && pkg-config --atleast-version=0.4.66 gimp-gegl-0.4 \
    && pkg-config --atleast-version=0.1.116 gimp-babl-0.1 \
    && gimptool --version \
    && gcc /test/sdk-test.c -o /test/sdk-test $(pkg-config --cflags --libs gimpui-3.0) \
    && /test/sdk-test
RUN --network=none EXPECT_REPACK=1 GIMP_TEST_FORMATS=1 bash /test/smoke.sh

FROM base AS reinstall
RUN apt-get install -y --no-install-recommends gimp
COPY debs/ /test/debs/
COPY smoke.py smoke.sh audit.py /test/
RUN --network=none mkdir -p "$TMPDIR" \
    && xvfb-run -a bash /test/smoke.sh /usr/share/applications/gimp.desktop
RUN sha256sum /usr/lib/x86_64-linux-gnu/libbabl-0.1.so.0 \
        /usr/lib/x86_64-linux-gnu/libgegl-0.4.so.0 > /test/system-libraries.sha256 \
    && dpkg-query -W libbabl-0.1-0 libgegl-0.4-0t64 \
        gir1.2-babl-0.1 gir1.2-gegl-0.4 > /test/system-libraries.before \
    && apt-get remove -y gimp gimp-data libgimp-3.0-0 gir1.2-gimp-3.0 \
    && printf '\n# local-repack-reinstall-test\n' >> /etc/gimp/3.0/gimprc \
    && apt-get --simulate install /test/debs/*.deb \
    && apt-get install -y --no-install-recommends \
        -o Dpkg::Options::=--force-confold /test/debs/*.deb \
    && grep -Fq '# local-repack-reinstall-test' /etc/gimp/3.0/gimprc \
    && sha256sum --check /test/system-libraries.sha256 \
    && dpkg-query -W libbabl-0.1-0 libgegl-0.4-0t64 \
        gir1.2-babl-0.1 gir1.2-gegl-0.4 > /test/system-libraries.after \
    && cmp /test/system-libraries.before /test/system-libraries.after \
    && dpkg --audit \
    && python3 /test/audit.py
RUN --network=none EXPECT_REPACK=1 GIMP_TEST_FORMATS=1 bash /test/smoke.sh
