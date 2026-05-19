"""Initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "library_assets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_url", sa.String(2000), nullable=True),
        sa.Column("local_source_path", sa.String(1000), nullable=True),
        sa.Column("source_name", sa.String(500), nullable=True),
        sa.Column("duration_sec", sa.Integer, nullable=True),
        sa.Column("tags", JSONB, server_default="[]", nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("rights_status", sa.String(30), nullable=False, server_default="pending_review"),
        sa.Column("approval_notes", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="registered"),
        sa.Column("last_downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_streamed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("times_streamed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("current_local_path", sa.String(1000), nullable=True),
        sa.Column("current_local_size_bytes", sa.Integer, nullable=True),
        sa.Column("checksum", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "stream_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("target_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "stream_plan_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "stream_plan_id", UUID(as_uuid=True), sa.ForeignKey("stream_plans.id"), nullable=False
        ),
        sa.Column("sequence_index", sa.Integer, nullable=False),
        sa.Column(
            "video_asset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("library_assets.id"),
            nullable=False,
        ),
        sa.Column(
            "music_asset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("library_assets.id"),
            nullable=True,
        ),
        sa.Column("planned_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_duration_sec", sa.Integer, nullable=True),
        sa.Column("mix_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "video_audio_gain", sa.Numeric(3, 2), nullable=False, server_default="0.50"
        ),
        sa.Column(
            "music_audio_gain", sa.Numeric(3, 2), nullable=False, server_default="0.50"
        ),
        sa.Column("delete_after_stream", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("prep_status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("stream_status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("prepared_file_path", sa.String(1000), nullable=True),
        sa.Column("prepared_file_size_bytes", sa.Integer, nullable=True),
        sa.Column("actual_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_log", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "prep_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plan_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("stream_plan_items.id"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "stream_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column(
            "plan_id", UUID(as_uuid=True), sa.ForeignKey("stream_plans.id"), nullable=True
        ),
        sa.Column(
            "plan_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("stream_plan_items.id"),
            nullable=True,
        ),
        sa.Column(
            "asset_id", UUID(as_uuid=True), sa.ForeignKey("library_assets.id"), nullable=True
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("payload", JSONB, server_default="{}", nullable=False),
    )

    op.create_table(
        "daily_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("report_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("summary", JSONB, server_default="{}", nullable=False),
        sa.Column("markdown_text", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("report_date", name="uq_daily_reports_date"),
    )


def downgrade() -> None:
    op.drop_table("daily_reports")
    op.drop_table("stream_events")
    op.drop_table("prep_jobs")
    op.drop_table("stream_plan_items")
    op.drop_table("stream_plans")
    op.drop_table("library_assets")
