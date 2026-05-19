import enum


class AssetKind(str, enum.Enum):
    video = "video"
    music = "music"


class SourceType(str, enum.Enum):
    direct_url = "direct_url"
    uploaded_file = "uploaded_file"


class RightsStatus(str, enum.Enum):
    pending_review = "pending_review"
    approved_for_stream = "approved_for_stream"
    blocked = "blocked"


class AssetStatus(str, enum.Enum):
    registered = "registered"
    approved = "approved"
    blocked = "blocked"
    downloaded = "downloaded"
    prepared = "prepared"
    deleted = "deleted"


class PlanStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    preparing = "preparing"
    ready = "ready"
    streaming = "streaming"
    completed = "completed"
    failed = "failed"


class PrepStatus(str, enum.Enum):
    queued = "queued"
    preparing = "preparing"
    ready = "ready"
    failed = "failed"


class StreamItemStatus(str, enum.Enum):
    queued = "queued"
    streaming = "streaming"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class JobType(str, enum.Enum):
    download = "download"
    normalize = "normalize"
    mix = "mix"
    finalize = "finalize"
    cleanup = "cleanup"


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"


class EventType(str, enum.Enum):
    stream_started = "stream_started"
    item_started = "item_started"
    item_completed = "item_completed"
    item_failed = "item_failed"
    fallback_started = "fallback_started"
    fallback_stopped = "fallback_stopped"
    cleanup_deleted = "cleanup_deleted"
    cleanup_failed = "cleanup_failed"
    disconnect = "disconnect"
    reconnect = "reconnect"
    report_generated = "report_generated"


class ReportStatus(str, enum.Enum):
    generated = "generated"
    failed = "failed"
