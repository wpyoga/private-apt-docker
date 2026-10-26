"""Check native image processing and codec round trips in an isolated profile."""

from gi.repository import Gimp, Gio, Gegl, Babl
from pathlib import Path
import os
import io
import subprocess
import tarfile


if os.environ.get("EXPECT_REPACK") == "1":
    # Debian slim can exclude installed documentation. Read the expected
    # versions from the actual package rather than silently skipping the check.
    archives = list(Path("/test/debs").glob("gimp-bundled-runtime_*.deb"))
    assert len(archives) == 1, archives
    payload = subprocess.check_output(["dpkg-deb", "--fsys-tarfile", archives[0]])
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        record = archive.extractfile("./usr/share/doc/gimp-bundled-runtime/upstream-versions")
        assert record is not None
        versions = dict(line.split(": ", 1) for line in record.read().decode().splitlines())
    for name, library in (("babl", Babl), ("gegl", Gegl)):
        actual = ".".join(str(part) for part in library.get_version())
        assert actual == versions[name], (name, actual, versions[name])
        print(f"RUNTIME_VERSION: {name} {actual}")


def check_image(image, tolerance=0):
    assert (image.get_width(), image.get_height()) == (64, 64)
    pixel = bytes(image.get_layers()[0].get_buffer().get(
        Gegl.Rectangle.new(32, 32, 1, 1), 1.0, "R'G'B'A u8", Gegl.AbyssPolicy.NONE))
    assert len(pixel) == 4 and max(pixel[:3]) <= tolerance and pixel[3] == 255, pixel


out = Path(os.environ["TMPDIR"])
image = Gimp.Image.new(64, 64, Gimp.ImageBaseType.RGB)
layer = Gimp.Layer.new(image, "Test", 64, 64, Gimp.ImageType.RGB_IMAGE,
                      100, Gimp.LayerMode.NORMAL)
image.insert_layer(layer, None, 0)
assert layer.fill(Gimp.FillType.WHITE)
layer.merge_filter(Gimp.DrawableFilter.new(layer, "gegl:invert-linear", "Invert"))
check_image(image)
path = Gio.File.new_for_path(str(out / "test.xcf"))
assert Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, path)
loaded = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, path)
check_image(loaded)

formats = [("png", "file-png-export")]
if os.environ.get("GIMP_TEST_FORMATS") == "1":
    formats += [("jpeg", "file-jpeg-export"), ("tiff", "file-tiff-export"),
                ("webp", "file-webp-export"), ("heic", "file-heif-export"),
                ("avif", "file-heif-av1-export"), ("jxl", "file-jpegxl-export"),
                ("xpm", "file-xpm-export")]
for extension, name in formats:
    procedure = Gimp.get_pdb().lookup_procedure(name)
    assert procedure is not None, name
    config = procedure.create_config()
    config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
    config.set_property("image", loaded)
    if extension == "tiff":
        # The default-thumbnail discrepancy is recorded separately and deferred.
        config.set_property("include-thumbnail", False)
    path = Gio.File.new_for_path(str(out / f"test.{extension}"))
    config.set_property("file", path)
    result = procedure.run(config)
    assert result.index(0) == Gimp.PDBStatusType.SUCCESS, (name, result.index(0))
    decoded = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, path)
    check_image(decoded, tolerance=2)
    decoded.delete()
    print(f"FORMAT_TEST_PASS: {extension}")
if os.environ.get("GIMP_TEST_FORMATS") == "1":
    svg = out / "test.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
                   '<rect width="64" height="64" fill="black"/></svg>')
    decoded = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(svg)))
    check_image(decoded)
    decoded.delete()
    print("FORMAT_TEST_PASS: svg")
loaded.delete()
image.delete()
print("IMAGE_TEST_PASS: GEGL, XCF and codec round trips")
