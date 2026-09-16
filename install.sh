#!/usr/bin/env bash
set -euo pipefail

REPO="lecomputeur/vibez"
API_URL="https://api.github.com/repos/${REPO}/releases/latest"
RELEASES_URL="https://github.com/${REPO}/releases/latest"

info() { printf '==> %s\n' "$*"; }
warn() { printf 'Warning: %s\n' "$*" >&2; }
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

normalize_arch() {
  case "${1:-}" in
    x86_64|amd64) printf 'x64\n' ;;
    aarch64|arm64) printf 'arm64\n' ;;
    *) return 1 ;;
  esac
}

asset_names_from_json() {
  sed -n 's/.*"name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p'
}

select_asset() {
  local package_type="$1" arch="$2" name
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    case "${package_type}:${arch}" in
      deb:x64) [[ "$name" == *.deb && ( "$name" == *amd64* || "$name" == *x86_64* || "$name" == *x64* ) ]] && { printf '%s\n' "$name"; return 0; } ;;
      deb:arm64) [[ "$name" == *.deb && ( "$name" == *arm64* || "$name" == *aarch64* ) ]] && { printf '%s\n' "$name"; return 0; } ;;
      rpm:x64) [[ "$name" == *.rpm && ( "$name" == *x86_64* || "$name" == *x64* ) ]] && { printf '%s\n' "$name"; return 0; } ;;
      rpm:arm64) [[ "$name" == *.rpm && ( "$name" == *aarch64* || "$name" == *arm64* ) ]] && { printf '%s\n' "$name"; return 0; } ;;
      pacman:x64)
        [[ ( "$name" == *.pacman || "$name" == *.pkg.tar.zst ) && "$name" != *arm64* && "$name" != *aarch64* ]] && { printf '%s\n' "$name"; return 0; }
        ;;
      pacman:arm64) [[ ( "$name" == *.pacman || "$name" == *.pkg.tar.zst ) && ( "$name" == *arm64* || "$name" == *aarch64* ) ]] && { printf '%s\n' "$name"; return 0; } ;;
    esac
  done
  return 1
}

detect_package_type() {
  local id="$1" like="$2"
  case " ${id} ${like} " in
    *" debian "*|*" ubuntu "*) printf 'deb\n' ;;
    *" fedora "*|*" rhel "*|*" centos "*|*" suse "*) printf 'rpm\n' ;;
    *" arch "*) printf 'pacman\n' ;;
    *) return 1 ;;
  esac
}

verify_checksum() {
  local dir="$1" file="$2" sums="$3"
  command -v sha256sum >/dev/null 2>&1 || { warn "sha256sum is unavailable; skipping checksum verification."; return 0; }
  [[ -s "$sums" ]] || { warn "This release has no SHA256SUMS file; skipping checksum verification."; return 0; }
  local expected
  expected="$(awk -v target="$file" '$2 == target || $2 == "*" target {print $1; exit}' "$sums")"
  [[ -n "$expected" ]] || fail "No checksum was published for ${file}."
  local actual
  actual="$(sha256sum "$dir/$file" | awk '{print $1}')"
  [[ "$actual" == "$expected" ]] || fail "Checksum verification failed for ${file}."
  info "SHA-256 checksum verified."
}

uninstall_vibez() {
  [[ -r /etc/os-release ]] || fail "Could not detect your Linux distribution."
  # shellcheck disable=SC1091
  . /etc/os-release
  local type
  type="$(detect_package_type "${ID:-unknown}" "${ID_LIKE:-}")" || fail "Automatic uninstall is not supported on ${PRETTY_NAME:-this distribution}."
  local sudo_cmd=()
  if [[ "${EUID}" -ne 0 ]]; then command -v sudo >/dev/null 2>&1 || fail "sudo is required."; sudo_cmd=(sudo); fi
  case "$type" in
    deb) "${sudo_cmd[@]}" apt remove -y vibez ;;
    rpm)
      if command -v dnf >/dev/null 2>&1; then "${sudo_cmd[@]}" dnf remove -y vibez
      elif command -v yum >/dev/null 2>&1; then "${sudo_cmd[@]}" yum remove -y vibez
      else fail "No supported RPM package manager found."; fi
      ;;
    pacman) "${sudo_cmd[@]}" pacman -Rns --noconfirm vibez ;;
  esac
  info "VibeZ uninstalled."
}

main() {
  if [[ "${1:-}" == "--uninstall" ]]; then uninstall_vibez; return; fi
  command -v curl >/dev/null 2>&1 || fail "curl is required."
  command -v uname >/dev/null 2>&1 || fail "uname is required."

  local arch
  arch="$(normalize_arch "$(uname -m)")" || fail "Unsupported Linux architecture: $(uname -m)."
  [[ "$arch" == "x64" ]] || fail "VibeZ 2 public Linux packages are available for x86_64 only. Build from source on ${arch}."
  [[ -r /etc/os-release ]] || fail "Could not detect your Linux distribution (/etc/os-release is missing)."
  # shellcheck disable=SC1091
  . /etc/os-release
  local package_type
  package_type="$(detect_package_type "${ID:-unknown}" "${ID_LIKE:-}")" || fail "Unsupported distribution: ${PRETTY_NAME:-${ID:-unknown}}. Use the AppImage or Flatpak from ${RELEASES_URL}."

  info "Checking the latest VibeZ release..."
  local release_json tag version asset_names asset
  release_json="$(curl -fsSL --retry 3 "$API_URL")" || fail "Could not contact GitHub Releases."
  tag="$(printf '%s\n' "$release_json" | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
  [[ -n "$tag" ]] || fail "Could not determine the latest VibeZ version."
  version="${tag#v}"
  asset_names="$(printf '%s\n' "$release_json" | asset_names_from_json)"
  asset="$(printf '%s\n' "$asset_names" | select_asset "$package_type" "$arch")" || fail "No ${package_type} package for ${arch} was found in VibeZ ${version}."

  local tmp_dir base_url sums_url
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "$tmp_dir"' EXIT
  base_url="https://github.com/${REPO}/releases/download/${tag}"

  info "Detected ${PRETTY_NAME:-Linux} (${arch})."
  info "Downloading VibeZ ${version}: ${asset}"
  curl -fL --retry 3 -o "$tmp_dir/$asset" "$base_url/$asset"

  sums_url="$base_url/SHA256SUMS"
  if curl -fsSL --retry 2 -o "$tmp_dir/SHA256SUMS" "$sums_url"; then
    verify_checksum "$tmp_dir" "$asset" "$tmp_dir/SHA256SUMS"
  else
    rm -f "$tmp_dir/SHA256SUMS"
    warn "Could not download SHA256SUMS; continuing without checksum verification for this older release."
  fi

  local sudo_cmd=()
  if [[ "${EUID}" -ne 0 ]]; then command -v sudo >/dev/null 2>&1 || fail "sudo is required to install VibeZ system-wide."; sudo_cmd=(sudo); fi

  info "Installing ${asset}..."
  case "$package_type" in
    deb) "${sudo_cmd[@]}" apt install -y "$tmp_dir/$asset" ;;
    rpm)
      if command -v dnf >/dev/null 2>&1; then "${sudo_cmd[@]}" dnf install -y "$tmp_dir/$asset"
      elif command -v yum >/dev/null 2>&1; then "${sudo_cmd[@]}" yum install -y "$tmp_dir/$asset"
      else fail "No supported RPM package manager found (dnf or yum)."; fi
      ;;
    pacman) "${sudo_cmd[@]}" pacman -U --noconfirm "$tmp_dir/$asset" ;;
  esac
  info "VibeZ ${version} installed successfully."
}

if [[ "${VIBEZ_INSTALLER_LIBRARY:-0}" != "1" ]]; then main "$@"; fi
