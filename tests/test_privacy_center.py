"""Privacy Center history and diagnostics data-minimization tests."""

from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from app import activity, config, diagnostics

FAILURES: list[str] = []


class FakeSettings:
    values = {
        "offline_lock": True,
        "check_for_updates": False,
        "box_sync_destination": "/private/user/Box Sync",
    }

    def get(self, key, fallback=None):
        return self.values.get(key, fallback)


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        FAILURES.append(label)


def test_diagnostics_are_allowlisted_and_path_free():
    sensitive = {
        "selected_model": "/private/user/transcript-token-SECRET",
        "target_device": "/private/user/token-SECRET",
        "state": "ready",
        "model_downloaded": True,
    }
    with patch.object(config, "SETTINGS", FakeSettings()):
        report = diagnostics.build(sensitive)
    encoded = json.dumps(report)
    check("diagnostics omit model names and user paths",
          "selected_model" not in encoded and "/private/user" not in encoded)
    check("diagnostics omit token and transcript sentinels",
          "SECRET" not in encoded and "transcript" not in encoded.lower())
    check("diagnostics report only safe state and backup booleans",
          report["engine"]["state"] == "ready"
          and report["privacy"]["offline_lock"]
          and report["privacy"]["box_sync_backup_configured"])


def test_activity_records_network_actions_without_free_text():
    with tempfile.TemporaryDirectory() as tmp:
        paths = replace(config.PATHS, logs=Path(tmp) / "logs")
        with patch.object(config, "PATHS", paths):
            activity.record("update_check", outcome="started")
            activity.record(
                "snapshot_create",
                "/private/user/Project title",
                "transcript token SECRET",
            )
            events = activity.recent()
            stored = (paths.logs / "project-activity.json").read_text(
                encoding="utf-8"
            )
    check("history classifies network and recovery actions",
          [event["category"] for event in events] == ["network", "recovery"])
    check("history excludes arbitrary outcome text and user paths",
          "SECRET" not in stored and "/private/user" not in stored
          and events[-1]["outcome"] == "completed")


def test_history_rows_are_readable_and_merge_started_results():
    day = "2026-10-12T20:16:23-05:00"
    events = [
        {"timestamp": day, "action": "update_check", "outcome": "started"},
        {"timestamp": "2026-10-12T20:16:24-05:00", "action": "update_check",
         "outcome": "completed"},
        {"timestamp": "2026-10-12T20:17:46-05:00", "action": "document_delete",
         "outcome": "deleted_without_snapshot",
         "project_ref": activity._project_ref("synthetic-1")},
        {"timestamp": "2026-10-12T20:18:00-05:00", "action": "box_sync_backup",
         "outcome": "failed", "project_ref": activity._project_ref("gone")},
        {"timestamp": "2026-10-12T20:19:00-05:00", "action": "model_download",
         "outcome": "started"},
        {"timestamp": "2026-10-12T20:20:00-05:00", "action": "other", "outcome": "completed"},
    ]
    titles = activity.title_index([{"project_id": "synthetic-1", "title": "Synthetic study"}])
    rows = activity.history_rows(events, titles, now=datetime.fromisoformat(day))
    check("a started event and its result become one row",
          [r["summary"] for r in rows if "update" in r["summary"].lower()]
          == ["Checked for updates"])
    check("history is newest first and skips uncategorised events",
          len(rows) == 4 and rows[0]["summary"] == "Started downloading a speech model")
    check("an unfinished start is labelled, not shown as success",
          rows[0]["status"] == "started" and rows[0]["status_label"] == "No result recorded")
    by_summary = {r["summary"]: r for r in rows}
    deleted = by_summary["Removed a recording without a recovery snapshot"]
    check("project titles are resolved for existing projects",
          deleted["project"] == "Synthetic study")
    failed = by_summary["A Box Sync backup failed"]
    check("deleted projects are named generically and failures are flagged",
          failed["project"] == "A deleted or unknown project" and failed["status"] == "failed")
    check("no raw identifiers or ISO text in the summary",
          all("_" not in r["summary"] and "T20:" not in r["summary"] for r in rows))
    check("dates read as Today and times as 12-hour clock",
          all(r["day"] == "Today" and r["time"][-2:] in ("AM", "PM") for r in rows))


def main() -> int:
    for test in (
        test_diagnostics_are_allowlisted_and_path_free,
        test_activity_records_network_actions_without_free_text,
        test_history_rows_are_readable_and_merge_started_results,
    ):
        print(f"\n{test.__name__}")
        test()
    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
