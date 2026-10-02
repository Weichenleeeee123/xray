"""Expiring provider cache; preserve malformed input for diagnosis without deletion."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from contextvars import ContextVar

from app.persistence import atomic_text
FORCE_REFRESH = ContextVar("force_refresh", default=False)


def read_fresh(path: Path, field: str, *, force: bool = False) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        saved = json.loads(text)
        if not isinstance(saved, dict) or not isinstance(saved[field], dict):
            raise ValueError("invalid cache payload")
        stamp = datetime.fromisoformat(saved["retrieved_at"])
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - stamp).total_seconds()
        ttl = max(0, int(os.getenv("XRAY_COMMERCIAL_CACHE_TTL", "86400")))
        return saved if not (force or FORCE_REFRESH.get()) and 0 <= age < ttl else None
    except (ValueError, KeyError, TypeError):
        try:
            atomic_text(path.with_suffix(f".corrupt-{uuid4().hex}"), text)
        except OSError:
            pass  # Keep the original; inability to cache must not stop source collection.
        return None
