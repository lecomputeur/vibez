#!/bin/sh
# Close only the installed VibeZ executable before replacing its files.
# Never match a process name, touch profiles, or stop an AppImage/preview copy.
set -eu
case "${1:-}" in install|upgrade|1|2) ;; *) exit 0 ;; esac
installed='/usr/bin/vibez3'
for process in /proc/[0-9]*; do
    executable=$(readlink "$process/exe" 2>/dev/null) || continue
    case "$executable" in "$installed"|"$installed (deleted)") ;; *) continue ;; esac
    pid=${process##*/}
    kill -TERM "$pid" 2>/dev/null || continue
    remaining=5
    while [ "$remaining" -gt 0 ]; do
        current=$(readlink "$process/exe" 2>/dev/null) || break
        case "$current" in "$installed"|"$installed (deleted)") ;; *) break ;; esac
        sleep 1
        remaining=$((remaining - 1))
    done
    current=$(readlink "$process/exe" 2>/dev/null) || continue
    case "$current" in
        "$installed"|"$installed (deleted)")
            echo 'VibeZ could not be closed; its application files have not been replaced.' >&2
            exit 1
            ;;
    esac
done
exit 0
