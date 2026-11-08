# Secrets Directory Specification

In production and development, the `secrets/` directory holds one file per secret, mode `0600`, owned by `uid:gid 1000:1000`.

Mounted as Docker secrets into container runtime at `/run/secrets/`.

Files required in Phase 1:
- `pg_superuser_password`: PostgreSQL root superuser password
- `tr_migrator_password`: Migration runner database user password
- `tr_app_password`: Application worker database user password
- `tr_ro_password`: Read-only reporting database user password
- `telegram_bot_token`: Telegram Bot API token
- `alerter_bot_token`: Standalone security alerter Telegram bot token
- `restic_password`: Encrypted backup repository password
