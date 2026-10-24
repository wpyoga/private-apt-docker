#!/bin/bash
set -Eeuo pipefail

stage=$1
mkdir -p "$stage"
stage=$(cd -- "$stage" && pwd)
cd -- "$REPO_DIR"

for arch in $REPO_ARCHITECTURES; do
    index="$stage/main/binary-$arch"
    mkdir -p "$index"
    dpkg-scanpackages --multiversion --arch "$arch" pool > "$index/Packages"
    gzip -n -9 -c "$index/Packages" > "$index/Packages.gz"
done

apt-ftparchive \
    -o "APT::FTPArchive::Release::Origin=$REPO_ORIGIN" \
    -o "APT::FTPArchive::Release::Label=$REPO_LABEL" \
    -o "APT::FTPArchive::Release::Suite=$REPO_SUITE" \
    -o "APT::FTPArchive::Release::Codename=$CODENAME" \
    -o "APT::FTPArchive::Release::Architectures=$REPO_ARCHITECTURES" \
    -o 'APT::FTPArchive::Release::Components=main' \
    -o "APT::FTPArchive::Release::Description=$REPO_DESCRIPTION" \
    release "$stage" > "$stage.release"
mv -- "$stage.release" "$stage/Release"
printf '%s\n' 'Acquire-By-Hash: yes' >> "$stage/Release"

gpg --batch --yes --local-user "$GPG_KEY" \
    --armor --detach-sign --output "$stage/Release.gpg" "$stage/Release"
gpg --batch --yes --local-user "$GPG_KEY" \
    --clearsign --output "$stage/InRelease" "$stage/Release"

# All generation and signing must succeed before changing any live index.
install_metadata() {
    local source=$1 destination=$2 temporary
    mkdir -p -- "$(dirname -- "$destination")"
    temporary=$(mktemp "$(dirname -- "$destination")/.metadata-XXXXXX")
    install -m 644 -- "$source" "$temporary"
    mv -f -- "$temporary" "$destination"
}

distribution="dists/$CODENAME"
for arch in $REPO_ARCHITECTURES; do
    for name in Packages Packages.gz; do
        source="$stage/main/binary-$arch/$name"
        # Keep old hashes so clients holding an older Release can finish fetching.
        for algorithm in 256 512; do
            read -r digest _ < <("sha${algorithm}sum" "$source")
            install_metadata "$source" "$distribution/main/binary-$arch/by-hash/SHA$algorithm/$digest"
        done
        install_metadata "$source" "$distribution/main/binary-$arch/$name"
    done
done
for name in Release.gpg Release InRelease; do
    install_metadata "$stage/$name" "$distribution/$name"
done
echo "Published signed repository: $CODENAME"
