"""Add invitation lifecycle state and uniqueness enforcement."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

INVITATION_STATES = ("pending", "queued", "accepted", "rejected", "expired", "canceled")


def upgrade() -> None:
    op.add_column(
        "gameplays",
        sa.Column(
            "invitation_state",
            sa.String(length=32),
            nullable=False,
            server_default="accepted",
        ),
    )
    op.execute(
        """
        UPDATE gameplays
        SET invitation_state = CASE
            WHEN jsonb_typeof(match_result) = 'object' AND (match_result ->> 'reason') = 'pending'
                THEN 'pending'
            ELSE 'accepted'
        END
        """
    )
    op.alter_column("gameplays", "invitation_state", server_default=None)
    op.create_check_constraint(
        "ck_gameplays_invitation_state",
        "gameplays",
        ("invitation_state IN ('pending','queued','accepted','rejected','expired','canceled')"),
    )

    op.create_index(
        "idx_gameplays_pending_or_queued_host",
        "gameplays",
        ["host_player"],
        unique=False,
        postgresql_where=sa.text("invitation_state IN ('pending', 'queued')"),
    )
    op.create_index(
        "idx_gameplays_pending_or_queued_guest",
        "gameplays",
        ["guest_player"],
        unique=False,
        postgresql_where=sa.text(
            "invitation_state IN ('pending', 'queued') AND guest_player IS NOT NULL"
        ),
    )
    op.create_index(
        "idx_gameplays_active_host",
        "gameplays",
        ["host_player"],
        unique=True,
        postgresql_where=sa.text("invitation_state = 'accepted' AND match_result IS NULL"),
    )
    op.create_index(
        "idx_gameplays_active_guest",
        "gameplays",
        ["guest_player"],
        unique=True,
        postgresql_where=sa.text(
            "invitation_state = 'accepted' AND match_result IS NULL AND guest_player IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("idx_gameplays_active_guest", table_name="gameplays")
    op.drop_index("idx_gameplays_active_host", table_name="gameplays")
    op.drop_index("idx_gameplays_pending_or_queued_guest", table_name="gameplays")
    op.drop_index("idx_gameplays_pending_or_queued_host", table_name="gameplays")
    op.drop_constraint("ck_gameplays_invitation_state", "gameplays", type_="check")
    op.drop_column("gameplays", "invitation_state")
