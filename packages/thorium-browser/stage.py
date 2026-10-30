"""Validate the known upstream layout and stage a coinstallable browser."""

import gzip
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile

PREFIX = "opt/chromium.org/thorium"
OUTSIDE_FILES = {
    "usr/bin/pak", "usr/bin/thorium-browser", "usr/bin/thorium-shell",
    "usr/share/appdata/thorium-browser.appdata.xml",
    "usr/share/applications/org.chromium.Thorium.desktop",
    "usr/share/applications/thorium-browser.desktop",
    "usr/share/applications/thorium-shell.desktop",
    "usr/share/doc/thorium-browser/changelog.gz",
    "usr/share/gnome-control-center/default-apps/thorium-browser.xml",
    "usr/share/man/man1/thorium-browser.1.gz",
}


def validate(archive):
    source = os.environ["UPSTREAM_REPOSITORY"]
    arch = os.environ["ARCHITECTURE"]
    machine = {"amd64": 62, "arm64": 183}[arch]
    allowed = set(OUTSIDE_FILES)
    if source == "Alex313031/thorium":
        allowed.update({"etc/cron.daily/thorium-browser", "usr/share/menu/thorium-browser.menu"})
    links = {"usr/bin/thorium-browser": f"/{PREFIX}/thorium-browser"}
    if source == "Alex313031/thorium":
        links["etc/cron.daily/thorium-browser"] = f"/{PREFIX}/cron/thorium-browser"
    else:
        links["usr/bin/pak"] = f"/{PREFIX}/pak"
    entries = {}
    elf_files = set()
    # Validation decodes the payload too; extraction's thread limit is not enough.
    process = subprocess.Popen(
        ["dpkg-deb", "--threads-max=1", "--fsys-tarfile", archive],
        stdout=subprocess.PIPE,
    )
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as payload:
            for entry in payload:
                name = entry.name.removeprefix("./").rstrip("/")
                if name in ("", "."):
                    continue
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or name in entries:
                    raise ValueError(f"Unsafe or duplicate payload path: {entry.name}")
                entries[name] = entry
                if not (entry.isfile() or entry.isdir() or entry.issym()):
                    raise ValueError(f"Unexpected payload type: {name}")
                if entry.issym() and links.get(name) != entry.linkname:
                    raise ValueError(f"Unexpected symlink: {name} -> {entry.linkname}")
                if not entry.isdir() and not name.startswith(PREFIX + "/") and name not in allowed:
                    raise ValueError(f"Unexpected upstream file: {name}")
                if entry.isfile():
                    header = payload.extractfile(entry).read(64)
                    if header.startswith(b"\x7fELF"):
                        elf_files.add(name)
                        actual_machine = int.from_bytes(header[18:20], "little")
                        foreign_cdm = f"{PREFIX}/ClearKeyCdm/_platform_specific/linux_arm64/libclearkeycdm.so"
                        known_foreign = (source == "Alex313031/thorium" and arch == "amd64"
                                         and name == foreign_cdm and actual_machine == 183)
                        if (len(header) < 20 or header[4] != 2 or header[5] != 1
                                or (actual_machine != machine and not known_foreign)):
                            raise ValueError(f"{name}: expected ELF machine {machine}, got {actual_machine}")
        status = process.wait()
        if status != 0:
            raise ValueError(f"Cannot read Debian payload {archive}: dpkg-deb exit status {status}")
    except tarfile.TarError as error:
        # Closing the pipe also releases a decoder blocked on an invalid tar stream.
        process.stdout.close()
        try:
            status = process.wait(timeout=5)
            detail = f"dpkg-deb exit status {status}"
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait()
            detail = "dpkg-deb did not exit after its payload pipe was closed"
        raise ValueError(f"Cannot parse Debian payload {archive}: {error}; {detail}") from error
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.terminate()
            process.wait()

    required = {
        f"{PREFIX}/{name}" for name in (
            "thorium", "thorium-browser", "thorium_shell", "chrome-sandbox",
            "chrome_crashpad_handler", "chromedriver", "resources.pak", "icudtl.dat",
            "locales/en-US.pak", "product_logo_128.png", "thorium_shell.png",
        )
    }
    required.update(OUTSIDE_FILES)
    if source == "gz83/thorium":
        required.add(f"{PREFIX}/apparmor.d/thorium-browser")
    for name in sorted(required):
        if name not in entries:
            raise ValueError(f"Missing upstream path: {name}")
        if name not in links and not entries[name].isfile():
            raise ValueError(f"Expected regular upstream file: {name}")
    for name, target in links.items():
        if name not in entries or not entries[name].issym() or entries[name].linkname != target:
            raise ValueError(f"Expected upstream symlink: {name} -> {target}")
    for name in ("thorium", "thorium_shell", "chrome-sandbox", "chrome_crashpad_handler", "chromedriver"):
        if f"{PREFIX}/{name}" not in elf_files:
            raise ValueError(f"Expected ELF executable: {PREFIX}/{name}")
    sandbox = entries[f"{PREFIX}/chrome-sandbox"]
    if sandbox.mode != 0o4755 or sandbox.uid != 0 or sandbox.gid != 0:
        raise ValueError("chrome-sandbox must be root:root with mode 4755")


def stage():
    extracted = Path(os.environ["EXTRACT_DIR"])
    destination = Path(os.environ["PACKAGE_DIR"])
    package = os.environ["PACKAGE_NAME"]
    source = os.environ["UPSTREAM_REPOSITORY"]
    payload = destination / "opt" / package
    payload.parent.mkdir(parents=True)
    shutil.move(str(extracted / PREFIX), payload)
    shutil.rmtree(payload / "cron", ignore_errors=True)
    (payload / "thorium-browser").unlink()

    def copy_file(relative, output):
        target = destination / output
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(extracted / relative, target)

    def write_file(relative, contents, mode=0o644):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents)
        target.chmod(mode)

    # Retain upstream descriptions/dependencies, dropping obsolete replacement rules.
    original = (extracted / "DEBIAN/control").read_text()
    kept = []
    skip = False
    for line in original.splitlines():
        if line and not line[0].isspace():
            skip = line.split(":", 1)[0].lower() in {
                "conflicts", "replaces", "breaks", "conffiles", "installed-size",
            }
        if not skip:
            kept.append(line)
    write_file("DEBIAN/control", "\n".join(kept) + "\n")
    write_file(f"usr/bin/{package}-shell",
               f'#!/bin/bash\nset -Eeuo pipefail\nexec /opt/{package}/thorium_shell "$@"\n', 0o755)
    if source == "Alex313031/thorium":
        shutil.move(str(extracted / "usr/bin/pak"), payload / "pak")
    for tool, binary in (("pak", "pak"), ("chromedriver", "chromedriver")):
        write_file(f"usr/bin/{package}-{tool}",
                   f'#!/bin/bash\nset -Eeuo pipefail\nexec /opt/{package}/{binary} "$@"\n', 0o755)

    def rewrite_desktop(relative):
        text = (extracted / relative).read_text()
        commands = {"thorium-browser": package, "thorium-shell": package + "-shell"}
        text = re.sub(r"/usr/bin/(thorium-browser|thorium-shell)\b",
                      lambda match: "/usr/bin/" + commands[match[1]], text)
        text = re.sub(r"^Icon=.*$", "Icon=" + (
            package + "-shell" if relative.endswith("thorium-shell.desktop") else package
        ), text, flags=re.M)
        if relative.endswith("thorium-browser.desktop"):
            text = re.sub(r"^StartupWMClass=.*$", "StartupWMClass=" + package, text, flags=re.M)
        main, separator, actions = text.partition("[Desktop Action")
        main = re.sub(r"^(Name(?:\[[^\]]+\])?=.*)$",
                      lambda match: match[0] + f" ({package})", main, flags=re.M)
        result = main + separator + actions
        if "/opt/chromium.org/thorium" in result:
            raise ValueError(f"Unexpected upstream desktop reference: {relative}")
        return result

    desktop = rewrite_desktop("usr/share/applications/thorium-browser.desktop")
    write_file(f"usr/share/applications/{package}.desktop", desktop)
    shell_desktop = rewrite_desktop("usr/share/applications/thorium-shell.desktop")
    write_file(f"usr/share/applications/{package}-shell.desktop", shell_desktop)
    appdata = (extracted / "usr/share/appdata/thorium-browser.appdata.xml").read_text()
    if "<id>thorium-browser.desktop</id>" not in appdata:
        raise ValueError("Unexpected upstream AppStream application ID")
    appdata = appdata.replace("thorium-browser", package).replace("org.chromium.Thorium", package)
    appdata = appdata.replace("<name>Thorium Browser</name>", f"<name>Thorium Browser ({package})</name>")
    write_file(f"usr/share/metainfo/{package}.appdata.xml", appdata)
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon = payload / f"product_logo_{size}.png"
        if not icon.is_file():
            raise ValueError(f"Missing upstream icon: {icon}")
        target = destination / f"usr/share/icons/hicolor/{size}x{size}/apps/{package}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(icon, target)
    target = destination / f"usr/share/icons/hicolor/128x128/apps/{package}-shell.png"
    shutil.copy2(payload / "thorium_shell.png", target)
    copy_file("usr/share/doc/thorium-browser/changelog.gz", f"usr/share/doc/{package}/changelog.gz")
    manpage = gzip.decompress((extracted / "usr/share/man/man1/thorium-browser.1.gz").read_bytes())
    manpage = manpage.replace(b"thorium-browser", package.encode())
    manpage = manpage.replace(b"/opt/chromium.org/thorium", f"/opt/{package}".encode())
    manpath = destination / f"usr/share/man/man1/{package}.1.gz"
    manpath.parent.mkdir(parents=True, exist_ok=True)
    manpath.write_bytes(gzip.compress(manpage, mtime=0))
    if source == "gz83/thorium":
        profile = payload / "apparmor.d/thorium-browser"
        text = profile.read_text()
        if "profile thorium-browser /opt/chromium.org/thorium/thorium " not in text:
            raise ValueError("Unexpected upstream AppArmor attachment")
        text = text.replace("thorium-browser", package)
        text = text.replace("/opt/chromium.org/thorium/thorium", f"/opt/{package}/thorium")
        write_file(f"etc/apparmor.d/{package}", text)
        write_file("DEBIAN/conffiles", f"/etc/apparmor.d/{package}\n")
        shutil.rmtree(payload / "apparmor.d")
    (destination / "usr/bin").mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    try:
        if sys.argv[1] == "validate":
            validate(sys.argv[2])
        elif sys.argv[1] == "stage":
            stage()
        else:
            raise ValueError(f"Unknown stage operation: {sys.argv[1]}")
    except (ValueError, OSError, tarfile.TarError) as error:
        raise SystemExit(f"{os.environ['PACKAGE_NAME']}: {error}") from error
