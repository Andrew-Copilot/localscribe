"""Synthetic, local-only snapshot fixtures. Run: python -m tests.test_snapshots"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import stat
import tempfile
import warnings
import zipfile
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from app import config, projects, snapshots, transcript

FAILURES: list = []
CREATED = "2026-01-01T00:00:00+00:00"


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} {detail}")
        FAILURES.append(label)


def rejects(label, operation, exception=snapshots.SnapshotError):
    try:
        operation()
    except exception:
        check(label, True)
    else:
        check(label, False)


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = replace(config.PATHS, projects=root / "projects", logs=root / "logs")
        with patch.object(projects, "PATHS", paths), patch.object(config, "PATHS", paths):
            record = projects.create_project("Synthetic study", data_sensitivity="may_contain_phi")
            slug = record["slug"]
            doc = projects.add_document(slug, "synthetic.wav", data=b"synthetic media")
            document = projects.document_dir(slug, doc["id"])
            canonical = transcript.new_document(
                duration=1, model="synthetic-model", language="en",
                engine={"beam_size": 5, "device": "cpu", "temperature": [0.0, 0.2]},
            )
            canonical["segments"] = [transcript.make_segment(0, 0, 1, "Synthetic private text")]
            projects.save_transcript(slug, doc["id"], canonical, revision=False)
            (document / "preview.m4a").write_bytes(b"synthetic preview audio")
            projects.write_json(document / "waveform.json", {"cache": [0, 1]})
            projects.write_json(document / "revisions" / "20260101-000000-001.json", canonical)
            (document / "outputs" / "transcript.txt").write_text("Synthetic private text", encoding="utf-8")
            yield root, slug, doc["id"]


def exported(root, slug, include_media=True):
    with patch.object(projects, "_now", return_value=CREATED):
        return projects.export_project(slug, root / "archives", include_media)


def rewrite(source, dest, transform=None, remove=None, extras=None):
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(dest, "w") as out:
        for info in src.infolist():
            if info.filename == remove:
                continue
            data = src.read(info)
            if transform:
                data = transform(info.filename, data)
            out.writestr(info, data)
        for name, data in (extras or {}).items():
            out.writestr(name, data)
    return dest


def change_manifest(change):
    def transform(name, data):
        if name == snapshots.MANIFEST_FILE:
            manifest = json.loads(data)
            change(manifest)
            return json.dumps(manifest).encode()
        return data
    return transform


def test_deterministic_full_and_transcript_only():
    with fixture() as (root, slug, doc_id):
        full = exported(root, slug)
        second = exported(root, slug)
        manifest = snapshots.validate_snapshot(full)
        check("same data and clock give deterministic manifests",
              manifest == snapshots.validate_snapshot(second))
        check("archives do not overwrite each other", full != second and full.exists())
        check("v2 local format", manifest["format"] == "localscribe-project" and manifest["format_version"] == 2)
        check("identity, version, timestamp", manifest["slug"] == slug
              and manifest["title"] == "Synthetic study" and manifest["app_version"] == config.app_version()
              and manifest["exported"] == CREATED)
        check("sensitivity preserved", manifest["data_sensitivity"] == "may_contain_phi")
        provenance = manifest["documents"][0]["provenance"]["transcript"]
        check("model and actual settings provenance",
              provenance["model"] == "synthetic-model" and provenance["engine"]["beam_size"] == 5
              and provenance["language"] == "en" and provenance["schema"] == transcript.SCHEMA_VERSION)
        paths = [item["path"] for item in manifest["artifacts"]]
        check("inventory sorted", paths == sorted(paths))
        check("full includes media and preview", any(p.startswith("media/") for p in paths)
              and f"documents/{doc_id}/preview.m4a" in paths)
        check("waveform cache excluded", not any("waveform" in p for p in paths))
        check("transcript, revision, and output included",
              f"documents/{doc_id}/transcript.json" in paths
              and f"documents/{doc_id}/revisions/20260101-000000-001.json" in paths
              and f"documents/{doc_id}/outputs/transcript.txt" in paths)
        with zipfile.ZipFile(full) as archive:
            check("every artifact size and checksum matches", all(
                item["size_bytes"] == len(archive.read(item["path"]))
                and item["sha256"] == hashlib.sha256(archive.read(item["path"])).hexdigest()
                for item in manifest["artifacts"]
            ))
        only = exported(root, slug, False)
        only_manifest = snapshots.validate_snapshot(only)
        only_paths = [item["path"] for item in only_manifest["artifacts"]]
        check("transcript-only excludes source and derived audio",
              not only_manifest["includes_media"] and not any(
                  p.startswith("media/") or p.endswith("preview.m4a") for p in only_paths))
        check("transcript-only keeps provenance", only_manifest["documents"] == manifest["documents"])
        imported = projects.import_project(full)
        check("full import still works", projects.media_file(imported["slug"], doc_id).read_bytes() == b"synthetic media")
        imported_only = projects.import_project(only)
        check("transcript-only import still works", projects.load_transcript(imported_only["slug"], doc_id) is not None
              and not list(projects.media_dir(imported_only["slug"]).iterdir()))


def test_exclusion_and_no_sensitive_logging():
    with fixture() as (root, slug, doc_id):
        project = projects.project_dir(slug)
        document = projects.document_dir(slug, doc_id)
        for name in ("application.log", "localscribe.pid", "project.json.tmp", "credentials.json",
                     ".env", ".venv/lib/runtime.py", "tmp/secret.txt"):
            path = project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Synthetic excluded data", encoding="utf-8")
        for name in ("application.log", "credentials.json", "transcript.txt.tmp"):
            (document / "outputs" / name).write_text("Synthetic excluded data", encoding="utf-8")
        for name in ("credentials.json", "secrets.json", "20260101-000000-001.json.tmp"):
            (document / "revisions" / name).write_text("Synthetic excluded data", encoding="utf-8")
        orphan = project / "media" / "orphan.wav"
        orphan.write_bytes(b"orphan media")
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger()
        logger.addHandler(handler)
        try:
            with redirect_stdout(stream), redirect_stderr(stream):
                archive = exported(root, slug)
                manifest = snapshots.validate_snapshot(archive)
                bad = rewrite(archive, root / "bad.lsproj", extras={"credentials.json": b"synthetic"})
                try:
                    snapshots.validate_snapshot(bad)
                except snapshots.SnapshotError as exc:
                    logger.warning(str(exc))
        finally:
            logger.removeHandler(handler)
        paths = [a["path"] for a in manifest["artifacts"]]
        check("allowlist excludes logs, PID, environments, temporary files, credentials and orphan media",
              not any(p.endswith((".log", ".pid", ".tmp")) or "credentials" in p
                      or ".venv" in p or "orphan" in p or "/tmp/" in p for p in paths))
        check("sensitive classification is metadata, not logged",
              manifest["data_sensitivity"] == "may_contain_phi"
              and not any(value in stream.getvalue() for value in
                          ("Synthetic private text", "Synthetic study", "synthetic.wav", "may_contain_phi")))
        legacy = projects.read_json(project / "project.json")
        del legacy["data_sensitivity"]
        projects.write_json(project / "project.json", legacy)
        before = (project / "project.json").read_bytes()
        manifest = snapshots.validate_snapshot(exported(root, slug, False))
        check("legacy classification defaults without rewriting source",
              manifest["data_sensitivity"] == "unknown_treat_as_phi"
              and (project / "project.json").read_bytes() == before)


def test_tampering_and_invalid_schema():
    with fixture() as (root, slug, doc_id):
        source = exported(root, slug)
        name = f"documents/{doc_id}/outputs/transcript.txt"
        bad = root / "bad.lsproj"
        original = projects.project_dir(slug) / "project.json"
        before = original.read_bytes()
        def tamper(path, data):
            return b"X" * len(data) if path == name else data
        rewrite(source, bad, tamper)
        rejects("same-size tampered content rejected", lambda: snapshots.validate_snapshot(bad))
        rejects("tampered replace rejected before deletion",
                lambda: projects.import_project(bad, mode="replace"), projects.ProjectError)
        check("failed validation leaves existing project intact", original.read_bytes() == before)
        rewrite(source, bad, remove=name)
        rejects("missing artifact rejected", lambda: snapshots.validate_snapshot(bad))
        for label, change in (
            ("malformed checksum", lambda m: m["artifacts"][0].update(sha256="not-a-checksum")),
            ("wrong checksum", lambda m: m["artifacts"][0].update(sha256="0" * 64)),
            ("wrong size", lambda m: m["artifacts"][0].update(size_bytes=1)),
            ("negative size", lambda m: m["artifacts"][0].update(size_bytes=-1)),
            ("boolean size", lambda m: m["artifacts"][0].update(size_bytes=True)),
            ("unknown version", lambda m: m.update(format_version=99)),
            ("boolean version", lambda m: m.update(format_version=True)),
            ("wrong format", lambda m: m.update(format="other")),
            ("missing inventory", lambda m: m.pop("artifacts")),
            ("missing provenance", lambda m: m["documents"][0].pop("provenance")),
            ("malformed provenance", lambda m: m["documents"][0].update(provenance={})),
            ("non-object manifest", lambda m: None),
            ("unrecognized sensitivity", lambda m: m.update(data_sensitivity="ordinary")),
            ("missing timestamp", lambda m: m.pop("exported")),
            ("naive timestamp", lambda m: m.update(exported="2026-01-01T00:00:00")),
            ("unsorted inventory", lambda m: m["artifacts"].reverse()),
            ("duplicate inventory", lambda m: m["artifacts"].append(m["artifacts"][0])),
        ):
            if label == "non-object manifest":
                rewrite(source, bad, lambda p, data: b"[]" if p == snapshots.MANIFEST_FILE else data)
            else:
                rewrite(source, bad, change_manifest(change))
            rejects(f"{label} rejected", lambda: snapshots.validate_snapshot(bad))
        for data in (b"not json", b"\xff"):
            rewrite(source, bad, lambda p, content: data if p == snapshots.MANIFEST_FILE else content)
            rejects("invalid manifest encoding/JSON rejected", lambda: snapshots.validate_snapshot(bad))
        rewrite(source, bad, extras={"unexpected.txt": b"extra"})
        rejects("unexpected archive file rejected", lambda: snapshots.validate_snapshot(bad))
        before_files = sorted(root.rglob("*"))
        snapshots.validate_snapshot(source)
        check("validation creates no files", before_files == sorted(root.rglob("*")))


def test_unsafe_archive_paths():
    with fixture() as (root, slug, doc_id):
        source = exported(root, slug)
        bad = root / "bad.lsproj"
        for name in ("../escape.txt", "/absolute.txt", "C:/drive.txt", r"..\escape.txt",
                     "documents//file", "./file", "trailing.", "NUL.txt", "documents/CON/file"):
            rewrite(source, bad, extras={name: b"unsafe"})
            rejects("unsafe path rejected", lambda: snapshots.validate_snapshot(bad))
            rejects("unsafe import rejected", lambda: projects.import_project(bad), projects.ProjectError)
        rewrite(source, bad)
        with zipfile.ZipFile(bad, "a") as archive:
            link = zipfile.ZipInfo("link")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, "../synthetic")
        rejects("archive symlink rejected", lambda: snapshots.validate_snapshot(bad))
        rewrite(source, bad, extras={"PROJECT.JSON": b"ambiguous"})
        rejects("case-insensitive path collision rejected", lambda: snapshots.validate_snapshot(bad))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            rewrite(source, bad, extras={"project.json": b"duplicate"})
        rejects("duplicate archive member rejected", lambda: snapshots.validate_snapshot(bad))
        check("nothing escaped extraction", not (root / "escape.txt").exists())


def test_atomic_failure_and_source_links():
    with fixture() as (root, slug, doc_id):
        existing = exported(root, slug)
        before = existing.read_bytes()
        with patch.object(snapshots, "validate_snapshot", side_effect=snapshots.SnapshotError("Synthetic failure")):
            rejects("failed snapshot creation reported", lambda: exported(root, slug), projects.ProjectError)
        check("failure publishes no partial archive", list((root / "archives").iterdir()) == [existing])
        check("prior archive unchanged", existing.read_bytes() == before)
        with patch.object(snapshots.os, "replace", side_effect=OSError("Synthetic failure")):
            rejects("failed atomic rename reported", lambda: exported(root, slug), OSError)
        check("rename failure cleaned temporary archive", list((root / "archives").iterdir()) == [existing])
        document = projects.document_dir(slug, doc_id)
        preview = document / "preview.m4a"
        preview.unlink()
        preview.symlink_to(root / "outside.m4a")
        (root / "outside.m4a").write_bytes(b"synthetic outside content")
        rejects("selected source symlink rejected", lambda: exported(root, slug), projects.ProjectError)
        check("transcript-only never follows preview link",
              snapshots.validate_snapshot(exported(root, slug, False))["includes_media"] is False)


def test_legacy_v1_compatibility():
    with fixture() as (root, slug, doc_id):
        legacy = root / "legacy.lsproj"
        project = projects.project_dir(slug)
        with zipfile.ZipFile(legacy, "w") as archive:
            archive.writestr(snapshots.MANIFEST_FILE, json.dumps({
                "format": "localscribe-project", "format_version": 1,
                "slug": slug, "title": "Synthetic legacy", "includes_media": True,
            }))
            archive.writestr("documents/", b"")
            for path in sorted(project.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(project).as_posix())
        check("v1 inspect remains available", projects.inspect_archive(legacy)["format_version"] == 1)
        rejects("v1 is never presented as checksum verified", lambda: snapshots.validate_snapshot(legacy))
        imported = projects.import_project(legacy)
        check("v1 imports without checksums", imported["slug"] != slug
              and projects.load_transcript(imported["slug"], doc_id)["model"] == "synthetic-model")
        check("v1 media restored", projects.media_file(imported["slug"], doc_id).read_bytes() == b"synthetic media")


def test_archive_endpoints_do_not_log_sensitive_content():
    import asyncio
    from fastapi import UploadFile
    from app import update_check

    with fixture() as (root, slug, doc_id), patch.object(
        update_check, "refresh_state_async"
    ), patch.object(config, "install_offline_guard"):
        from app import main as web

        # No other API behavior is exercised: only archive export/import logging.
        with patch.object(web, "PATHS", projects.PATHS), patch.object(web.CONSOLE, "success") as log:
            projects.PATHS.logs.mkdir(parents=True, exist_ok=True)

            async def exercise():
                response = await web.api_export_project(slug, include_media=False)
                payload = Path(response.path).read_bytes()
                uploaded = UploadFile(
                    filename="../../Synthetic sensitive filename.lsproj", file=io.BytesIO(payload),
                )
                return await web.api_import_project(uploaded, mode="rename")

            imported = asyncio.run(exercise())
            messages = repr(log.call_args_list)
            check("archive endpoints log no title, filename, slug, transcript, or sensitivity",
                  log.call_count == 2 and not any(value in messages for value in (
                      "Synthetic", slug, "private text", "may_contain_phi", "filename",
                  )))
            check("endpoint import restores transcript",
                  projects.load_transcript(imported["project"]["slug"], doc_id) is not None)
            check("endpoint staging ignores unsafe uploaded name and is removed",
                  not list(projects.PATHS.logs.glob("import-*"))
                  and not (root / "Synthetic sensitive filename.lsproj").exists())


def main():
    for test in (
        test_deterministic_full_and_transcript_only, test_exclusion_and_no_sensitive_logging,
        test_tampering_and_invalid_schema, test_unsafe_archive_paths,
        test_atomic_failure_and_source_links, test_legacy_v1_compatibility,
        test_archive_endpoints_do_not_log_sensitive_content,
    ):
        print(f"\n{test.__name__}")
        test()
    print(f"\n{len(FAILURES)} failures")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
