"""Synthetic local Box Sync copy and policy tests.

Run with: python -m tests.test_box_sync
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import tempfile
import time
import zipfile
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from app import activity, box_sync, config, projects
from fastapi import HTTPException, Request

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
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
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

        settings.values["box_sync_destination"] = "\x00invalid"
        try:
            box_sync.configured_destination()
        except box_sync.BackupError:
            check("malformed destination path is rejected", True)
        else:
            check("malformed destination path is rejected", False)

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
            media_entry = next(
                name for name in archive.namelist() if name.startswith("media/")
            )
            check("archive media remains compressed",
                  archive.getinfo(media_entry).compress_type == zipfile.ZIP_DEFLATED)
        check("backup outcome is recorded without a configured path",
              bool(activity.recent(project_id=project["project_id"]))
              and str(destination) not in str(activity.recent()))
        check("archive bytes are non-empty", bool(digest))


def test_cancellation_cleans_partial_output():
    with backup_context() as (_root, destination, settings, project, _):
        manager = box_sync.BackupManager()
        original_copy = box_sync._copy_and_verify
        entered_copy = threading.Event()

        def cancel_during_copy(source, target, cancel_event, progress, check_allowed):
            entered_copy.set()
            cancel_event.wait(timeout=5)
            return original_copy(
                source, target, cancel_event, progress, check_allowed
            )

        with patch.object(box_sync, "_copy_and_verify", cancel_during_copy):
            job = manager.submit(
                project["slug"],
                confirm_sync_destination=True,
                independently_verified_box_health=False,
            )
            check("backup entered cancellable copy stage",
                  entered_copy.wait(timeout=5))
            check("active backup accepts cancellation",
                  manager.cancel(project["slug"], job["job_id"]))
            result = wait_for_job(manager, project["slug"], job["job_id"])
        check("cancellation reports a cancelled outcome", result["status"] == "cancelled")
        check("cancelled archive is not published",
              not list(destination.glob("*.lsproj"))
              and not list(destination.glob(".*.partial")))

        def engage_offline_during_copy(
            source, target, cancel_event, progress, check_allowed
        ):
            settings.values["offline_lock"] = True
            return original_copy(
                source, target, cancel_event, progress, check_allowed
            )

        with patch.object(
            box_sync, "_copy_and_verify", engage_offline_during_copy
        ):
            locked = manager.submit(
                project["slug"],
                confirm_sync_destination=True,
                independently_verified_box_health=False,
            )
            stopped = wait_for_job(manager, project["slug"], locked["job_id"])
        check("engaging Offline Lock stops an active copy",
              stopped["status"] == "failed"
              and "Offline Lock" in stopped["error"])
        check("Offline Lock interruption publishes no archive",
              not list(destination.glob("*.lsproj"))
              and not list(destination.glob(".*.partial")))

        settings.values["offline_lock"] = False
        retry = manager.submit(
            project["slug"],
            confirm_sync_destination=True,
            independently_verified_box_health=False,
        )
        completed = wait_for_job(manager, project["slug"], retry["job_id"])
        check("cancellation can be explicitly retried",
              completed["status"] == "complete" and completed["verified"])


def test_backup_api_and_project_ui():
    with backup_context() as (_root, destination, settings, project, _):
        with patch("app.update_check.refresh_state_async"), patch.object(
            config, "install_offline_guard"
        ):
            from app import main as web

        original_settings = web.SETTINGS
        web.SETTINGS = settings

        def request(payload=None):
            scope = {
                "type": "http", "method": "GET" if payload is None else "POST",
                "path": "/", "headers": [], "scheme": "http",
                "server": ("127.0.0.1", 43707), "query_string": b"",
            }

            async def receive():
                body = b"" if payload is None else json.dumps(payload).encode()
                return {"type": "http.request", "body": body, "more_body": False}

            return Request(scope, receive)

        async def exercise():
            try:
                await web.api_start_box_backup(
                    project["slug"],
                    request({"confirm_sync_destination": False}),
                )
            except HTTPException as exc:
                check("backup API requires destination confirmation",
                      exc.status_code == 400)
            else:
                check("backup API requires destination confirmation", False)

            page = await web.page_project(request(), project["slug"])
            check("project UI shows Box Sync confirmation and media option",
                  b"Back up to Box Sync" in page.body
                  and b"confirm-box-sync-destination" in page.body
                  and b"box-backup-include-media" in page.body)
            check("project UI does not reveal configured absolute path",
                  str(destination).encode() not in page.body)

            result = await web.api_start_box_backup(
                project["slug"],
                request({
                    "confirm_sync_destination": True,
                    "independently_verified_box_health": False,
                    "include_media": False,
                }),
            )
            job_id = result["backup"]["job_id"]
            completed = wait_for_job(box_sync.BACKUPS, project["slug"], job_id)
            status = await web.api_get_box_backup(project["slug"], job_id)
            check("backup API reports completed verified copy",
                  completed["status"] == "complete"
                  and status["backup"]["verified"])
            check("backup API exposes no destination path",
                  str(destination) not in str(status))

        try:
            asyncio.run(exercise())
        finally:
            web.SETTINGS = original_settings


def main() -> int:
    for test in (
        test_explicit_destination_and_sensitivity_gate,
        test_copy_verification_and_retry_after_interruption,
        test_cancellation_cleans_partial_output,
        test_backup_api_and_project_ui,
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
