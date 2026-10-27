"""GIMP-specific Debian manual fixtures."""

import hashlib
import subprocess


def create_help_fixtures(base, adapter, *, version="3.2.0-3", architecture="all",
                         dependency=None, installed_size="999999"):
    names = ("gimp-help-common", "gimp-help-en", "gimp-help-de")
    manifest = []
    for name in names:
        root = base / "upstream-help" / name
        (root / "DEBIAN").mkdir(parents=True, exist_ok=True)
        if name != "gimp-help-common":
            payload = root / "usr/share/gimp/3.0/help" / name.removeprefix("gimp-help-")
            payload.mkdir(parents=True, exist_ok=True)
            (payload / "index.html").write_text("<html>Manual fixture</html>\n")
        copyright_path = root / "usr/share/doc" / name / "copyright"
        copyright_path.parent.mkdir(parents=True, exist_ok=True)
        copyright_path.write_text("Upstream documentation license fixture\n")
        html_link = copyright_path.parent / "html"
        if not html_link.is_symlink():
            html_link.symlink_to("../../gimp/3.0/help")
        depends = "" if name == "gimp-help-common" else (
            dependency or f"gimp-help-common (= {version})")
        control = (f"Package: {name}\nVersion: {version}\nArchitecture: {architecture}\n"
                   "Maintainer: Debian Fixture <test@example.invalid>\n"
                   "Description: Precompiled manual fixture\n A continuation line.\n")
        if installed_size:
            control += f"Installed-Size: {installed_size}\n"
        if depends:
            control += f"Depends: {depends}\n"
        (root / "DEBIAN/control").write_text(control)
        if name == "gimp-help-de":
            script = root / "DEBIAN/postinst"
            script.write_text("#!/bin/sh\n# Verified upstream migration fixture\nexit 0\n")
            script.chmod(0o755)
        archive = base / "downloads" / f"{name}_{version}_{architecture}.deb"
        existing = subprocess.check_output(["dpkg-deb", "--field", archive], text=True) if archive.exists() else ""
        if existing.strip() != control.strip():
            subprocess.run(["dpkg-deb", "--build", root, archive], check=True, capture_output=True)
        manifest.append("|".join((name, version, hashlib.sha256(archive.read_bytes()).hexdigest(),
                                   f"pool/main/g/gimp-help/{archive.name}")))
    (adapter / "help-assets").write_text("\n".join(manifest) + "\n")
    config = adapter / "config"
    original = config.read_text().split('BINARY_PACKAGES="')[1].split('"')[0].split()
    packages = [name for name in original if not name.startswith("gimp-help-")]
    config.write_text('RELEASE_STREAM=gimp-3.2\nBINARY_PACKAGES="' +
                      " ".join(packages + list(names)) + '"\n')
