import enum


class SearchMode(str, enum.Enum):
    keyword_search = "keyword_search"
    listing_browse = "listing_browse"
    direct_lookup = "direct_lookup"


class KeywordSource(str, enum.Enum):
    operator = "operator"
    llm_expanded = "llm_expanded"
    learned_from_success = "learned_from_success"


class DiscoveryRunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class RetrievalStatus(str, enum.Enum):
    none = "none"
    authorized_direct = "authorized_direct"
    authorized_official = "authorized_official"
    metadata_only = "metadata_only"
    blocked = "blocked"


class CandidateRightsStatus(str, enum.Enum):
    pending_review = "pending_review"
    approved_for_stream = "approved_for_stream"
    blocked = "blocked"


class DiscoveryStatus(str, enum.Enum):
    found = "found"
    inspected = "inspected"
    accepted = "accepted"
    rejected = "rejected"


class AdapterType(str, enum.Enum):
    direct_url = "direct_url"
    official_download = "official_download"
    official_api = "official_api"
    uploaded_file = "uploaded_file"


class LineupStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    emitted = "emitted"
    failed = "failed"


class SlotType(str, enum.Enum):
    main = "main"
    buffer = "buffer"
    fallback_reserve = "fallback_reserve"
    music_overlay = "music_overlay"


class MediaIRStatus(str, enum.Enum):
    queued = "queued"
    compiled = "compiled"
    failed = "failed"
