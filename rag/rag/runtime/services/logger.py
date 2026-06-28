"""
Structured JSON logger for CloudWatch.

Emits raw JSON lines so CloudWatch Logs Insights can query them directly.

CloudWatch Logs Insights query example:
    fields @timestamp, level, message, latency_ms
    | filter request_id = "abc-123"
    | sort @timestamp asc
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone


def log(level: str, message: str, **kwargs: object) -> None:
    """
    Emit a single structured JSON log line to stdout.

    Args:
        level:   Log level string ("INFO", "WARNING", "ERROR").
        message: Human-readable summary of the event.
        **kwargs: Arbitrary key/value pairs merged into the log record.
                  Common keys: request_id, latency_ms, model_id, error.
    """
    record: dict = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "level": level.upper(),
        "message": message,
        **kwargs,
    }
    # flush=True: ensures the line reaches CloudWatch before Lambda freezes.
    print(json.dumps(record, default=str), flush=True, file=sys.stdout)
