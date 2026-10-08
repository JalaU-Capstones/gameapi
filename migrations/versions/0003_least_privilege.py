"""Grant DML to gameapi_app and revoke it from alembic_version.

This migration is intentionally idempotent. It assumes the role `gameapi_app`
already exists; role creation is done by the Postgres init script (local) or by
the operator (Render), as documented in .docs/deployment/README.md.
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

APP_ROLE = "gameapi_app"
TABLES = ("users", "gameplays", "refresh_tokens", "logs")


def upgrade() -> None:
    table_grants = " ".join(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {APP_ROLE};" for table in TABLES
    )
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            GRANT USAGE ON SCHEMA public TO {APP_ROLE};
            REVOKE CREATE ON SCHEMA public FROM {APP_ROLE};
            {table_grants}
            REVOKE ALL ON TABLE alembic_version FROM {APP_ROLE};
            ALTER DEFAULT PRIVILEGES FOR ROLE gameapi IN SCHEMA public
              GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE};
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    table_revokes = " ".join(f"REVOKE ALL ON TABLE {table} FROM {APP_ROLE};" for table in TABLES)
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            {table_revokes}
            REVOKE ALL ON TABLE alembic_version FROM {APP_ROLE};
            REVOKE USAGE ON SCHEMA public FROM {APP_ROLE};
            ALTER DEFAULT PRIVILEGES FOR ROLE gameapi IN SCHEMA public
              REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE};
          END IF;
        END $$;
        """
    )
