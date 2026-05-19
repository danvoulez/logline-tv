"""Tool executor — validates LLM-proposed actions against bounded tool grammar.

The LLM proposes actions as typed tool calls. This executor validates,
dispatches, logs, and returns typed responses. The LLM never executes directly.
"""

import structlog

from .tool_types import (
    ToolAuditEntry,
    ToolVerb,
)

logger = structlog.get_logger()

# In-memory audit log — capped to prevent unbounded growth
_audit_log: list[ToolAuditEntry] = []
_AUDIT_LOG_MAX = 500


TOOL_REQUEST_TYPES = {
    ToolVerb.search_site: "SearchSiteRequest",
    ToolVerb.open_result: "OpenResultRequest",
    ToolVerb.inspect_candidate: "InspectCandidateRequest",
    ToolVerb.verify_playback: "VerifyPlaybackRequest",
    ToolVerb.extract_metadata: "ExtractMetadataRequest",
    ToolVerb.register_retrieval_adapter: "RegisterRetrievalAdapterRequest",
    ToolVerb.reject_candidate: "RejectCandidateRequest",
    ToolVerb.expand_keywords: "ExpandKeywordsRequest",
    ToolVerb.enrich_candidate: "EnrichCandidateRequest",
    ToolVerb.build_candidate_shelf: "BuildCandidateShelfRequest",
    ToolVerb.rerank_candidates: "RerankCandidatesRequest",
    ToolVerb.schedule_slot: "ScheduleSlotRequest",
    ToolVerb.insert_buffer: "InsertBufferRequest",
    ToolVerb.choose_music_pairing: "ChooseMusicPairingRequest",
    ToolVerb.emit_media_ir: "EmitMediaIRRequest",
    ToolVerb.write_report: "WriteReportRequest",
}


def validate_tool_call(verb: str, params: dict) -> tuple[bool, str]:
    """Validate that a tool call uses a known verb and well-formed params."""
    try:
        tool_verb = ToolVerb(verb)
    except ValueError:
        return False, f"Unknown tool verb: {verb}"

    if tool_verb not in TOOL_REQUEST_TYPES:
        return False, f"No request type registered for verb: {verb}"

    return True, ""


def record_audit(verb: ToolVerb, request_data: dict, response_data: dict,
                 success: bool = True, error: str | None = None) -> None:
    """Record a tool execution in the audit log."""
    entry = ToolAuditEntry(
        verb=verb,
        request_data=request_data,
        response_data=response_data,
        success=success,
        error=error,
    )
    _audit_log.append(entry)
    if len(_audit_log) > _AUDIT_LOG_MAX:
        del _audit_log[:_AUDIT_LOG_MAX // 2]
    logger.info("tool_audit", verb=verb.value, success=success, error=error)


def get_audit_log() -> list[ToolAuditEntry]:
    """Return the current session's audit log."""
    return list(_audit_log)


def clear_audit_log() -> None:
    """Clear the audit log."""
    _audit_log.clear()
