"""Synthetic local Box Sync copy and policy tests.

Run with: python -m tests.test_box_sync
"""

from __future__ import annotations

import hashlib
import tempfile
import time
import zipfile
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from app import activity, box_sync, config, projects

FAILURES: list = []


class FakeSettings:
    def __init__(self, destination: str = "", offline_lock: bool = False):
        self.values = {
            "box_sync_destination": destination,
            "offline_lock": offline_lock,
        }

    def get(self, key, fallback=None):
        return self.values.get(key, fallback)


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} {detail}")
        FAILURES.append(label)


@contextmanager
def backup_context(*, classification="no_phi", offline_lock=False):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        projects_root = root / "projects"
        logs = root / "logs"
        destination = root / "Box Sync [Box Health - Synthetic]"
        destination.mkdir()
        paths = replace(
            config.PATHS,
            projects=projects_root,
            logs=logs,
            models=root / "models",
            settings_file=root / "settings.json",
        )
        settings = FakeSettings(str(destination), offline_lock)
        with (
            patch.object(projects, "PATHS", paths),
            patch.object(config, "PATHS", paths),
            patch.object(config, "SETTINGS", settings),
        ):
            project = projects.create_project(
                "Synthetic Box backup", data_sensitivity=classification
            )
            document = projects.add_document(
                project["slug"], "synthetic.wav", data=b"synthetic media only"
            )
            projects.write_json(
                projects.document_dir(project["slug"], document["id"])
                / projects.TRANSCRIPT_FILE,
                {"text": "synthetic transcript only"},
            )
            yield root, destination, settings, project, document


def wait_for_job(manager: box_sync.BackupManager, slug: str, job_id: str):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = manager.get(slug, job_id)
        if job and job["status"] in ("complete", "failed", "cancelled"):
            return job
        time.sleep(0.01)
    raise AssertionError("backup job did not finish before timeout")


def test_explicit_destination_and_sensitivity_gate():
    with backup_context(classification="no_phi") as (root, dest, settings, project, _):
        manager = box_sync.BackupManager()
        try:
            manager.submit(
                project["slug"],
                confirm_sync_destination=False,
                independently_verified_box_health=False,
            )
        except box_sync.BackupError:
            check("requires explicit Box Sync folder confirmation", True)
        else:
            check("requires explicit Box Sync folder confirmation", False)

        settings.values["box_sync_destination"] = ""
        try:
            box_sync.configured_destination()
        except box_sync.BackupError:
            check("empty destination is never auto-selected", True)
        else:
            check("empty destination is never auto-selected", False)

        settings.values["box_sync_destination"] = "relative/Box"
        try:
            box_sync.configured_destination()
        except box_sync.BackupError:
            check("relative destination is rejected", True)
        else:
            check("relative destination is rejected", False)

        settings.values["box_sync_destination"] = str(projects.project_dir(project["slug"]))
        try:
            box_sync.configured_destination()
        except box_sync.BackupError:
            check("project storage cannot be used as Box destination", True)
        else:
            check("project storage cannot be used as Box destination", False)

        settings.values["box_sync_destination"] = str(dest)
        settings.values["offline_lock"] = True
        try:
            manager.submit(
                project["slug"],
                confirm_sync_destination=True,
                independently_verified_box_health=True,
            )
        except box_sync.BackupError as exc:
            check("Offline Lock blocks backup", "Offline Lock" in str(exc))
        else:
            check("Offline Lock blocks backup", False)

    with backup_context(classification="unknown_treat_as_phi") as (
        _root, _dest, settings, project, _
    ):
        ordinary_box = Path(_root) / "Box"
        ordinary_box.mkdir()
        settings.values["box_sync_destination"] = str(ordinary_box)
        try:
            box_sync.validate_backup_request(
                project["slug"],
                confirm_sync_destination=True,
                independently_verified_box_health=False,
            )
        except box_sync.BackupError as exc:
            check("PHI and unknown require Box Health", "Box Health" in str(exc))
        else:
            check("PHI and unknown require Box Health", False)

        validated, actual_destination = box_sync.validate_backup_request(
            project["slug"],
            confirm_sync_destination=True,
            independently_verified_box_health=True,
        )
        check("explicit independent verification permits policy gate",
              validated["slug"] == project["slug"] and actual_destination == ordinary_box)
        check("manual attestation is bound to the selected path",
              projects.load_project(project["slug"])["box_health_override"][
                  "destination_root"
              ] == str(ordinary_box))


def test_copy_verification_and_retry_after_interruption():
    with backup_context() as (_root, destination, _settings, project, _):
        manager = box_sync.BackupManager()
        original_open = Path.open

        def interrupted_open(path, mode="r", *args, **kwargs):
            if mode == "xb" and path.name.endswith(".partial"):
                partial = original_open(path, mode, *args, **kwargs)
                partial.write(b"interrupted partial bytes")
                partial.close()
                raise OSError("synthetic interrupted write")
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", interrupted_open):
            first = manager.submit(
                project["slug"],
                confirm_sync_destination=True,
                independently_verified_box_health=False,
            )
            failed = wait_for_job(manager, project["slug"], first["job_id"])
        check("interrupted transfer reports a retryable failure",
              failed["status"] == "failed" and bool(failed["error"]))
        check("interrupted transfer leaves no partial or final archive",
              not list(destination.glob("*.lsproj"))
              and not list(destination.glob(".*.partial")))

        retry = manager.submit(
            project["slug"],
            confirm_sync_destination=True,
            independently_verified_box_health=False,
        )
        completed = wait_for_job(manager, project["slug"], retry["job_id"])
        backed_up = destination / completed["filename"]
        check("retry completes with checksum verification",
              completed["status"] == "complete" and completed["verified"])
        check("verified archive is present at destination",
              backed_up.is_file() and backed_up.stat().st_size == completed["total_bytes"])
        check("destination archive manifest verifies",
              projects.inspect_archive(backed_up)["integrity_verified"])
        digest = hashlib.sha256(backed_up.read_bytes()).hexdigest()
        with zipfile.ZipFile(backed_up) as archive:
            check("archive carries the synthetic transcript",
                  b"synthetic transcript only" in archive.read(
                      f"documents/{projects.list_documents(project['slug'])[0]['id']}/"
                      f"{projects.TRANSCRIPT_FILE}"
                  ))
        check("backup outcome is recorded without a configured path",
              bool(activity.recent(project_id=project["project_id"]))
              and str(destination) not in str(activity.recent()))
        check("archive bytes are non-empty", bool(digest))


def test_cancellation_cleans_partial_output():
    with backup_context() as (_root, destination, _settings, project, _):
        manager = box_sync.BackupManager()
        original_copy = box_sync._copy_and_verify

        def cancel_during_copy(source, target, cancel_event, progress):
            cancel_event.set()
            return original_copy(source, target, cancel_event, progress)

        with patch.object(box_sync, "_copy_and_verify", cancel_during_copy):
            job = manager.submit(
                project["slug"],
                confirm_sync_destination=True,
                independently_verified_box_health=False,
            )
            result = wait_for_job(manager, project["slug"], job["job_id"])
        check("cancellation reports a cancelled outcome", result["status"] == "cancelled")
        check("cancelled archive is not published",
              not list(destination.glob("*.lsproj"))
              and not list(destination.glob(".*.partial")))
        retry = manager.submit(
            project["slug"],
            confirm_sync_destination=True,
            independently_verified_box_health=False,
        )
        completed = wait_for_job(manager, project["slug"], retry["job_id"])
        check("cancellation can be explicitly retried",
              completed["status"] == "complete" and completed["verified"])


def main() -> int:
    for test in (
        test_explicit_destination_and_sensitivity_gate,
        test_copy_verification_and_retry_after_interruption,
        test_cancellation_cleans_partial_output,
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
