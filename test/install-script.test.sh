#!/usr/bin/env bash
set -euo pipefail
export VIBEZ_INSTALLER_LIBRARY=1
# shellcheck source=../install.sh
source "$(dirname "$0")/../install.sh"

[[ "$(normalize_arch x86_64)" == "x64" ]]
[[ "$(normalize_arch aarch64)" == "arm64" ]]
grep -q 'VibeZ 2 public Linux packages are available for x86_64 only' "$(dirname "$0")/../install.sh"
[[ "$(detect_package_type ubuntu debian)" == "deb" ]]
[[ "$(detect_package_type fedora '')" == "rpm" ]]
[[ "$(detect_package_type manjaro arch)" == "pacman" ]]

assets=$'VibeZ_1.3.0_amd64.deb\nVibeZ_1.3.0_arm64.deb\nVibeZ-1.3.0.x86_64.rpm\nVibeZ-1.3.0.aarch64.rpm\nVibeZ-1.3.0.pacman\nVibeZ-1.3.0-arm64.pacman\nVibeZ-1.3.0.AppImage'
[[ "$(printf '%s\n' "$assets" | select_asset deb x64)" == "VibeZ_1.3.0_amd64.deb" ]]
[[ "$(printf '%s\n' "$assets" | select_asset deb arm64)" == "VibeZ_1.3.0_arm64.deb" ]]
[[ "$(printf '%s\n' "$assets" | select_asset rpm arm64)" == "VibeZ-1.3.0.aarch64.rpm" ]]
[[ "$(printf '%s\n' "$assets" | select_asset pacman x64)" == "VibeZ-1.3.0.pacman" ]]
[[ "$(printf '%s\n' "$assets" | select_asset pacman arm64)" == "VibeZ-1.3.0-arm64.pacman" ]]

echo "install.sh tests passed"
