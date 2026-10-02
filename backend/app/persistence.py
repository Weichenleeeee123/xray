"""Small file-store primitives. Locks work across threads and worker processes."""
import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

_guard = threading.Lock()
_locks: dict[str, threading.RLock] = {}


@contextmanager
def locked(path: Path):
    key = str(path.resolve())
    with _guard:
        lock = _locks.setdefault(key, threading.RLock())
    with lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.with_suffix(path.suffix + ".lock").open("a+b") as handle:
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)


def atomic_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f".{uuid4().hex}.tmp")
    with temp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def atomic_json(path: Path, data):
    atomic_text(path, json.dumps(data, ensure_ascii=False, allow_nan=False))
