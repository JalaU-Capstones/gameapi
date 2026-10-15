"""Keep the rival's history when an account is deleted.

host_player and player_turn become nullable and their foreign keys use
ON DELETE SET NULL (guest_player already does). Deleting a user no longer
cascades to the gameplays they hosted, and no longer fails with a 500 when
they held the turn of a game they were invited to.
"""

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.alter_column("gameplays", "host_player", existing_type=UUID, nullable=True)
    op.alter_column("gameplays", "player_turn", existing_type=UUID, nullable=True)

    op.drop_constraint("gameplays_host_player_fkey", "gameplays", type_="foreignkey")
    op.create_foreign_key(
        "gameplays_host_player_fkey",
        "gameplays",
        "users",
        ["host_player"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint("gameplays_player_turn_fkey", "gameplays", type_="foreignkey")
    op.create_foreign_key(
        "gameplays_player_turn_fkey",
        "gameplays",
        "users",
        ["player_turn"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Rows whose host or turn was nulled by an account deletion cannot satisfy
    # NOT NULL again, so they are removed before restoring the old constraints.
    op.execute("DELETE FROM gameplays WHERE host_player IS NULL OR player_turn IS NULL")

    op.drop_constraint("gameplays_player_turn_fkey", "gameplays", type_="foreignkey")
    op.create_foreign_key(
        "gameplays_player_turn_fkey",
        "gameplays",
        "users",
        ["player_turn"],
        ["id"],
    )

    op.drop_constraint("gameplays_host_player_fkey", "gameplays", type_="foreignkey")
    op.create_foreign_key(
        "gameplays_host_player_fkey",
        "gameplays",
        "users",
        ["host_player"],
        ["id"],
        ondelete="CASCADE",
    )

    op.alter_column("gameplays", "player_turn", existing_type=UUID, nullable=False)
    op.alter_column("gameplays", "host_player", existing_type=UUID, nullable=False)
