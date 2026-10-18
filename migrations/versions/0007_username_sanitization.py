"""Replace user names with sanitized, case-insensitively unique usernames."""

import sqlalchemy as sa
from alembic import op

from gameapi.core.username import (
    generate_fallback_username,
    generate_unique_username,
    sanitize_username,
)

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=30), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "username_modified_by_system",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, name FROM users ORDER BY id")).mappings().all()
    existing_usernames: set[str] = set()
    update_user = sa.text(
        "UPDATE users "
        "SET username = :username, username_modified_by_system = :modified "
        "WHERE id = :user_id"
    )

    for row in rows:
        original_name = row["name"] or ""
        username = sanitize_username(original_name) or generate_fallback_username()
        username = generate_unique_username(username, existing_usernames)
        existing_usernames.add(username)
        connection.execute(
            update_user,
            {
                "username": username,
                "modified": original_name != username,
                "user_id": row["id"],
            },
        )

    op.alter_column("users", "username", nullable=False)
    op.drop_column("users", "name")
    op.create_index(
        "ix_users_username_lower",
        "users",
        [sa.text("LOWER(username)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_users_username_lower", table_name="users")
    op.add_column("users", sa.Column("name", sa.String(length=100), nullable=True))
    connection = op.get_bind()
    connection.execute(sa.text("UPDATE users SET name = username"))
    op.alter_column("users", "name", nullable=False)
    op.drop_column("users", "username_modified_by_system")
    op.drop_column("users", "username")
