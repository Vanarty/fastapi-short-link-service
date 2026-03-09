"""Initial tables

Revision ID: 001
Revises:
Create Date: 2025-03-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("short_code", sa.String(20), nullable=False, unique=True),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("click_count", sa.Integer(), server_default="0"),
    )
    op.create_index("ix_links_short_code", "links", ["short_code"])
    op.create_index("ix_links_original_url", "links", ["original_url"])

    op.create_table(
        "link_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("short_code", sa.String(20), nullable=False),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("reason", sa.String(50), nullable=False),
        sa.Column("click_count", sa.Integer(), server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("link_history")
    op.drop_table("links")
    op.drop_table("users")
