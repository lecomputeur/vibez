#!/usr/bin/env bash
set -euo pipefail
mkdir -p arch-stage release-assets
cp release-assets/*Linux-x64.deb arch-stage/app.deb
# A real Pacman package, not a renamed Debian archive.
docker run --rm -v "$PWD/arch-stage:/work" archlinux:base-devel bash -eu -c '
 pacman -Syu --noconfirm --needed libarchive zstd
 useradd -m builder; chown -R builder:builder /work
 cd /work
 bsdtar -xf app.deb
 mkdir payload; bsdtar -xf data.tar.* -C payload
 cat > PKGBUILD <<"PKG"
pkgname=vibez3
pkgver=3.0.3
pkgrel=1
pkgdesc="VibeZ 3 — Rust/Tauri client for Mistral Vibe"
arch=(x86_64)
url="https://github.com/lecomputeur/vibez"
license=(MIT)
depends=(gtk3 webkit2gtk-4.1 libayatana-appindicator xdg-desktop-portal)
options=(!strip !debug)
package() { cp -a "$startdir/payload/usr" "$pkgdir/"; }
PKG
 chown -R builder:builder /work
 su builder -c "cd /work && makepkg --nodeps --noconfirm"
 pacman -Qip /work/*.pkg.tar.zst
 pacman -U --noconfirm /work/*.pkg.tar.zst
 vibez3 --version | grep 3.0.3
 if ldd /usr/bin/vibez3 | grep "not found"; then exit 1; fi
'
cp arch-stage/*.pkg.tar.zst release-assets/VibeZ-3.0.3-Linux-x64.pkg.tar.zst
