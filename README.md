# Private Codex APT repository

This is an unofficial repackaging of official OpenAI Codex release executables.
The publisher container does not expose HTTP; serve `repo/` with an existing Caddy instance.
Make sure gpg is installed before proceeding.

## Setup

0. Create the codexrepo user as a low-capability user: sudo useradd --system --no-create-home --shell /usr/sbin/nologin codexrepo
   Store the UID and GID in .env as CODEX_UID and CODEX_GID

1. ```sh
   sudo -u codexrepo mkdir -p repo gnupg
   sudo -u codexrepo chmod 700 gnupg
   ```
2. Generate a dedicated signing key using a temporary GNUPGHOME, or import an existing dedicated key into `./gnupg`:
   ```sh
   sudo -u codexrepo gpg --homedir /srv/apt/codex/gnupg --quick-generate-key "Private Codex Repository <repo@localhost>" ed25519 sign 20y
   sudo -u codexrepo gpg --homedir /srv/apt/codex/gnupg --list-secret-keys --with-colons
   ```
   Record the full fingerprint from the `fpr` line.
3. `printf 'GPG_KEY=%s\n' 'YOUR_FULL_FINGERPRINT' > .env && chmod 600 .env`
4. `docker compose up -d --build`
5. `docker compose logs -f`

Export the public key:
```sh
sudo -u codexrepo gpg --armor --export YOUR_FULL_FINGERPRINT > codex-repo.asc
```
Transfer the public key to the Debian client securely and verify its fingerprint out of band.

## Caddy

Replace the example Tailnet IP with `tailscale ip -4` on the VPS:

```caddyfile
http://100.101.102.103:8080 {
    bind 100.101.102.103
    root * /absolute/path/to/codex-apt-docker/repo
    file_server
}
```

Caddy needs filesystem read access to `repo/`. The updater publishes with umask 022. Ensure parent directories permit traversal and Caddy has read access to the repository files. Never grant Caddy access to `gnupg/`.

## Debian client

```sh
sudo install -m 0644 codex-repo.asc /etc/apt/keyrings/codex-repo.asc
printf '%s\n' 'deb [signed-by=/etc/apt/keyrings/codex-repo.asc] http://100.101.102.103:8080/ trixie main' | sudo tee /etc/apt/sources.list.d/codex.list
sudo apt update
sudo apt install codex-cli
```

## Caveats

- GitHub TLS transport is used, but upstream signatures/checksums are not independently validated.
- Container uses a writable signing key: protect the VPS and Docker daemon accordingly.
- The latest GitHub release endpoint and asset names are assumptions to validate against the current upstream release.
- This implementation retains all old versions. Add a retention policy if disk usage grows.
- `reprepro` writes repository data using its own file permissions; ensure Caddy can read only the published tree.
- The container checks every six hours, including while no clients are connected.
- Initial build is not end-to-end tested against GitHub in this offline build environment.
