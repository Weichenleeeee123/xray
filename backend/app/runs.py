"""Append-only progress journal for recovering a browser tab after refresh.

Each run is one randomly named NDJSON file. A run's final event references the
already-persisted case; it does not duplicate private case data in the journal.
"""
import json
import re
import time
from pathlib import Path
from app.persistence import atomic_json

RUN_ID = re.compile(r"^[0-9a-f]{24}$")
LEASE_SECONDS = 30


def touch(directory: Path, run_id: str, *, finished: bool = False):
    atomic_json(path_for(directory, run_id).with_suffix(".lease"),
                {"expires": 0 if finished else time.time() + LEASE_SECONDS})


def active(directory: Path, run_id: str) -> bool:
    try:
        return json.loads(path_for(directory, run_id).with_suffix(".lease").read_text(encoding="utf-8"))["expires"] > time.time()
    except (OSError, ValueError, KeyError, TypeError):
        return False


def path_for(directory: Path, run_id: str) -> Path:
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("invalid run id")
    return directory / f"{run_id}.ndjson"


def append(directory: Path, run_id: str, event: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with path_for(directory, run_id).open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")


def save_input(directory: Path, run_id: str, body: dict) -> None:
    """Keep the complete original input separately from progress, for deliberate retries."""
    directory.mkdir(parents=True, exist_ok=True)
    path = path_for(directory, run_id).with_suffix(".input.json")
    atomic_json(path, body)


def read_input(directory: Path, run_id: str) -> dict | None:
    path = path_for(directory, run_id).with_suffix(".input.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def set_owner(directory: Path, run_id: str, owner_id: str) -> None:
    atomic_json(path_for(directory, run_id).with_suffix(".owner.json"), {"owner_id": owner_id})


def owned_by(directory: Path, run_id: str, owner_id: str) -> bool:
    try:
        path = path_for(directory, run_id).with_suffix(".owner.json")
        return json.loads(path.read_text(encoding="utf-8")).get("owner_id") == owner_id
    except (ValueError, OSError, TypeError):
        return False


def events(directory: Path, run_id: str) -> list[dict] | None:
    path = path_for(directory, run_id)
    if not path.is_file():
        return None
    collected = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            collected.append(json.loads(line))
        except json.JSONDecodeError:
            break  # A reader may catch the writer halfway through one line.
    return collected
