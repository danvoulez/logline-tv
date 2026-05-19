"""Director runs + actions.

Each director tick creates a DirectorRun (state snapshot + LLM response).
Each verb the LLM emits creates a DirectorAction (executed, rejected or failed).

Revision ID: 007
Revises: 006
Create Date: 2026-05-19
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "director_runs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state_snapshot", JSONB(), nullable=False, server_default="{}"),
        sa.Column("llm_response", JSONB(), nullable=False, server_default="{}"),
        sa.Column("action_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text(), nullable=True),
    )

    op.create_table(
        "director_actions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("director_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence_index", sa.Integer(), nullable=False),
        sa.Column("verb", sa.String(50), nullable=False),
        sa.Column("args", JSONB(), nullable=False, server_default="{}"),
        sa.Column("why", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="pending"
        ),  # pending | executed | rejected | failed
        sa.Column("result", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_director_actions_run_id_seq",
        "director_actions",
        ["run_id", "sequence_index"],
    )
    op.create_index(
        "ix_director_actions_created_at",
        "director_actions",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_director_actions_created_at", "director_actions")
    op.drop_index("ix_director_actions_run_id_seq", "director_actions")
    op.drop_table("director_actions")
    op.drop_table("director_runs")
