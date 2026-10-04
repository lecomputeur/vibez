#!/bin/sh
# Only system-wide desktop caches; never touch user profiles or pinned launchers.
set -e
case "${1:-}" in
    configure|remove|purge)
        if command -v gtk-update-icon-cache >/dev/null 2>&1; then
            gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
        fi
        if command -v update-desktop-database >/dev/null 2>&1; then
            update-desktop-database -q /usr/share/applications || true
        fi
        ;;
esac
exit 0
