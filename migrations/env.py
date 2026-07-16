"""
Alembic env.py for TW2 web tier.

Reads POSTGRES_DSN dynamically — preference order:
  1. TW2_ALEMBIC_DSN_OVERRIDE env var (used by the restore-drill).
  2. Process env (POSTGRES_DSN), already populated under systemd units.
  3. /etc/tradewave/secrets.env (parsed inline) when invoked ad-hoc.
  4. config.POSTGRES_DSN (which itself reads from os.environ).

Targets models.Base.metadata for autogenerate.
"""
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from alembic import context


def _maybe_load_secrets_env(path: str = '/etc/tradewave/secrets.env') -> None:
    """Lightweight KEY=VALUE loader for ad-hoc CLI runs (no shell sourcing)."""
    if not os.path.isfile(path):
        return
    try:
        with open(path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, _, v = line.partition('=')
                k = k.strip()
                v = v.strip()
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                # Don't overwrite values already set by the parent shell.
                os.environ.setdefault(k, v)
    except PermissionError:
        # Running as a user without read access to /etc/tradewave/secrets.env;
        # rely on whatever's already in the env.
        pass


_maybe_load_secrets_env()

_REPO_ROOT = Path(__file__).resolve().parents[1]
for candidate in (str(_REPO_ROOT), str(_REPO_ROOT / "web")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import config as tw2_config  # noqa: E402
from models import Base  # noqa: E402

alembic_config = context.config

_dsn = (
    os.environ.get('TW2_ALEMBIC_DSN_OVERRIDE')
    or tw2_config.POSTGRES_DSN
    or os.environ.get('POSTGRES_DSN')
)
if not _dsn:
    raise RuntimeError(
        "alembic env.py: no Postgres DSN found. Set POSTGRES_DSN in the "
        "environment, populate /etc/tradewave/secrets.env, or set "
        "TW2_ALEMBIC_DSN_OVERRIDE for one-off runs."
    )
alembic_config.set_main_option('sqlalchemy.url', _dsn)

if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = alembic_config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        alembic_config.get_section(alembic_config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
