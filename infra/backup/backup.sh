#!/bin/bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-data/backup}"
VAULT_DIR="${VAULT_DIR:-data/vault}"
LIBRARY_DIR="${LIBRARY_DIR:-data/library}"
SECRETS_DIR="${SECRETS_DIR:-secrets}"
RESTIC_REPOSITORY="${RESTIC_REPOSITORY:-/mnt/backup/restic}"
RESTIC_PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-$SECRETS_DIR/restic_password}"
export RESTIC_PASSWORD_FILE

# DUMP step: Nightly postgres dump
mkdir -p "$BACKUP_DIR/pg"
TS=$(date -u +"%Y%m%d_%H%M%SZ")
DUMP_FILE="$BACKUP_DIR/pg/techradar-${TS}.dump"

docker compose exec -T postgres pg_dump -Fc -U tr_migrator --exclude-table-data=techradar.bank_credentials -d techradar > "$DUMP_FILE"

# Rotate local dumps: keep newest 14
# shellcheck disable=SC2012
ls -1t "$BACKUP_DIR/pg"/techradar-*.dump 2>/dev/null | tail -n +15 | xargs -r rm -f

# RESTIC snapshot step: Weekly snapshot on Sunday if repository mounted and password file exists
if [ "$(date +%u)" -eq 7 ] && [ -d "$RESTIC_REPOSITORY" ] && [ -f "$RESTIC_PASSWORD_FILE" ]; then
    mkdir -p "$VAULT_DIR" "$LIBRARY_DIR" 2>/dev/null || true

    # Honeytoken files are skipped through restic-excludes.txt. The backup never
    # reads the honeytoken directory: that would set off the tr_honey audit watch.
    # The library (originals, chapter text, summaries) is backed up; its media/ folder
    # (extracted audio, re-creatable from the originals) is not (SEC-43).
    restic -r "$RESTIC_REPOSITORY" backup "$BACKUP_DIR/pg" "$VAULT_DIR" "$SECRETS_DIR" "$LIBRARY_DIR" --exclude-file infra/backup/restic-excludes.txt --exclude "$LIBRARY_DIR/media"
    restic -r "$RESTIC_REPOSITORY" forget --keep-weekly 8 --keep-monthly 12 --prune
fi
