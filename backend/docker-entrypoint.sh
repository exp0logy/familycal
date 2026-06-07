#!/bin/sh
# Backend container entrypoint.
#
# The /data directory is normally a host bind mount (see docker-compose.yml) so
# the SQLite db + photo cache survive rebuilds and are easy to back up. A bind
# mount keeps the HOST's ownership, which usually won't match the container's
# non-root `familycal` user — causing "unable to open database file". To keep
# both the bind-mount convenience AND a non-root app process, we fix ownership
# here while we still have root, then drop privileges via gosu.
set -e

if [ "$(id -u)" = "0" ]; then
    mkdir -p /data/photos
    # Best-effort: on some hosts (e.g. root-squashed NFS) chown may fail; the
    # app still works if the mount is already writable, so don't hard-fail.
    chown -R familycal:familycal /data 2>/dev/null || true
    exec gosu familycal "$@"
fi

# Already non-root (e.g. compose `user:` override) — just exec.
exec "$@"
