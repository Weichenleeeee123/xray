"""Public release diagnostics: identifiers only, never configuration values or paths."""
import hashlib
import os
import re
from pathlib import Path

from app import config


def fingerprint(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else None


def status() -> dict:
    revision = os.getenv("XRAY_RELEASE_ID", "")
    return {
        "release_id": revision if re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", revision) else None,
        "report_asset": fingerprint(config.WEB_DIR / "app.js"),
        "home_asset": fingerprint(config.REPO_DIR / "research-room/home-dist/index.html"),
        "expected_model": "qwen3.8-max",
    }
