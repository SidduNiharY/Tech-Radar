#!/bin/bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-data/backup}"

# shellcheck disable=SC2012
NEWEST_DUMP=$(ls -1t "$BACKUP_DIR/pg"/techradar-*.dump 2>/dev/null | head -n 1)

if [ -z "$NEWEST_DUMP" ] || [ ! -f "$NEWEST_DUMP" ]; then
    echo "No backup dump found in $BACKUP_DIR/pg" >&2
    exit 1
fi

trap 'docker compose exec -T postgres psql -U postgres -c "DROP DATABASE IF EXISTS techradar_restore_test;"' EXIT

docker compose exec -T postgres psql -U postgres -c "DROP DATABASE IF EXISTS techradar_restore_test;"
docker compose exec -T postgres psql -U postgres -c "CREATE DATABASE techradar_restore_test WITH TEMPLATE template0;"

if docker compose exec -T postgres test -f "$NEWEST_DUMP" 2>/dev/null; then
    docker compose exec -T postgres pg_restore -U postgres -d techradar_restore_test "$NEWEST_DUMP"
else
    docker compose exec -T postgres pg_restore -U postgres -d techradar_restore_test < "$NEWEST_DUMP"
fi

TABLES=$(docker compose exec -T postgres psql -U postgres -d techradar -t -A -c "SELECT tablename FROM pg_tables WHERE schemaname = 'techradar' AND tablename != 'bank_credentials' ORDER BY tablename;")

MATCH_COUNT=0
for table in $TABLES; do
    LIVE_COUNT=$(docker compose exec -T postgres psql -U postgres -d techradar -t -A -c "SELECT count(*) FROM techradar.\"$table\";" | tr -d '[:space:]')
    RESTORE_COUNT=$(docker compose exec -T postgres psql -U postgres -d techradar_restore_test -t -A -c "SELECT count(*) FROM techradar.\"$table\";" | tr -d '[:space:]')
    if [ "$LIVE_COUNT" != "$RESTORE_COUNT" ]; then
        echo "Row count mismatch for table $table: live=$LIVE_COUNT, restore=$RESTORE_COUNT" >&2
        exit 1
    fi
    MATCH_COUNT=$((MATCH_COUNT + 1))
done

if [ "$MATCH_COUNT" -eq 0 ]; then
    echo "No tables found in schema techradar" >&2
    exit 1
fi

echo "RESTORE OK ($MATCH_COUNT tables match)"
