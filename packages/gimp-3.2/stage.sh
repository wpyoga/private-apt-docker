#!/bin/bash
set -Eeuo pipefail
shopt -s nullglob

: "${ADAPTER_DIR:?ADAPTER_DIR must be set and non-empty}"
: "${SOURCE_USR:?SOURCE_USR must be set and non-empty}"
: "${STAGING_DIR:?STAGING_DIR must be set and non-empty}"
: "${MULTIARCH:?MULTIARCH must be set and non-empty}"

for PACKAGE in gimp gimp-data libgimp-3.0-0 gir1.2-gimp-3.0 gimp-bundled-runtime; do
    mkdir -p "$STAGING_DIR/$PACKAGE/usr/lib/$MULTIARCH"
done
APPLICATION="$STAGING_DIR/gimp"
DATA="$STAGING_DIR/gimp-data"
LIBRARIES="$STAGING_DIR/libgimp-3.0-0/usr/lib/$MULTIARCH"
TYPELIBS="$STAGING_DIR/gir1.2-gimp-3.0/usr/lib/$MULTIARCH/girepository-1.0"
PRIVATE="$STAGING_DIR/gimp-bundled-runtime/usr/lib/$MULTIARCH/gimp/bundled"
mkdir -p "$APPLICATION/usr/bin" "$APPLICATION/usr/libexec" "$TYPELIBS" \
    "$PRIVATE/girepository-1.0" "$DATA/usr/share" "$DATA/etc" "$DATA/usr/etc"

for EXECUTABLE in gimp-3.2 gimp-console-3.2 gimp-script-fu-interpreter-3.0; do
    cp -a "$SOURCE_USR/bin/$EXECUTABLE" "$APPLICATION/usr/bin/$EXECUTABLE.bin"
    sed -e "s/@MULTIARCH@/$MULTIARCH/g" -e "s/@EXECUTABLE@/$EXECUTABLE/g" \
        "$ADAPTER_DIR/launcher.in" > "$APPLICATION/usr/bin/$EXECUTABLE"
    chmod 755 "$APPLICATION/usr/bin/$EXECUTABLE"
done
for ALIAS in gimp gimp-3 org.gimp.GIMP.Stable; do
    ln -s gimp-3.2 "$APPLICATION/usr/bin/$ALIAS"
done
ln -s gimp-console-3.2 "$APPLICATION/usr/bin/gimp-console"
cp -a "$SOURCE_USR/libexec/gimp-debug-tool-3.2" "$APPLICATION/usr/libexec/"
ln -s gimp-debug-tool-3.2 "$APPLICATION/usr/libexec/gimp-debug-tool"
ln -s gimp-debug-tool-3.2 "$APPLICATION/usr/libexec/gimp-debug-tool-3"
cp -a "$SOURCE_USR/lib/$MULTIARCH/gimp" "$APPLICATION/usr/lib/$MULTIARCH/"
printf '# Runtime paths are supplied by the native launcher.\n' \
    > "$APPLICATION/usr/lib/$MULTIARCH/gimp/3.0/environ/native-runtime.env"

for LIBRARY in "$SOURCE_USR/lib/$MULTIARCH/"libgimp*.so*; do
    # Development linker symlinks are not part of the runtime packages.
    if [[ -L "$LIBRARY" && "$LIBRARY" == *.so ]]; then
        continue
    fi
    cp -a "$LIBRARY" "$LIBRARIES/"
done
cp -a "$SOURCE_USR/lib/$MULTIARCH/girepository-1.0/"Gimp*.typelib "$TYPELIBS/"
for LIBRARY in "$SOURCE_USR/lib/$MULTIARCH/"libbabl*.so* "$SOURCE_USR/lib/$MULTIARCH/"libgegl*.so*; do
    if [[ -L "$LIBRARY" && "$LIBRARY" == *.so ]]; then
        continue
    fi
    cp -a "$LIBRARY" "$PRIVATE/"
done
cp -a "$SOURCE_USR/lib/$MULTIARCH/babl-0.1" "$SOURCE_USR/lib/$MULTIARCH/gegl-0.4" "$PRIVATE/"
cp -a "$SOURCE_USR/lib/$MULTIARCH/girepository-1.0/Babl-0.1.typelib" \
    "$SOURCE_USR/lib/$MULTIARCH/girepository-1.0/Gegl-0.4.typelib" "$PRIVATE/girepository-1.0/"

cp -a "$SOURCE_USR/share/gimp" "$DATA/usr/share/"
cp -a "$SOURCE_USR/etc/gimp" "$DATA/etc/"
ln -s ../../etc/gimp "$DATA/usr/etc/gimp"
mkdir -p "$DATA/usr/share/applications" "$DATA/usr/share/metainfo"
cp -a "$SOURCE_USR/share/applications/org.gimp.GIMP.Stable.desktop" "$DATA/usr/share/applications/"
cp -a "$SOURCE_USR/share/metainfo/org.gimp.GIMP.Stable.appdata.xml" "$DATA/usr/share/metainfo/"
sed -i 's/^Icon=.*/Icon=gimp/' "$DATA/usr/share/applications/org.gimp.GIMP.Stable.desktop"
(
    cd "$SOURCE_USR"
    find share/icons -type f -name 'gimp.*' -exec cp --parents -t "$DATA/usr" {} +
    find share/locale -type f -name 'gimp*.mo' -exec cp --parents -t "$DATA/usr" {} +
)
