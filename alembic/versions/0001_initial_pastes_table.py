"""initial pastes table

Revision ID: 0001
Revises:
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pastes",
        sa.Column("slug", sa.String(12), primary_key=True, index=True, nullable=False),
        sa.Column("encrypted_content", sa.Text, nullable=False),
        sa.Column("language", sa.String(50), nullable=False, server_default="plaintext"),
        sa.Column("burn_after_read", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_password_protected", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("delete_token_hash", sa.String(64), nullable=False),
        sa.Column("password_salt", sa.String(64), nullable=True),
        sa.Column("view_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_burned", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_pastes_expires_at", "pastes", ["expires_at"])
    op.create_index("ix_pastes_is_burned", "pastes", ["is_burned"])


def downgrade() -> None:
    op.drop_index("ix_pastes_is_burned")
    op.drop_index("ix_pastes_expires_at")
    op.drop_table("pastes")
