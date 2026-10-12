"""Persistent, local-only history for project recovery actions."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

from .config import PATHS

_LOCK = threading.RLock()
_MAX_EVENTS = 500


def _path():
    return PATHS.logs / "project-activity.json"


def record(project_slug: str, action: str, outcome: str, **details) -> dict:
    event = {
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "project_slug": project_slug,
        "action": action,
        "outcome": outcome,
    }
    for key in ("mode", "snapshot_created"):
        if key in details:
            event[key] = details[key]

    with _LOCK:
        path = _path()
        try:
            events = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(events, list):
                events = []
        except (OSError, ValueError):
            events = []
        events = [item for item in events if isinstance(item, dict)]
        events.append(event)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        try:
            temporary.write_text(json.dumps(events[-_MAX_EVENTS:], indent=2), encoding="utf-8")
            temporary.replace(path)
        except OSError:
            temporary.unlink(missing_ok=True)
    return event


def for_project(project_slug: str, limit: int = 50) -> list[dict]:
    with _LOCK:
        try:
            events = json.loads(_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
    if not isinstance(events, list):
        return []
    matching = [
        event for event in events
        if isinstance(event, dict) and event.get("project_slug") == project_slug
    ]
    count = max(0, min(int(limit), 100))
    return matching[-count:] if count else []


def recent(limit: int = 50) -> list[dict]:
    with _LOCK:
        try:
            events = json.loads(_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
    if not isinstance(events, list):
        return []
    count = max(0, min(int(limit), 100))
    return [event for event in events[-count:] if isinstance(event, dict)] if count else []
