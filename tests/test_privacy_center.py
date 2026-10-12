"""Privacy Center history and diagnostics data-minimization tests."""

from __future__ import annotations

import json
import tempfile
from dataclasses import replace
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


def main() -> int:
    for test in (
        test_diagnostics_are_allowlisted_and_path_free,
        test_activity_records_network_actions_without_free_text,
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
