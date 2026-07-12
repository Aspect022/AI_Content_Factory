"""JSON log schema constants used by durable run log writers."""

RUN_LOG_REQUIRED_FIELDS = frozenset(
    {
        "run_id",
        "date",
        "status",
        "provider",
        "model",
        "topic",
        "title",
        "youtube_url",
        "duration_seconds",
        "generation_seconds",
        "error",
        "retry_count",
    }
)
