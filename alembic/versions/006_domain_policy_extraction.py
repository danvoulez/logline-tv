"""Move site adapter config from Python to domain_policies.

Adds extraction/login/credential columns so the admin UI can manage any site
(adult or not) without touching code. Banco começa vazio — sem seed.

Revision ID: 006
Revises: 005
Create Date: 2026-05-19
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Search / browse templates
    op.add_column("domain_policies", sa.Column("search_url_template", sa.Text(), nullable=True))
    op.add_column("domain_policies", sa.Column("user_url_template", sa.Text(), nullable=True))

    # DOM selectors
    op.add_column("domain_policies", sa.Column("result_selector", sa.Text(), nullable=True))
    op.add_column("domain_policies", sa.Column("title_selector", sa.Text(), nullable=True))

    # Login flow
    op.add_column("domain_policies", sa.Column("login_url", sa.Text(), nullable=True))
    op.add_column("domain_policies", sa.Column("login_email_selector", sa.Text(), nullable=True))
    op.add_column("domain_policies", sa.Column("login_password_selector", sa.Text(), nullable=True))
    op.add_column("domain_policies", sa.Column("login_submit_selector", sa.Text(), nullable=True))
    op.add_column("domain_policies", sa.Column("login_success_selector", sa.Text(), nullable=True))

    # Credentials (stored in DB — no more .env hardcoding)
    op.add_column("domain_policies", sa.Column("credential_email", sa.Text(), nullable=True))
    op.add_column("domain_policies", sa.Column("credential_password", sa.Text(), nullable=True))

    # File extensions accepted as direct retrieval
    op.add_column(
        "domain_policies",
        sa.Column(
            "accepted_extensions",
            JSONB(),
            nullable=False,
            server_default='["mp4", "webm", "m3u8", "mpd"]',
        ),
    )

    # Flags
    op.add_column(
        "domain_policies",
        sa.Column("is_adult", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "domain_policies",
        sa.Column("requires_login", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "domain_policies",
        sa.Column(
            "needs_media_interception",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Title suffix patterns to strip ("Video — XVIDEOS.COM" → "Video")
    op.add_column(
        "domain_policies",
        sa.Column("title_suffix_strips", JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    for col in (
        "title_suffix_strips",
        "needs_media_interception",
        "requires_login",
        "is_adult",
        "accepted_extensions",
        "credential_password",
        "credential_email",
        "login_success_selector",
        "login_submit_selector",
        "login_password_selector",
        "login_email_selector",
        "login_url",
        "title_selector",
        "result_selector",
        "user_url_template",
        "search_url_template",
    ):
        op.drop_column("domain_policies", col)
