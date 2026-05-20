"""Bounded tool layer — typed inputs/outputs for LLM actions.

The LLM must only propose actions through these typed verbs.
Each tool has typed request, typed response, validation, and audit logging.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ToolVerb(str, Enum):
    search_site = "search_site"
    open_result = "open_result"
    inspect_candidate = "inspect_candidate"
    verify_playback = "verify_playback"
    extract_metadata = "extract_metadata"
    register_retrieval_adapter = "register_retrieval_adapter"
    reject_candidate = "reject_candidate"
    expand_keywords = "expand_keywords"
    enrich_candidate = "enrich_candidate"
    build_candidate_shelf = "build_candidate_shelf"
    rerank_candidates = "rerank_candidates"
    schedule_slot = "schedule_slot"
    insert_buffer = "insert_buffer"
    choose_music_pairing = "choose_music_pairing"
    emit_media_ir = "emit_media_ir"
    write_report = "write_report"


# ---------- Discovery Tools ----------


class SearchSiteRequest(BaseModel):
    domain: str
    query: str
    max_results: int = 10


class SearchSiteResponse(BaseModel):
    results: list[dict] = Field(default_factory=list)
    total_found: int = 0


class OpenResultRequest(BaseModel):
    url: str
    domain: str


class OpenResultResponse(BaseModel):
    page_title: str = ""
    page_url: str = ""
    content_type: str = ""
    has_media: bool = False


class InspectCandidateRequest(BaseModel):
    page_url: str
    domain: str


class InspectCandidateResponse(BaseModel):
    title: str = ""
    duration_sec: int | None = None
    quality_signals: dict = Field(default_factory=dict)
    has_authorized_retrieval: bool = False
    retrieval_url: str | None = None
    retrieval_type: str | None = None
    tags: list[str] = Field(default_factory=list)


class VerifyPlaybackRequest(BaseModel):
    page_url: str
    domain: str


class VerifyPlaybackResponse(BaseModel):
    playback_works: bool = False
    player_type: str | None = None
    resolution: str | None = None
    duration_sec: int | None = None


class ExtractMetadataRequest(BaseModel):
    page_url: str
    domain: str


class ExtractMetadataResponse(BaseModel):
    title: str = ""
    description: str = ""
    duration_sec: int | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class RegisterRetrievalAdapterRequest(BaseModel):
    candidate_asset_id: str
    adapter_type: str
    adapter_spec: dict = Field(default_factory=dict)


class RegisterRetrievalAdapterResponse(BaseModel):
    adapter_id: str = ""
    success: bool = False


class RejectCandidateRequest(BaseModel):
    candidate_asset_id: str
    reason: str


class RejectCandidateResponse(BaseModel):
    success: bool = True


# ---------- Enrichment Tools ----------


class ExpandKeywordsRequest(BaseModel):
    base_keywords: list[str]
    category: str | None = None
    max_expansions: int = 5


class ExpandKeywordsResponse(BaseModel):
    expanded_keywords: list[str] = Field(default_factory=list)


class EnrichCandidateRequest(BaseModel):
    candidate_asset_id: str
    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    duration_sec: int | None = None


class EnrichCandidateResponse(BaseModel):
    mood_tags: list[str] = Field(default_factory=list)
    theme_tags: list[str] = Field(default_factory=list)
    energy_score: float = 0.5
    pacing_score: float = 0.5
    repetition_risk: float = 0.0
    music_pairing_hints: list[str] = Field(default_factory=list)
    prime_time_fit: float = 0.5
    late_night_fit: float = 0.5
    llm_notes: str = ""


# ---------- Curation Tools ----------


class BuildCandidateShelfRequest(BaseModel):
    min_duration_sec: int = 60
    max_candidates: int = 100


class BuildCandidateShelfResponse(BaseModel):
    candidate_ids: list[str] = Field(default_factory=list)
    total_duration_sec: int = 0


class RerankCandidatesRequest(BaseModel):
    candidate_ids: list[str]
    context: dict = Field(default_factory=dict)
    max_reorder_distance: int = 3


class RerankCandidatesResponse(BaseModel):
    reranked_ids: list[str] = Field(default_factory=list)
    changes: list[dict] = Field(default_factory=list)


class ScheduleSlotRequest(BaseModel):
    lineup_run_id: str
    candidate_asset_id: str
    sequence_index: int
    slot_type: str = "main"
    decision_reason: str = ""


class ScheduleSlotResponse(BaseModel):
    lineup_item_id: str = ""
    success: bool = True


class InsertBufferRequest(BaseModel):
    lineup_run_id: str
    after_sequence_index: int
    buffer_asset_id: str | None = None
    duration_sec: int = 30


class InsertBufferResponse(BaseModel):
    lineup_item_id: str = ""
    success: bool = True


class ChooseMusicPairingRequest(BaseModel):
    candidate_asset_id: str
    available_music_refs: list[str] = Field(default_factory=list)


class ChooseMusicPairingResponse(BaseModel):
    chosen_music_ref: str | None = None
    reason: str = ""


class EmitMediaIRRequest(BaseModel):
    asset_id: str
    ops: list[dict] = Field(default_factory=list)


class EmitMediaIRResponse(BaseModel):
    ir_job_id: str = ""
    success: bool = True


class WriteReportRequest(BaseModel):
    report_date: str
    sections: dict = Field(default_factory=dict)


class WriteReportResponse(BaseModel):
    report_id: str = ""
    success: bool = True


# ---------- Audit ----------


class ToolAuditEntry(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    verb: ToolVerb
    request_data: dict = Field(default_factory=dict)
    response_data: dict = Field(default_factory=dict)
    success: bool = True
    error: str | None = None
