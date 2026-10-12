"""Filesystem-backed project store.

There is no database. A project is a directory of plain JSON and media files,
which means a researcher can inspect it, copy it to an encrypted drive, hand it
to a colleague, or recover a transcript with a text editor if this application
ever stops working. Import and export are therefore just a zip archive.

Layout::

    projects/<slug>/
      project.json
      media/<doc_id>__<original name>
      documents/<doc_id>/
        document.json          source facts, status, engine settings, stats
        transcript.json         canonical transcript (see transcript.py)
        preview.m4a             browser-playable audio companion
        waveform.json           cached envelope for the editor's time ribbon
        revisions/<stamp>.json  autosave history
        outputs/                transcript.txt/.md/.docx/.vtt/.srt/.json
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import unicodedata
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .config import PATHS, app_version
from . import snapshots
from .sensitivity import DEFAULT_SENSITIVITY, future_backup_gate, normalize_sensitivity, validate_sensitivity
from .transcript import summary as transcript_summary

PROJECT_FILE = "project.json"
DOCUMENT_FILE = "document.json"
TRANSCRIPT_FILE = "transcript.json"
MANIFEST_FILE = "localscribe-manifest.json"
EXPORT_SUFFIX = ".lsproj"

# Editable project metadata. Anything not in here cannot be set by the client.
EDITABLE_FIELDS = (
    "title",
    "description",
    "principal_investigator",
    "irb_protocol",
    "participant_scheme",
    "consent_notes",
    "glossary",
    "tags",
    "data_sensitivity",
)

_LOCK = threading.RLock()
_SLUG_CLEAN = re.compile(r"[^a-z0-9]+")


class ProjectError(Exception):
    """A project operation failed for a reason worth showing the user."""


class ProjectValidationError(ProjectError):
    """Incoming project metadata is invalid."""


def _validate_sensitivity(value) -> str:
    try:
        return validate_sensitivity(value)
    except ValueError as exc:
        raise ProjectValidationError(str(exc)) from exc


def _normalize_project(record: dict) -> dict:
    record["data_sensitivity"] = normalize_sensitivity(record.get("data_sensitivity"))
    return record


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]


def slugify(text: str, fallback: str = "project") -> str:
    normalised = unicodedata.normalize("NFKD", str(text or ""))
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii").lower()
    slug = _SLUG_CLEAN.sub("-", ascii_only).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return (slug or fallback)[:60]


def safe_filename(name: str) -> str:
    """Strip any path component and characters Windows refuses."""
    base = Path(str(name or "")).name
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base).strip(" .")
    return base[:150] or "file"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def project_dir(slug: str) -> Path:
    clean = slugify(slug)
    if not clean:
        raise ProjectError("Invalid project identifier.")
    path = (PATHS.projects / clean).resolve()
    # Refuse anything that escapes the projects root.
    if not path.is_relative_to(PATHS.projects.resolve()):
        raise ProjectError("Invalid project path.")
    return path


def document_dir(slug: str, doc_id: str) -> Path:
    clean_id = re.sub(r"[^A-Za-z0-9_-]", "", str(doc_id or ""))
    if not clean_id:
        raise ProjectError("Invalid document identifier.")
    return project_dir(slug) / "documents" / clean_id


def media_dir(slug: str) -> Path:
    return project_dir(slug) / "media"


def outputs_dir(slug: str, doc_id: str) -> Path:
    return document_dir(slug, doc_id) / "outputs"


# ---------------------------------------------------------------------------
# Read / write helpers
# ---------------------------------------------------------------------------

def read_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def new_project_record(title: str, **fields) -> dict:
    record = {
        "slug": slugify(title),
        "title": (title or "Untitled project").strip(),
        "description": "",
        "principal_investigator": "",
        "irb_protocol": "",
        "participant_scheme": "",
        "consent_notes": "",
        "glossary": "",
        "tags": [],
        "data_sensitivity": DEFAULT_SENSITIVITY,
        "created": _now(),
        "updated": _now(),
        "app_version": app_version(),
    }
    for key in EDITABLE_FIELDS:
        if key == "data_sensitivity" and key in fields:
            record[key] = _validate_sensitivity(fields[key])
            continue
        if key in fields and fields[key] is not None:
            record[key] = fields[key]
    return record


def create_project(title: str, **fields) -> dict:
    with _LOCK:
        base = slugify(title)
        slug = base
        counter = 2
        while (PATHS.projects / slug).exists():
            slug = f"{base}-{counter}"
            counter += 1

        record = new_project_record(title, **fields)
        record["slug"] = slug

        root = project_dir(slug)
        (root / "media").mkdir(parents=True, exist_ok=True)
        (root / "documents").mkdir(parents=True, exist_ok=True)
        write_json(root / PROJECT_FILE, record)
        return record


def load_project(slug: str) -> dict:
    root = project_dir(slug)
    record = read_json(root / PROJECT_FILE)
    if record is None:
        raise ProjectError(f"Project '{slug}' was not found.")
    record["slug"] = root.name
    return _normalize_project(record)


def save_project(slug: str, updates: dict) -> dict:
    with _LOCK:
        record = load_project(slug)
        for key in EDITABLE_FIELDS:
            if key not in updates:
                continue
            value = updates[key]
            if key == "data_sensitivity":
                value = _validate_sensitivity(value)
            elif key == "tags":
                if isinstance(value, str):
                    value = [t.strip() for t in value.split(",")]
                value = [str(t).strip() for t in (value or []) if str(t).strip()]
            else:
                value = str(value if value is not None else "").strip()
            record[key] = value
        record["updated"] = _now()
        write_json(project_dir(slug) / PROJECT_FILE, record)
        return record


def record_box_health_override(
    slug: str, destination_root: Path, *, independently_verified_box_health: bool = False
) -> dict:
    """Record only the latest explicit attestation, not a reusable permission."""
    with _LOCK:
        record = load_project(slug)
        destination_root = Path(destination_root)
        result = future_backup_gate(
            record["data_sensitivity"], destination_root.name,
            independently_verified_box_health=independently_verified_box_health,
        )
        if not result.override_used or not destination_root.is_absolute():
            raise ProjectValidationError(
                "An override requires explicit independent Box Health verification "
                "for a PHI/unknown project and an absolute destination folder path."
            )
        record["box_health_override"] = {
            "confirmed_at": _now(),
            "destination_root": str(destination_root),
            "independently_verified_box_health": True,
        }
        record["updated"] = _now()
        write_json(project_dir(slug) / PROJECT_FILE, record)
        return record


def delete_project(slug: str) -> None:
    with _LOCK:
        root = project_dir(slug)
        if not root.exists():
            raise ProjectError(f"Project '{slug}' was not found.")
        try:
            shutil.rmtree(root)
        except OSError as exc:
            raise ProjectError("The project could not be removed.") from exc


def list_projects() -> list:
    PATHS.projects.mkdir(parents=True, exist_ok=True)
    out = []
    for entry in sorted(PATHS.projects.iterdir()):
        if not entry.is_dir():
            continue
        record = read_json(entry / PROJECT_FILE)
        if record is None:
            continue
        record["slug"] = entry.name
        _normalize_project(record)
        record["stats"] = project_stats(entry.name)
        out.append(record)
    out.sort(key=lambda r: r.get("updated") or "", reverse=True)
    return out


def project_stats(slug: str) -> dict:
    docs = list_documents(slug)
    statuses: dict = {}
    words = 0
    duration = 0.0
    for doc in docs:
        statuses[doc["status"]] = statuses.get(doc["status"], 0) + 1
        words += int(doc.get("words") or 0)
        duration += float(doc.get("duration") or 0.0)
    return {
        "documents": len(docs),
        "statuses": statuses,
        "words": words,
        "duration": round(duration, 1),
        "pending": sum(
            1 for d in docs if d["status"] in ("uploaded", "failed", "cancelled")
        ),
        "reviewed": sum(1 for d in docs if d.get("human_edited")),
    }


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

def new_document_id() -> str:
    return uuid.uuid4().hex[:12]


def add_document(slug: str, filename: str, data: bytes | None = None, source_path: Path | None = None) -> dict:
    """Register an uploaded file. Media is stored verbatim and never modified."""
    with _LOCK:
        load_project(slug)  # existence check
        doc_id = new_document_id()
        clean = safe_filename(filename)

        media = media_dir(slug)
        media.mkdir(parents=True, exist_ok=True)
        stored = media / f"{doc_id}__{clean}"

        if data is not None:
            stored.write_bytes(data)
        elif source_path is not None:
            shutil.copy2(source_path, stored)
        else:
            raise ProjectError("No file content was provided.")

        record = {
            "id": doc_id,
            "filename": clean,
            "media_path": str(stored.relative_to(project_dir(slug))).replace("\\", "/"),
            "size_bytes": stored.stat().st_size,
            "status": "uploaded",
            "status_detail": "Waiting to be transcribed",
            "created": _now(),
            "updated": _now(),
            "duration": None,
            "media": {},
            "engine": {},
            "stats": {},
            "words": 0,
            "segments": 0,
            "human_edited": False,
            "preview": None,
            "error": None,
        }

        target = document_dir(slug, doc_id)
        (target / "outputs").mkdir(parents=True, exist_ok=True)
        (target / "revisions").mkdir(parents=True, exist_ok=True)
        write_json(target / DOCUMENT_FILE, record)
        touch_project(slug)
        return record


def load_document(slug: str, doc_id: str) -> dict:
    record = read_json(document_dir(slug, doc_id) / DOCUMENT_FILE)
    if record is None:
        raise ProjectError(f"Document '{doc_id}' was not found.")
    record["id"] = record.get("id") or doc_id
    return record


def save_document(slug: str, doc_id: str, record: dict) -> dict:
    record["updated"] = _now()
    write_json(document_dir(slug, doc_id) / DOCUMENT_FILE, record)
    return record


def update_document(slug: str, doc_id: str, **changes) -> dict:
    with _LOCK:
        record = load_document(slug, doc_id)
        record.update(changes)
        return save_document(slug, doc_id, record)


def set_status(slug: str, doc_id: str, status: str, detail: str = "", error: str | None = None) -> dict:
    return update_document(
        slug, doc_id, status=status, status_detail=detail, error=error
    )


def list_documents(slug: str) -> list:
    root = project_dir(slug) / "documents"
    if not root.is_dir():
        return []
    out = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        record = read_json(entry / DOCUMENT_FILE)
        if record is None:
            continue
        record["id"] = record.get("id") or entry.name
        record["has_transcript"] = (entry / TRANSCRIPT_FILE).exists()
        out.append(record)
    out.sort(key=lambda r: r.get("created") or "")
    return out


def media_file(slug: str, doc_id: str) -> Path:
    record = load_document(slug, doc_id)
    rel = record.get("media_path") or ""
    path = (project_dir(slug) / rel).resolve()
    if not str(path).startswith(str(project_dir(slug).resolve())):
        raise ProjectError("Invalid media path.")
    if not path.exists():
        raise ProjectError(f"The media file for '{record.get('filename')}' is missing.")
    return path


def delete_document(slug: str, doc_id: str) -> None:
    with _LOCK:
        record = load_document(slug, doc_id)
        rel = record.get("media_path")
        if rel:
            media = project_dir(slug) / rel
            if media.exists():
                media.unlink(missing_ok=True)
        shutil.rmtree(document_dir(slug, doc_id), ignore_errors=True)
        touch_project(slug)


def touch_project(slug: str) -> None:
    root = project_dir(slug)
    record = read_json(root / PROJECT_FILE)
    if record is not None:
        _normalize_project(record)
        record["updated"] = _now()
        write_json(root / PROJECT_FILE, record)


# ---------------------------------------------------------------------------
# Transcripts
# ---------------------------------------------------------------------------

def transcript_path(slug: str, doc_id: str) -> Path:
    return document_dir(slug, doc_id) / TRANSCRIPT_FILE


def load_transcript(slug: str, doc_id: str) -> dict | None:
    return read_json(transcript_path(slug, doc_id))


def save_transcript(slug: str, doc_id: str, doc: dict, revision: bool = True, keep: int = 20) -> dict:
    """Persist the transcript, optionally snapshotting the previous version."""
    with _LOCK:
        path = transcript_path(slug, doc_id)
        if revision and path.exists() and keep > 0:
            previous = read_json(path)
            if previous is not None:
                revisions = document_dir(slug, doc_id) / "revisions"
                revisions.mkdir(parents=True, exist_ok=True)
                write_json(revisions / f"{_stamp()}.json", previous)
                prune_revisions(slug, doc_id, keep)

        write_json(path, doc)

        info = transcript_summary(doc)
        update_document(
            slug, doc_id,
            words=info["words"],
            segments=info["segments"],
            duration=info["duration"] or None,
            human_edited=info["human_edited"],
            retimestamped_at=info["retimestamped_at"],
            low_confidence=info["low_confidence"],
            speakers=info["speakers"],
        )
        touch_project(slug)
        return doc


def prune_revisions(slug: str, doc_id: str, keep: int) -> None:
    revisions = document_dir(slug, doc_id) / "revisions"
    if not revisions.is_dir():
        return
    files = sorted(revisions.glob("*.json"))
    for stale in files[:-keep] if keep > 0 else files:
        stale.unlink(missing_ok=True)


def list_revisions(slug: str, doc_id: str) -> list:
    revisions = document_dir(slug, doc_id) / "revisions"
    if not revisions.is_dir():
        return []
    out = []
    for path in sorted(revisions.glob("*.json"), reverse=True):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        out.append({"id": path.stem, "size_bytes": size})
    return out


def load_revision(slug: str, doc_id: str, revision_id: str) -> dict | None:
    clean = re.sub(r"[^0-9A-Za-z_-]", "", str(revision_id or ""))
    if not clean:
        return None
    return read_json(document_dir(slug, doc_id) / "revisions" / f"{clean}.json")


def list_outputs(slug: str, doc_id: str) -> list:
    out_dir = outputs_dir(slug, doc_id)
    if not out_dir.is_dir():
        return []
    files = []
    for path in sorted(out_dir.iterdir()):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        files.append({
            "name": path.name,
            "format": path.suffix.lstrip("."),
            "size_bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        })
    return files


# ---------------------------------------------------------------------------
# Import / export
# ---------------------------------------------------------------------------

def export_project(slug: str, dest_dir: Path | None = None, include_media: bool = True) -> Path:
    """Write an atomic, checksummed v2 .lsproj snapshot."""
    with _LOCK:
        record = load_project(slug)
        source = PATHS.projects / record["slug"]
        if source.is_symlink():
            raise ProjectError("Snapshot source must not contain symbolic links.")
        try:
            return snapshots.write_snapshot(
                source, Path(dest_dir or PATHS.logs), record,
                app_version=app_version(), created_at=_now(),
                include_media=bool(include_media),
            )
        except snapshots.SnapshotError as exc:
            raise ProjectError(str(exc)) from exc


def snapshot_root_dir() -> Path:
    root = PATHS.projects / ".snapshots"
    if root.is_symlink():
        raise ProjectError("Snapshot location is not safe.")
    return root


def local_snapshot_dir(slug: str) -> Path:
    """Return a hidden, app-managed location that survives project deletion."""
    directory = snapshot_root_dir() / slugify(slug)
    if directory.is_symlink():
        raise ProjectError("Snapshot location is not safe.")
    return directory


def create_local_snapshot(slug: str, include_media: bool = True) -> Path:
    try:
        return export_project(slug, local_snapshot_dir(slug), include_media=include_media)
    except OSError as exc:
        raise ProjectError("Snapshot could not be created.") from exc


def get_local_snapshot(slug: str, filename: str) -> Path:
    if (
        not isinstance(filename, str)
        or Path(filename).name != filename
        or not filename.endswith(EXPORT_SUFFIX)
    ):
        raise ProjectError("Snapshot not found.")
    directory = local_snapshot_dir(slug)
    path = directory / filename
    if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
        raise ProjectError("Snapshot not found.")
    return path


def inspect_archive(archive_path: Path) -> dict:
    """Read an archive's manifest without extracting anything."""
    try:
        with zipfile.ZipFile(archive_path) as archive:
            manifest = snapshots.read_manifest(archive)
            if manifest["format_version"] == snapshots.FORMAT_VERSION:
                snapshots.validate_snapshot(archive)
    except (zipfile.BadZipFile, snapshots.SnapshotError) as exc:
        raise ProjectError("That file is not a readable archive.") from exc

    if manifest.get("format") != "localscribe-project":
        raise ProjectError("That archive was not produced by Local Scribe.")
    return manifest


def import_project(
    archive_path: Path, mode: str = "rename", *, snapshot_before: bool = False,
) -> dict:
    """Extract a .lsproj archive into projects/.

    ``mode`` is 'rename' (default, keeps both copies) or 'replace'.
    """
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ProjectError("That file is not a readable archive.") from exc
    with archive:
        return _import_archive(archive, archive_path, mode, snapshot_before=snapshot_before)


def _import_archive(
    archive: zipfile.ZipFile, archive_path: Path, mode: str, *, snapshot_before: bool = False,
) -> dict:
    try:
        manifest = snapshots.read_manifest(archive)
        if manifest["format_version"] == snapshots.FORMAT_VERSION:
            snapshots.validate_snapshot(archive)
        record = snapshots.read_project_metadata(archive)
    except snapshots.SnapshotError as exc:
        raise ProjectError(str(exc)) from exc
    incoming = slugify(manifest.get("slug") or manifest.get("title") or "imported")

    with _LOCK:
        if mode not in {"prompt", "rename", "replace"}:
            raise ProjectError("Choose rename or replace for this import.")
        slug = incoming
        if (PATHS.projects / slug).exists():
            if mode == "prompt":
                existing = read_json(PATHS.projects / slug / PROJECT_FILE, {})
                if not isinstance(existing, dict):
                    existing = {}
                return {
                    "conflict": True,
                    "slug": slug,
                    "incoming_title": record.get("title") or manifest.get("title") or slug,
                    "existing_title": existing.get("title") or slug,
                }
            if mode == "replace":
                if snapshot_before:
                    create_local_snapshot(slug)
                try:
                    shutil.rmtree(PATHS.projects / slug)
                except OSError as exc:
                    raise ProjectError("The existing project could not be replaced.") from exc
            else:
                counter = 2
                while (PATHS.projects / f"{incoming}-{counter}").exists():
                    counter += 1
                slug = f"{incoming}-{counter}"

        target = project_dir(slug)
        target.mkdir(parents=True, exist_ok=True)

        for name in archive.namelist():
            if name == MANIFEST_FILE:
                continue
            # Paths were checked before any existing project could be replaced.
            relative = Path(name)
            destination = (target / relative).resolve()
            if not destination.is_relative_to(target.resolve()):
                raise ProjectError("Archive contains an unsafe destination.")
            if name.endswith("/"):
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as src, open(destination, "wb") as dst:
                shutil.copyfileobj(src, dst)

        record["slug"] = slug
        _normalize_project(record)
        if slug != incoming:
            record["title"] = f"{record.get('title') or slug} (imported)"
        record["updated"] = _now()
        write_json(target / PROJECT_FILE, record)

        for directory in ("media", "documents"):
            (target / directory).mkdir(parents=True, exist_ok=True)

        record["stats"] = project_stats(slug)
        record["imported_from"] = Path(archive_path).name
        return record


def reveal(path: Path) -> bool:
    """Open a folder in the platform file manager. Best effort."""
    import subprocess
    import sys

    target = Path(path)
    if not target.exists():
        return False
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(target))  # noqa: S606 - documented Windows API
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
        return True
    except Exception:
        return False
