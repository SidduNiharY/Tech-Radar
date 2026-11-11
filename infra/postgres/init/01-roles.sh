#!/bin/bash
set -euo pipefail

# tr-entrypoint.sh copies these from /run/secrets on first start (postgres cannot
# read the mounted files); delete the copies as soon as they are read.
SECRETS=/tmp/tr-db-secrets
TR_MIGRATOR_PW="$(cat "$SECRETS/tr_migrator_password")"
TR_APP_PW="$(cat "$SECRETS/tr_app_password")"
TR_RO_PW="$(cat "$SECRETS/tr_ro_password")"
rm -f "$SECRETS"/tr_*_password

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
CREATE ROLE tr_migrator WITH LOGIN ENCRYPTED PASSWORD '$TR_MIGRATOR_PW';
CREATE ROLE tr_app WITH LOGIN ENCRYPTED PASSWORD '$TR_APP_PW';
CREATE ROLE tr_ro WITH LOGIN ENCRYPTED PASSWORD '$TR_RO_PW';
CREATE ROLE tr_auditor WITH NOLOGIN;

REVOKE ALL ON DATABASE techradar FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

GRANT CONNECT ON DATABASE techradar TO tr_migrator, tr_app, tr_ro;

CREATE SCHEMA IF NOT EXISTS techradar AUTHORIZATION tr_migrator;
GRANT USAGE ON SCHEMA techradar TO tr_app, tr_ro;

ALTER ROLE tr_migrator SET search_path = techradar;
ALTER ROLE tr_app SET search_path = techradar;
ALTER ROLE tr_ro SET search_path = techradar;

ALTER DEFAULT PRIVILEGES FOR ROLE tr_migrator IN SCHEMA techradar GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO tr_app;
ALTER DEFAULT PRIVILEGES FOR ROLE tr_migrator IN SCHEMA techradar GRANT USAGE, SELECT ON SEQUENCES TO tr_app;
ALTER DEFAULT PRIVILEGES FOR ROLE tr_migrator IN SCHEMA techradar GRANT SELECT ON TABLES TO tr_ro;

CREATE EXTENSION IF NOT EXISTS vector SCHEMA techradar;
CREATE EXTENSION IF NOT EXISTS pgaudit;
EOSQL
