#!/usr/bin/env python3
"""Plant honeytokens on the filesystem and PostgreSQL database for intrusion detection."""

from __future__ import annotations

import argparse
import os
import secrets
import string
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


def _exec_db(db_conn: Any, sql: str) -> None:
    """Execute SQL statement against database connection or mock."""
    if hasattr(db_conn, "cursor"):
        with db_conn.cursor() as cur:
            cur.execute(sql)
    elif hasattr(db_conn, "execute"):
        db_conn.execute(sql)
    if hasattr(db_conn, "commit"):
        db_conn.commit()


def plant_files(repo_root: Path) -> None:
    """Plant honeytoken files on filesystem with 0600 permissions."""
    secrets_dir = repo_root / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)

    # 1. secrets/aws_root_key.txt
    aws_key_path = secrets_dir / "aws_root_key.txt"
    suffix = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    fake_access_key = f"AKIA{suffix}"
    aws_key_path.write_text(f"{fake_access_key}\n")
    os.chmod(aws_key_path, 0o600)
    print(f"Planted {aws_key_path}")

    # 2. .env.production
    env_prod_path = repo_root / ".env.production"
    pw = secrets.token_urlsafe(16)
    env_content = f"DATABASE_URL=postgresql://admin_backup:{pw}@postgres:5432/techradar\n"
    env_prod_path.write_text(env_content)
    os.chmod(env_prod_path, 0o600)
    print(f"Planted {env_prod_path}")

    # 3. Excludes file listing honeytoken paths
    excludes_content = (
        "secrets/aws_root_key.txt\n.env.production\n/var/lib/techradar-honey/excludes.txt\n"
    )
    system_honey_dir = Path("/var/lib/techradar-honey")
    try:
        system_honey_dir.mkdir(parents=True, exist_ok=True)
        sys_excludes = system_honey_dir / "excludes.txt"
        sys_excludes.write_text(excludes_content)
        print(f"Planted {sys_excludes}")
    except PermissionError, OSError:
        local_honey_dir = repo_root / "var" / "lib" / "techradar-honey"
        local_honey_dir.mkdir(parents=True, exist_ok=True)
        local_excludes = local_honey_dir / "excludes.txt"
        local_excludes.write_text(excludes_content)
        print(f"Planted {local_excludes}")


def plant_db(db_conn: Any) -> None:
    """Plant honeytoken database role and table."""
    if db_conn is None:
        return

    # Random password for admin_backup role
    alphabet = string.ascii_letters + string.digits
    pw = "".join(secrets.choice(alphabet) for _ in range(24))

    _exec_db(db_conn, f"CREATE ROLE admin_backup WITH LOGIN PASSWORD '{pw}';")
    _exec_db(db_conn, "REVOKE ALL ON SCHEMA public FROM admin_backup;")
    _exec_db(db_conn, "REVOKE ALL ON DATABASE techradar FROM admin_backup;")

    _exec_db(db_conn, "CREATE SCHEMA IF NOT EXISTS techradar;")
    _exec_db(
        db_conn,
        """CREATE TABLE IF NOT EXISTS techradar.bank_credentials (
    id SERIAL PRIMARY KEY,
    bank_name VARCHAR(100) NOT NULL,
    account_number VARCHAR(50) NOT NULL,
    routing_number VARCHAR(50) NOT NULL,
    account_type VARCHAR(50) NOT NULL,
    balance_cents BIGINT NOT NULL
);""",
    )
    _exec_db(db_conn, "ALTER TABLE techradar.bank_credentials OWNER TO tr_migrator;")
    _exec_db(db_conn, "GRANT SELECT ON techradar.bank_credentials TO tr_auditor;")

    fake_rows = [
        ("Federal Reserve Bank", "1029384756", "021000021", "operating", 15420000),
        ("Standard Chartered Escrow", "9876543210", "011000015", "escrow", 489000000),
        ("Apex Clearing Reserve", "5647382910", "031000053", "settlement", 87654000),
        ("Zurich Vault Custody", "4321098765", "041000084", "collateral", 1200500000),
        ("Treasury Prime Sweeps", "7483920156", "051000092", "reserve", 95000000),
    ]
    for bank, acct, routing, acct_type, balance in fake_rows:
        sql = (
            f"INSERT INTO techradar.bank_credentials "  # noqa: S608
            f"(bank_name, account_number, routing_number, account_type, balance_cents) "
            f"VALUES ('{bank}', '{acct}', '{routing}', '{acct_type}', {balance});"
        )
        _exec_db(db_conn, sql)

    print("Created role admin_backup")
    print("Planted table techradar.bank_credentials (5 rows)")


def plant_vault(vault_path: Path, repo_root: Path | None = None) -> None:
    """Plant honeytoken in Obsidian vault: passwords.md with 0600, .stignore and TR_INDEX_SKIP."""
    vault_path.mkdir(parents=True, exist_ok=True)
    passwords_file = vault_path / "passwords.md"
    pw1 = secrets.token_urlsafe(16)
    pw2 = secrets.token_urlsafe(16)
    passwords_file.write_text(
        f"# Master Passwords & Credentials\n\n- admin_root: {pw1}\n- db_superuser: {pw2}\n"
    )
    os.chmod(passwords_file, 0o600)
    print(f"Planted {passwords_file}")

    stignore = vault_path / ".stignore"
    existing_ignore = stignore.read_text(encoding="utf-8") if stignore.exists() else ""
    if "passwords.md" not in existing_ignore:
        with stignore.open("a", encoding="utf-8") as f:
            f.write("\npasswords.md\n")
    print(f"Updated {stignore}")

    if repo_root:
        env_file = repo_root / ".env"
        if env_file.exists():
            env_content = env_file.read_text(encoding="utf-8")
            if "TR_INDEX_SKIP" not in env_content:
                with env_file.open("a", encoding="utf-8") as f:
                    f.write('\nTR_INDEX_SKIP="passwords.md"\n')


def plant(
    repo_root: Path,
    db_conn: Any = None,
    files: bool = True,
    db: bool = True,
    vault: Path | None = None,
) -> None:
    """Plant honeytoken files and database entities."""
    if files:
        plant_files(repo_root)
    if db:
        plant_db(db_conn)
    if vault:
        plant_vault(vault, repo_root)


def verify(repo_root: Path) -> bool:
    """Verify honeytoken files exist and have mode 0600."""
    ok = True
    aws_key = repo_root / "secrets" / "aws_root_key.txt"
    if not aws_key.exists():
        print(f"FAIL: {aws_key} does not exist")
        ok = False
    else:
        mode = os.stat(aws_key).st_mode & 0o777
        if mode != 0o600:
            print(f"FAIL: {aws_key} has mode {oct(mode)}, expected 0600")
            ok = False
        else:
            print(f"OK {aws_key} (mode 0600)")

    env_prod = repo_root / ".env.production"
    if not env_prod.exists():
        print(f"FAIL: {env_prod} does not exist")
        ok = False
    else:
        mode = os.stat(env_prod).st_mode & 0o777
        if mode != 0o600:
            print(f"FAIL: {env_prod} has mode {oct(mode)}, expected 0600")
            ok = False
        else:
            print(f"OK {env_prod} (mode 0600)")

    system_excludes = Path("/var/lib/techradar-honey/excludes.txt")
    local_excludes = repo_root / "var" / "lib" / "techradar-honey" / "excludes.txt"
    if not (system_excludes.exists() or local_excludes.exists()):
        print("FAIL: excludes.txt does not exist in system or local honey directory")
        ok = False
    else:
        print("OK excludes.txt exists")

    return ok


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Plant honeytokens for intrusion detection.")
    parser.add_argument("--files", action="store_true", help="Plant honeytoken files on host")
    parser.add_argument("--db", action="store_true", help="Plant honeytoken database objects")
    parser.add_argument("--vault", type=Path, help="Plant honeytoken note in vault")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify honeytoken files and permissions",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Path to repository root",
    )

    args = parser.parse_args()

    if not (args.files or args.db or args.vault or args.verify):
        parser.print_help()
        sys.exit(1)

    if args.verify and not verify(args.repo_root):
        sys.exit(1)

    if args.files or args.db or args.vault:
        db_conn = None
        if args.db:
            try:
                import psycopg

                from techradar.settings import settings

                db_conn = psycopg.connect(
                    f"postgresql://{settings.postgres_user}:"
                    f"{settings.postgres_password.get_secret_value()}@"
                    f"{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
                )
            except Exception as e:
                print(f"Database connection not available: {e}", file=sys.stderr)
                sys.exit(1)

        plant(args.repo_root, db_conn, files=args.files, db=args.db, vault=args.vault)


if __name__ == "__main__":
    main()
