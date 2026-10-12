"""Local snapshot and restore safeguards. Run: python -m tests.test_recovery"""

from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from app import activity, config, projects, snapshots

FAILURES: list = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} {detail}")
        FAILURES.append(label)


def rejects(label, operation, exception=projects.ProjectError):
    try:
        operation()
    except exception:
        check(label, True)
    else:
        check(label, False)


def fixture():
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    paths = replace(config.PATHS, projects=root / "projects", logs=root / "logs")
    stack = patch.object(projects, "PATHS", paths)
    stack.start()
    config_stack = patch.object(config, "PATHS", paths)
    config_stack.start()
    activity_stack = patch.object(activity, "PATHS", paths)
    activity_stack.start()
    return temporary, paths, (stack, config_stack, activity_stack)


def cleanup(temporary, patches):
    for item in reversed(patches):
        item.stop()
    temporary.cleanup()


def test_local_snapshot_and_safe_restore_choices():
    temporary, paths, patches = fixture()
    try:
        source = projects.create_project("Recovery fixture")
        slug = source["slug"]
        projects.add_document(slug, "synthetic.wav", data=b"synthetic")
        archive = projects.create_local_snapshot(slug)
        check("local snapshot is stored outside the project", archive.is_relative_to(paths.projects / ".snapshots"))
        check("local snapshot validates", snapshots.validate_snapshot(archive)["slug"] == slug)
        projects.delete_project(slug)

        imported = projects.import_project(archive, mode="prompt")
        check("prompt restore imports when there is no conflict", imported["slug"] == slug)
        projects.save_project(slug, {"title": "Local version"})
        conflict = projects.import_project(archive, mode="prompt")
        check("prompt restore reports conflicts without replacing", conflict.get("conflict") is True)
        check("conflict leaves local project intact", projects.load_project(slug)["title"] == "Local version")
        renamed = projects.import_project(archive, mode="rename")
        check("explicit rename keeps both projects", renamed["slug"] == f"{slug}-2")
        check("rename does not alter the existing project", projects.load_project(slug)["title"] == "Local version")

        restored = projects.import_project(archive, mode="replace", snapshot_before=True)
        check("explicit replace restores incoming project", restored["title"] == source["title"])
        backups = list((paths.projects / ".snapshots" / slug).glob("*.lsproj"))
        check("replace can preserve a pre-restore snapshot", len(backups) >= 2)
        rejects("snapshot traversal is rejected", lambda: projects.get_local_snapshot(slug, "../outside.lsproj"))
    except Exception as exc:
        check("local snapshot and restore choices", False, str(exc))
    finally:
        cleanup(temporary, patches)


def test_activity_is_local_and_project_scoped():
    temporary, paths, patches = fixture()
    try:
        activity.record("study-one", "create_snapshot", "success", snapshot_created=True)
        activity.record("study-two", "restore", "success", mode="rename")
        events = activity.for_project("study-one")
        check("activity history is project-scoped", len(events) == 1 and events[0]["project_slug"] == "study-one")
        check("activity retains the operation outcome", events[0]["outcome"] == "success")
        check("activity file is kept in local app data", (paths.logs / "project-activity.json").is_file())
    except Exception as exc:
        check("local activity history", False, str(exc))
    finally:
        cleanup(temporary, patches)


def main() -> int:
    test_local_snapshot_and_safe_restore_choices()
    test_activity_is_local_and_project_scoped()
    if FAILURES:
        print(f"\n{len(FAILURES)} test(s) failed: {', '.join(FAILURES)}")
        return 1
    print("\nAll recovery tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
