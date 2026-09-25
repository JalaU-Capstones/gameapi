"""Create the initial PostgreSQL schema."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "register_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "gameplays",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "current_positions",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("host_player", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("guest_player", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("player_turn", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_result", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["guest_player"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["host_player"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_turn"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("level", sa.String(length=10), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("gameplay_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["gameplay_id"], ["gameplays.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["player_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_gameplays_host_player", "gameplays", ["host_player"])
    op.create_index("idx_gameplays_guest_player", "gameplays", ["guest_player"])
    op.create_index("idx_gameplays_created_date", "gameplays", [sa.text("created_date DESC")])
    op.create_index("idx_logs_level", "logs", ["level"])
    op.create_index("idx_logs_event_type", "logs", ["event_type"])
    op.create_index("idx_logs_timestamp", "logs", [sa.text("timestamp DESC")])


def downgrade() -> None:
    op.drop_index("idx_logs_timestamp", table_name="logs")
    op.drop_index("idx_logs_event_type", table_name="logs")
    op.drop_index("idx_logs_level", table_name="logs")
    op.drop_index("idx_gameplays_created_date", table_name="gameplays")
    op.drop_index("idx_gameplays_guest_player", table_name="gameplays")
    op.drop_index("idx_gameplays_host_player", table_name="gameplays")
    op.drop_table("logs")
    op.drop_table("gameplays")
    op.drop_table("users")
