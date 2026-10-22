#!/bin/sh

set -eu

REPO_USER=codexrepo
REPO_GROUP=codexrepo
BASEDIR=/srv/apt/codex

GPG_KEY_NAME="Private Codex Repository <repo@localhost>"
GPG_KEY_TYPE=ed25519
GPG_KEY_VALIDITY=20y

sudo useradd --system --no-create-home --shell /usr/sbin/nologin $REPO_USER
echo "REPO_UID=`id -u $REPO_USER`" > .env
echo "REPO_GID=`id -g $REPO_GROUP`" >> .env

sudo -u $REPO_USER mkdir -p $BASEDIR/{repo,gnupg}
sudo -u $REPO_USER chmod 700 $BASEDIR/gnupg

sudo -u $REPO_USER gpg --homedir $BASEDIR/gnupg --pinentry-mode loopback --passphrase "" --quick-generate-key "$GPG_KEY_NAME" $GPG_KEY_TYPE sign $GPG_KEY_VALIDITY
sudo -u $REPO_USER gpg --homedir $BASEDIR/gnupg --list-secret-keys --with-colons

FPR=`sudo -u $REPO_USER gpg --homedir $BASEDIR/gnupg --list-secret-keys --with-colons | grep ^fpr: | sed -e 's,^fpr:,,' -e 's,:,,g'`
echo "GPG_KEY=$FPR" >> .env && chmod 600 .env

sudo -u $REPO_USER gpg --homedir $BASEDIR/gnupg --armor --export $FPR > repo-pubkey.asc

docker compose up --build

