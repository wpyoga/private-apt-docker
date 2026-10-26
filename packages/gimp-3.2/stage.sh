#!/bin/bash
set -Eeuo pipefail
shopt -s nullglob

: "${ADAPTER_DIR:?ADAPTER_DIR must be set and non-empty}"
: "${SOURCE_USR:?SOURCE_USR must be set and non-empty}"
: "${STAGING_DIR:?STAGING_DIR must be set and non-empty}"
: "${MULTIARCH:?MULTIARCH must be set and non-empty}"

for PACKAGE in gimp gimp-data libgimp-3.0-0 gir1.2-gimp-3.0 gimp-bundled-runtime \
    libgimp-3.0-bin libgimp-3.0-dev libgimp-3.0-doc; do
    mkdir -p "$STAGING_DIR/$PACKAGE/usr/lib/$MULTIARCH"
done
APPLICATION="$STAGING_DIR/gimp"
DATA="$STAGING_DIR/gimp-data"
LIBRARIES="$STAGING_DIR/libgimp-3.0-0/usr/lib/$MULTIARCH"
TYPELIBS="$STAGING_DIR/gir1.2-gimp-3.0/usr/lib/$MULTIARCH/girepository-1.0"
PRIVATE="$STAGING_DIR/gimp-bundled-runtime/usr/lib/$MULTIARCH/gimp/bundled"
TOOLS="$STAGING_DIR/libgimp-3.0-bin"
DEVELOPMENT="$STAGING_DIR/libgimp-3.0-dev"
mkdir -p "$APPLICATION/usr/bin" "$APPLICATION/usr/libexec" "$TYPELIBS" \
    "$PRIVATE/girepository-1.0" "$DATA/usr/share" "$DATA/etc" "$DATA/usr/etc"

for EXECUTABLE in gimp-3.2 gimp-console-3.2 gimp-script-fu-interpreter-3.0; do
    cp -a "$SOURCE_USR/bin/$EXECUTABLE" "$APPLICATION/usr/bin/$EXECUTABLE.bin"
    sed -e "s/@MULTIARCH@/$MULTIARCH/g" -e "s/@EXECUTABLE@/$EXECUTABLE/g" \
        "$ADAPTER_DIR/launcher.in" > "$APPLICATION/usr/bin/$EXECUTABLE"
    chmod 755 "$APPLICATION/usr/bin/$EXECUTABLE"
done

mkdir -p "$TOOLS/usr/bin" "$TOOLS/usr/share/man/man1" \
    "$DEVELOPMENT/usr/include/gimp-3.0/bundled" \
    "$DEVELOPMENT/usr/lib/$MULTIARCH/pkgconfig" \
    "$DEVELOPMENT/usr/lib/$MULTIARCH/gimp/bundled"
cp -a "$SOURCE_USR/bin/gimptool-3.2" "$TOOLS/usr/bin/"
ln -s gimptool-3.2 "$TOOLS/usr/bin/gimptool"
ln -s gimptool-3.2 "$TOOLS/usr/bin/gimptool-3"
sed -e "s/@GIMP_VERSION@/$UPSTREAM_VERSION/g" \
    -e 's|@manpage_gimpdir@|\\$XDG_CONFIG_HOME/GIMP/3.2|g' \
    -e "s|@gimpplugindir@|/usr/lib/$MULTIARCH/gimp/3.0|g" \
    -e 's|@gimpdatadir@|/usr/share/gimp/3.0|g' \
    "$ADAPTER_DIR/gimptool.1.in" | gzip -n -9 > "$TOOLS/usr/share/man/man1/gimptool-3.2.1.gz"
ln -s gimptool-3.2.1.gz "$TOOLS/usr/share/man/man1/gimptool.1.gz"
ln -s gimptool-3.2.1.gz "$TOOLS/usr/share/man/man1/gimptool-3.1.gz"
cp -a "$SOURCE_USR/include/gimp-3.0/." "$DEVELOPMENT/usr/include/gimp-3.0/"
cp -a "$SOURCE_USR/include/babl-0.1" "$SOURCE_USR/include/gegl-0.4" \
    "$DEVELOPMENT/usr/include/gimp-3.0/bundled/"
for LIBRARY in "$SOURCE_USR/lib/$MULTIARCH/"libgimp*.so; do
    cp -a "$LIBRARY" "$DEVELOPMENT/usr/lib/$MULTIARCH/"
done
for LIBRARY in "$SOURCE_USR/lib/$MULTIARCH/"libbabl*.so "$SOURCE_USR/lib/$MULTIARCH/"libgegl*.so; do
    cp -a "$LIBRARY" "$DEVELOPMENT/usr/lib/$MULTIARCH/gimp/bundled/"
done
for NAME in gimp-3.0 gimpui-3.0 gimpthumb-3.0; do
    sed -e 's/gegl-0.4/gimp-gegl-0.4/g' \
        -e 's|^gimpsysconfdir=.*|gimpsysconfdir=/etc/gimp/3.0|' \
        "$SOURCE_USR/lib/$MULTIARCH/pkgconfig/$NAME.pc" \
        > "$DEVELOPMENT/usr/lib/$MULTIARCH/pkgconfig/$NAME.pc"
done
for NAME in babl-0.1 gegl-0.4; do
    sed -e 's|^prefix=.*|prefix=/usr|' \
        -e 's|^includedir=.*|includedir=${prefix}/include/gimp-3.0/bundled|' \
        -e "s|^libdir=.*|libdir=/usr/lib/$MULTIARCH/gimp/bundled|" \
        -e "s|^pluginsdir=.*|pluginsdir=\${libdir}/$NAME|" \
        -e 's/Requires: \(.*\)babl-0.1/Requires: \1gimp-babl-0.1/' \
        -e '/^Libs:/s|$| -Wl,-rpath,${libdir}|' \
        "$SOURCE_USR/lib/$MULTIARCH/pkgconfig/$NAME.pc" \
        > "$DEVELOPMENT/usr/lib/$MULTIARCH/pkgconfig/gimp-$NAME.pc"
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
