#!/bin/bash
set -euo pipefail

TR_MIGRATOR_PW="$(cat /run/secrets/tr_migrator_password)"
TR_APP_PW="$(cat /run/secrets/tr_app_password)"
TR_RO_PW="$(cat /run/secrets/tr_ro_password)"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
CREATE ROLE tr_migrator WITH LOGIN ENCRYPTED PASSWORD '$TR_MIGRATOR_PW';
CREATE ROLE tr_app WITH LOGIN ENCRYPTED PASSWORD '$TR_APP_PW';
CREATE ROLE tr_ro WITH LOGIN ENCRYPTED PASSWORD '$TR_RO_PW';

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
EOSQL
