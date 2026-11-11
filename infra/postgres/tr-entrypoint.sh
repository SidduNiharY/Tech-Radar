#!/bin/bash
# Docker Compose mounts file secrets with the host owner and mode (uid 1000, 0600),
# but the image's init scripts run as the postgres user and cannot read them.
# On the first start only (empty data directory), copy the three role passwords,
# while still root, into a postgres-only folder in the container's /tmp.
# 01-roles.sh reads them from there and deletes them right after.
set -euo pipefail

if [ "$(id -u)" = "0" ] && [ ! -s "${PGDATA:-/var/lib/postgresql/data}/PG_VERSION" ]; then
    install -d -m 0700 -o postgres -g postgres /tmp/tr-db-secrets
    for name in tr_migrator_password tr_app_password tr_ro_password; do
        if [ -f "/run/secrets/$name" ]; then
            install -m 0400 -o postgres -g postgres "/run/secrets/$name" "/tmp/tr-db-secrets/$name"
        fi
    done
fi

exec docker-entrypoint.sh "$@"
