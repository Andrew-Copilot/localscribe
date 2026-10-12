"""Bounded, content-free history for privacy-sensitive actions."""

from __future__ import annotations

import json
import hashlib
import threading
from datetime import datetime, timezone

from . import config

HISTORY_LIMIT = 200
_LOCK = threading.Lock()

_RECOVERY_ACTIONS = {
    "document_delete",
    "import_replace",
    "import_replace_snapshot",
    "project_delete",
    "snapshot_create",
    "snapshot_restore",
}
_REMOTE_ACTIONS = {
    "box_sync_backup",
    "gpu_support_install",
    "model_download",
    "network_settings_changed",
    "offline_lock_changed",
    "update_apply",
    "update_check",
}
_ACTIONS = _RECOVERY_ACTIONS | _REMOTE_ACTIONS
_OUTCOMES = {
    "aborted",
    "cancelled",
    "complete",
    "completed",
    "deleted_with_snapshot",
    "deleted_without_snapshot",
    "engaged",
    "failed",
    "released",
    "restored_rename",
    "restored_replace",
    "replaced_no",
    "replaced_yes",
    "started",
}
LABELS = {
    "box_sync_backup": "Box Sync backup",
    "document_delete": "Document deletion",
    "gpu_support_install": "GPU support download",
    "import_replace": "Project import replacement",
    "import_replace_snapshot": "Pre-import recovery snapshot",
    "model_download": "Model download",
    "network_settings_changed": "Network and backup settings",
    "offline_lock_changed": "Offline Lock change",
    "project_delete": "Project deletion",
    "snapshot_create": "Recovery snapshot created",
    "snapshot_restore": "Recovery snapshot restored",
    "update_apply": "Application update",
    "update_check": "Update check",
}


def _project_ref(project_id: str) -> str:
    return hashlib.sha256(str(project_id).encode("utf-8")).hexdigest()[:24]


def category(action: str) -> str:
    if not isinstance(action, str):
        return "other"
    if action in _REMOTE_ACTIONS:
        return "network"
    if action in _RECOVERY_ACTIONS:
        return "recovery"
    return "other"


def label(action: str) -> str:
    if not isinstance(action, str):
        return "Other activity"
    return LABELS.get(action, "Other activity")


def record(
    action: str, project_id: str | None = None, outcome: str = "completed"
) -> dict | None:
    """Persist an allow-listed event without titles, filenames, or paths."""
    path = config.PATHS.logs / "project-activity.json"
    action = action if isinstance(action, str) and action in _ACTIONS else "other"
    outcome = outcome if isinstance(outcome, str) and outcome in _OUTCOMES else "completed"
    with _LOCK:
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
                "action": action,
                "category": category(action),
                "outcome": outcome,
            }
            if project_id is not None:
                entry["project_ref"] = _project_ref(project_id)
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
    count = max(0, min(int(limit), HISTORY_LIMIT))
    if not count:
        return []
    path = config.PATHS.logs / "project-activity.json"
    with _LOCK:
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(entries, list):
            return []
        result = [
            entry for entry in entries
            if isinstance(entry, dict)
            and (
                project_id is None
                or entry.get("project_ref") == _project_ref(project_id)
            )
        ]
        return result[-count:]
