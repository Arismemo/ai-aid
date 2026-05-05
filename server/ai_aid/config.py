import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str
    max_body_kb: int
    rate_limit_per_min: int
    event_buffer: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            db_path=os.environ.get("AI_AID_DB_PATH", "/data/ai-aid.db"),
            max_body_kb=int(os.environ.get("AI_AID_MAX_BODY_KB", "100")),
            rate_limit_per_min=int(os.environ.get("AI_AID_RATE_LIMIT_PER_MIN", "30")),
            event_buffer=int(os.environ.get("AI_AID_EVENT_BUFFER", "1000")),
        )
