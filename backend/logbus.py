"""In-memory progress log per run, read by the UI's control deck.

Nodes and the runner call log(run_id, ...) and the API serves the tail. It is
deliberately not persisted: the durable record is the checkpoint + run dir.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

_LOGS: dict[str, deque] = defaultdict(lambda: deque(maxlen=400))


def log(run_id: str | None, message: str, kind: str = "info") -> None:
    if not run_id:
        return
    _LOGS[run_id].append({"t": time.time(), "kind": kind, "msg": message})
    print(f"[{run_id}] {message}", flush=True)


def tail(run_id: str, n: int = 80) -> list[dict]:
    return list(_LOGS[run_id])[-n:]


def clear(run_id: str) -> None:
    _LOGS.pop(run_id, None)
