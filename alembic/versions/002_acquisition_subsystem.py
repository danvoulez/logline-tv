"""Acquisition subsystem — 10 new tables.

Revision ID: 002_acquisition
Revises: 001_initial_schema
Create Date: 2026-05-19
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "002_acquisition"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. domain_policies
    op.create_table(
        "domain_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("domain", sa.String(500), nullable=False, unique=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("session_profile_name", sa.String(200), nullable=True),
        sa.Column("search_mode", sa.String(50), nullable=False, server_default="keyword_search"),
        sa.Column("allowed_actions", JSONB(), nullable=False, server_default="{}"),
        sa.Column("retrieval_modes", JSONB(), nullable=False, server_default="[]"),
        sa.Column("requires_playback_verification", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("quality_floor", sa.String(50), nullable=True),
        sa.Column("max_pages_per_run", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # 2. search_keywords
    op.create_table(
        "search_keywords",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("keyword", sa.String(500), nullable=False),
        sa.Column("category", sa.String(200), nullable=True),
        sa.Column("weight", sa.Numeric(5, 2), nullable=False, server_default=sa.text("1.0")),
        sa.Column("include", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("source", sa.String(50), nullable=False, server_default="operator"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # 3. discovery_runs
    op.create_table(
        "discovery_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("input_summary", JSONB(), nullable=False, server_default="{}"),
        sa.Column("output_summary", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # 5. retrieval_adapters (created before candidate_assets due to FK)
    op.create_table(
        "retrieval_adapters",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("candidate_asset_id", UUID(as_uuid=True), nullable=False),
        sa.Column("adapter_type", sa.String(50), nullable=False),
        sa.Column("adapter_spec", JSONB(), nullable=False, server_default="{}"),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # 4. candidate_assets
    op.create_table(
        "candidate_assets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("discovery_run_id", UUID(as_uuid=True), sa.ForeignKey("discovery_runs.id"), nullable=True),
        sa.Column("domain_policy_id", UUID(as_uuid=True), sa.ForeignKey("domain_policies.id"), nullable=True),
        sa.Column("source_url", sa.String(2000), nullable=True),
        sa.Column("page_url", sa.String(2000), nullable=True),
        sa.Column("title", sa.String(1000), nullable=False),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("quality_signals", JSONB(), nullable=False, server_default="{}"),
        sa.Column("tags", JSONB(), nullable=False, server_default="[]"),
        sa.Column("metadata", JSONB(), nullable=False, server_default="{}"),
        sa.Column("playback_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("retrieval_status", sa.String(50), nullable=False, server_default="none"),
        sa.Column("retrieval_adapter_id", UUID(as_uuid=True), sa.ForeignKey("retrieval_adapters.id"), nullable=True),
        sa.Column("rights_status", sa.String(50), nullable=False, server_default="pending_review"),
        sa.Column("discovery_status", sa.String(50), nullable=False, server_default="found"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Add FK from retrieval_adapters back to candidate_assets
    op.create_foreign_key(
        "fk_retrieval_adapters_candidate",
        "retrieval_adapters",
        "candidate_assets",
        ["candidate_asset_id"],
        ["id"],
    )

    # 6. asset_enrichments
    op.create_table(
        "asset_enrichments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("candidate_asset_id", UUID(as_uuid=True), sa.ForeignKey("candidate_assets.id"), nullable=False, unique=True),
        sa.Column("mood_tags", JSONB(), nullable=False, server_default="[]"),
        sa.Column("theme_tags", JSONB(), nullable=False, server_default="[]"),
        sa.Column("energy_score", sa.Numeric(3, 2), nullable=True),
        sa.Column("pacing_score", sa.Numeric(3, 2), nullable=True),
        sa.Column("repetition_risk", sa.Numeric(3, 2), nullable=True),
        sa.Column("music_pairing_hints", JSONB(), nullable=False, server_default="[]"),
        sa.Column("prime_time_fit", sa.Numeric(3, 2), nullable=True),
        sa.Column("late_night_fit", sa.Numeric(3, 2), nullable=True),
        sa.Column("llm_notes", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # 7. lineup_runs
    op.create_table(
        "lineup_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("lineup_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("context_summary", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # 8. lineup_items
    op.create_table(
        "lineup_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("lineup_run_id", UUID(as_uuid=True), sa.ForeignKey("lineup_runs.id"), nullable=False),
        sa.Column("sequence_index", sa.Integer(), nullable=False),
        sa.Column("candidate_asset_id", UUID(as_uuid=True), sa.ForeignKey("candidate_assets.id"), nullable=False),
        sa.Column("target_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("slot_type", sa.String(50), nullable=False, server_default="main"),
        sa.Column("music_asset_ref", sa.String(500), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # 9. media_ir_jobs
    op.create_table(
        "media_ir_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("lineup_item_id", UUID(as_uuid=True), sa.ForeignKey("lineup_items.id"), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="queued"),
        sa.Column("ir_json", JSONB(), nullable=False, server_default="{}"),
        sa.Column("compiler_version", sa.String(50), nullable=False, server_default="1.0.0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # 10. autonomy_reports
    op.create_table(
        "autonomy_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("report_date", sa.Date(), nullable=False, unique=True),
        sa.Column("summary", JSONB(), nullable=False, server_default="{}"),
        sa.Column("markdown_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("autonomy_reports")
    op.drop_table("media_ir_jobs")
    op.drop_table("lineup_items")
    op.drop_table("lineup_runs")
    op.drop_table("asset_enrichments")
    op.drop_constraint("fk_retrieval_adapters_candidate", "retrieval_adapters", type_="foreignkey")
    op.drop_table("candidate_assets")
    op.drop_table("retrieval_adapters")
    op.drop_table("discovery_runs")
    op.drop_table("search_keywords")
    op.drop_table("domain_policies")
