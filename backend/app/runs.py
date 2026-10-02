"""Append-only progress journal for recovering a browser tab after refresh.

Each run is one randomly named NDJSON file. A run's final event references the
already-persisted case; it does not duplicate private case data in the journal.
"""
import json
import re
from pathlib import Path

RUN_ID = re.compile(r"^[0-9a-f]{24}$")


def path_for(directory: Path, run_id: str) -> Path:
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("invalid run id")
    return directory / f"{run_id}.ndjson"


def append(directory: Path, run_id: str, event: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with path_for(directory, run_id).open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")


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
