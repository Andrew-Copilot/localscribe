"""Bounded local history for recovery and destructive project actions."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .config import PATHS

HISTORY_LIMIT = 200


def record(action: str, project_id: str, outcome: str = "completed") -> dict | None:
    """Persist an event without recording project titles, filenames, or paths."""
    path = PATHS.logs / "project-activity.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            entries = []
        if not isinstance(entries, list):
            entries = []
        entry = {
            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "action": str(action),
            "outcome": str(outcome),
            "project_id": str(project_id),
        }
        entries.append(entry)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(
            json.dumps(entries[-HISTORY_LIMIT:], indent=2), encoding="utf-8"
        )
        temporary.replace(path)
        return entry
    except OSError:
        return None


def recent(project_id: str | None = None, limit: int = 50) -> list[dict]:
    path = PATHS.logs / "project-activity.json"
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(entries, list):
        return []
    result = [
        entry for entry in entries
        if isinstance(entry, dict)
        and (project_id is None or entry.get("project_id") == project_id)
    ]
    return result[-max(0, min(int(limit), HISTORY_LIMIT)):]
