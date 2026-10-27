#!/bin/bash
set -Eeuo pipefail

show_failure_logs() {
    local LOG
    for LOG in /test/headless.log /test/gui.log; do
        if [[ -f "$LOG" ]]; then tail -n 100 "$LOG" >&2; fi
    done
}
trap show_failure_logs ERR

mkdir -p "$HOME" "$TMPDIR" "$XDG_CACHE_HOME"
unset LD_LIBRARY_PATH LD_PRELOAD BABL_PATH GEGL_PATH GI_TYPELIB_PATH
DESKTOP_ENTRY=${1:-/usr/share/applications/org.gimp.GIMP.Stable.desktop}
desktop-file-validate "$DESKTOP_ENTRY"
gimp --version
if [[ "${EXPECT_REPACK:-0}" == 1 ]]; then
    [[ "$(dpkg-query --show --showformat='${X-Publisher-Stream}' gimp)" == gimp-3.2 ]]
    for PACKAGE in libheif1 libheif-plugin-aomenc libheif-plugin-dav1d \
        libheif-plugin-j2kdec libheif-plugin-j2kenc libheif-plugin-libde265 libheif-plugin-x265; do
        [[ "$(dpkg-query --show --showformat='${db:Status-Status}' "$PACKAGE")" == installed ]]
    done
    for PLUGIN in aomenc dav1d j2kdec j2kenc libde265 x265; do
        test -f "/usr/lib/x86_64-linux-gnu/libheif/plugins/libheif-$PLUGIN.so"
    done
    if grep -R '^LIBHEIF_PLUGIN_PATH=' /usr/lib/x86_64-linux-gnu/gimp/3.0/environ; then
        echo 'Unexpected private HEIF plugin override' >&2
        exit 1
    fi
    printf 'HEIF_DEPENDENCIES_PASS\n'
fi

check_log() {
    local LOG=$1
    grep -F 'IMAGE_TEST_PASS:' "$LOG"
    grep -E 'FORMAT_TEST_PASS:|RUNTIME_VERSION:' "$LOG"
    if grep -Ei 'Traceback|error while loading shared libraries|undefined symbol|installation seems broken|Failed to query|Gimp-Core-CRITICAL|fatal error|Gtk:ERROR' "$LOG"; then
        echo "Runtime failure in $LOG" >&2
        exit 1
    fi
}

gimp --no-interface --new-instance --no-data --no-fonts --console-messages --quit \
    --batch-interpreter=python-fu-eval --batch="exec(open('/test/smoke.py').read())" \
    > /test/headless.log 2>&1
check_log /test/headless.log
export HOME=/test/gui-profile
export GIMP3_DIRECTORY="$HOME"
mkdir -p "$HOME"
dbus-run-session -- xvfb-run -a gimp --new-instance --console-messages --quit \
    --batch-interpreter=python-fu-eval --batch="exec(open('/test/smoke.py').read())" \
    > /test/gui.log 2>&1
check_log /test/gui.log
printf 'CONTAINER_TEST_PASS: headless and virtual-display GUI\n'
