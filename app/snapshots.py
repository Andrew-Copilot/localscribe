"""Local .lsproj v2 snapshots. No transport, credentials, or logging."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from .sensitivity import SENSITIVITY_LABELS, normalize_sensitivity

MANIFEST_FILE = "localscribe-manifest.json"
FORMAT = "localscribe-project"
FORMAT_VERSION = 2
_ID = re.compile(r"[A-Za-z0-9_-]+")
_CHECKSUM = re.compile(r"[0-9a-f]{64}")
_OUTPUTS = {f"transcript.{ext}" for ext in ("txt", "md", "docx", "vtt", "srt", "json")}
_DEVICE = re.compile(r"(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.IGNORECASE)


class SnapshotError(ValueError):
    """Invalid snapshot; messages deliberately contain no project content."""


def safe_archive_path(name: str) -> bool:
    """Accept only canonical, portable relative paths."""
    return (
        isinstance(name, str) and bool(name)
        and not any(c in name for c in '\\:<>"|?*')
        and not any(ord(c) < 32 for c in name)
        and all(p and p not in (".", "..") and not p.endswith((" ", "."))
                and not _DEVICE.match(p)
                for p in name.split("/"))
    )


def _artifact_allowed(name: str, include_media: bool) -> bool:
    if not safe_archive_path(name):
        return False
    parts = name.split("/")
    if name == "project.json":
        return True
    if len(parts) == 2 and parts[0] == "media" and include_media:
        filename = parts[1].split("__", 1)[-1].lower()
        return (
            not filename.startswith(".")
            and not any(word in filename for word in ("credential", "secret", "token", "password"))
            and Path(filename).suffix not in {
                ".log", ".pid", ".tmp", ".temp", ".bak", ".py", ".pyc", ".env", ".pem", ".key",
            }
        )
    if len(parts) < 3 or parts[0] != "documents" or not _ID.fullmatch(parts[1]):
        return False
    if len(parts) == 3:
        return parts[2] in {"document.json", "transcript.json"} or (
            include_media and parts[2] == "preview.m4a"
        )
    if len(parts) == 4:
        return (
            parts[2] == "outputs" and parts[3] in _OUTPUTS
        ) or (
            parts[2] == "revisions" and bool(re.fullmatch(r"\d{8}-\d{6}-\d{3}\.json", parts[3]))
        )
    return False


def check_archive_paths(archive: zipfile.ZipFile) -> None:
    """Reject traversal, ambiguous names, duplicates, and special files."""
    seen = set()
    portable = set()
    for info in archive.infolist():
        name = info.filename[:-1] if info.is_dir() else info.filename
        mode = stat.S_IFMT(info.external_attr >> 16)
        if (
            not safe_archive_path(name) or name in seen
            or name.casefold() in portable
            or mode not in (0, stat.S_IFREG, stat.S_IFDIR)
        ):
            raise SnapshotError("Archive contains unsafe or duplicate paths.")
        seen.add(name)
        portable.add(name.casefold())


def _json(data: bytes):
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise SnapshotError("Snapshot metadata is not valid JSON.") from exc


def read_manifest(archive: zipfile.ZipFile) -> dict:
    check_archive_paths(archive)
    try:
        manifest = _json(archive.read(MANIFEST_FILE))
    except KeyError as exc:
        raise SnapshotError("Local Scribe manifest is missing.") from exc
    if (
        not isinstance(manifest, dict) or manifest.get("format") != FORMAT
        or type(manifest.get("format_version")) is not int
        or manifest["format_version"] not in (1, FORMAT_VERSION)
    ):
        raise SnapshotError("Unsupported Local Scribe archive format or version.")
    return manifest


def read_project_metadata(archive: zipfile.ZipFile) -> dict:
    """Require usable project JSON before any import can replace local data."""
    try:
        record = _json(archive.read("project.json"))
    except KeyError as exc:
        raise SnapshotError("Snapshot project metadata is missing.") from exc
    if not isinstance(record, dict):
        raise SnapshotError("Snapshot project metadata must be a JSON object.")
    return record


def _validate(archive: zipfile.ZipFile) -> dict:
    manifest = read_manifest(archive)
    if manifest["format_version"] != FORMAT_VERSION:
        raise SnapshotError("Checksum validation requires a v2 snapshot.")
    if (
        any(not isinstance(manifest.get(k), str) for k in
            ("app_version", "exported", "slug", "title", "data_sensitivity"))
        or not manifest["app_version"] or not manifest["slug"]
        or manifest["data_sensitivity"] not in SENSITIVITY_LABELS
        or type(manifest.get("includes_media")) is not bool
        or not isinstance(manifest.get("documents"), list)
        or not isinstance(manifest.get("artifacts"), list)
    ):
        raise SnapshotError("Invalid snapshot manifest schema.")
    try:
        if datetime.fromisoformat(manifest["exported"]).tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise SnapshotError("Invalid snapshot creation timestamp.") from exc

    doc_ids = []
    for doc in manifest["documents"]:
        if (
            not isinstance(doc, dict) or not isinstance(doc.get("id"), str)
            or not _ID.fullmatch(doc["id"])
            or "filename" not in doc or "status" not in doc
            or any(doc[k] is not None and not isinstance(doc[k], str) for k in ("filename", "status"))
            or not isinstance(doc.get("provenance"), dict)
            or any(not isinstance(doc["provenance"].get(k), dict) for k in ("document", "transcript"))
        ):
            raise SnapshotError("Invalid snapshot document provenance.")
        doc_ids.append(doc["id"])
    if doc_ids != sorted(set(doc_ids)):
        raise SnapshotError("Snapshot document inventory must be unique and sorted.")

    paths = []
    for item in manifest["artifacts"]:
        if (
            not isinstance(item, dict) or not isinstance(item.get("path"), str)
            or not _artifact_allowed(item["path"], manifest["includes_media"])
            or type(item.get("size_bytes")) is not int or item["size_bytes"] < 0
            or not isinstance(item.get("sha256"), str)
            or not _CHECKSUM.fullmatch(item["sha256"])
        ):
            raise SnapshotError("Invalid snapshot artifact inventory.")
        paths.append(item["path"])
    if paths != sorted(set(paths)) or "project.json" not in paths:
        raise SnapshotError("Snapshot artifact inventory must be complete, unique, and sorted.")
    if any(f"documents/{doc_id}/document.json" not in paths for doc_id in doc_ids):
        raise SnapshotError("Snapshot document metadata is missing.")
    if any(p.startswith("documents/") and p.split("/")[1] not in doc_ids for p in paths):
        raise SnapshotError("Snapshot artifact has no declared document.")
    # v2 has no directory entries or unlisted extras: nothing is silently ignored.
    if set(archive.namelist()) != set(paths) | {MANIFEST_FILE}:
        raise SnapshotError("Snapshot contains missing or unexpected artifacts.")
    for item in manifest["artifacts"]:
        info = archive.getinfo(item["path"])
        if info.file_size != item["size_bytes"]:
            raise SnapshotError("Snapshot artifact byte size does not match.")
        digest = hashlib.sha256()
        size = 0
        with archive.open(info) as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
        if size != item["size_bytes"] or digest.hexdigest() != item["sha256"]:
            raise SnapshotError("Snapshot artifact checksum does not match.")
    read_project_metadata(archive)
    return manifest


def validate_snapshot(archive_path: Path | zipfile.ZipFile) -> dict:
    """Verify v2 without extracting, writing, logging, or changing project state.

    Return the manifest or raise SnapshotError. v1 is intentionally not verified.
    An already-open ZIP can be used so import validates the same file it extracts.
    """
    try:
        if isinstance(archive_path, zipfile.ZipFile):
            return _validate(archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            return _validate(archive)
    except (OSError, zipfile.BadZipFile, RuntimeError, EOFError, NotImplementedError) as exc:
        raise SnapshotError("Snapshot archive could not be verified.") from exc


def _regular_file(root: Path, name: str) -> Path:
    path = root
    for part in name.split("/"):
        path = path / part
        if path.is_symlink():
            raise SnapshotError("Snapshot source must not contain symbolic links.")
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise SnapshotError("Snapshot source artifact is missing or unsafe.")
    return path


def write_snapshot(
    root: Path, dest_dir: Path, record: dict, *, app_version: str,
    created_at: str, include_media: bool,
) -> Path:
    """Publish a unique archive by same-directory atomic rename after validation."""
    if root.is_symlink():
        raise SnapshotError("Snapshot source must not contain symbolic links.")
    names = {"project.json"}
    documents = root / "documents"
    if documents.is_symlink():
        raise SnapshotError("Snapshot source must not contain symbolic links.")
    if documents.exists():
        for directory in sorted(documents.iterdir()):
            if directory.is_symlink():
                raise SnapshotError("Snapshot source must not contain symbolic links.")
            if not directory.is_dir() or not _ID.fullmatch(directory.name):
                continue
            prefix = f"documents/{directory.name}"
            if (directory / "document.json").is_symlink():
                raise SnapshotError("Snapshot source must not contain symbolic links.")
            if not (directory / "document.json").exists():
                continue
            names.add(f"{prefix}/document.json")
            for filename in ("transcript.json", "preview.m4a"):
                name = f"{prefix}/{filename}"
                if _artifact_allowed(name, include_media):
                    if (directory / filename).is_symlink():
                        raise SnapshotError("Snapshot source must not contain symbolic links.")
                    if (directory / filename).exists():
                        names.add(name)
            for folder in ("outputs", "revisions"):
                parent = directory / folder
                if parent.is_symlink():
                    raise SnapshotError("Snapshot source must not contain symbolic links.")
                if parent.is_dir():
                    for path in parent.iterdir():
                        name = f"{prefix}/{folder}/{path.name}"
                        if _artifact_allowed(name, include_media):
                            names.add(name)

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{record['slug']}-{uuid.uuid4().hex}.lsproj"
    fd, temporary = tempfile.mkstemp(prefix=".localscribe-", suffix=".tmp", dir=dest_dir)
    temp = Path(temporary)
    manifest = {
        "format": FORMAT, "format_version": FORMAT_VERSION,
        "app_version": app_version, "exported": created_at,
        "slug": record["slug"], "title": record.get("title", ""),
        "data_sensitivity": normalize_sensitivity(record.get("data_sensitivity")),
        "includes_media": include_media, "documents": [], "artifacts": [],
    }
    try:
        with os.fdopen(fd, "w+b") as output:
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                metadata = {}
                # Read metadata once; provenance and selected media refer to archived bytes.
                for name in sorted(names):
                    if name.endswith(("/document.json", "/transcript.json")):
                        data = _regular_file(root, name).read_bytes()
                        value = _json(data)
                        if not isinstance(value, dict):
                            raise SnapshotError("Snapshot metadata must be a JSON object.")
                        metadata[name] = (data, value)
                for name, (_, document) in sorted(metadata.items()):
                    if not name.endswith("/document.json"):
                        continue
                    doc_id = name.split("/")[1]
                    transcript = metadata.get(f"documents/{doc_id}/transcript.json", (None, {}))[1]
                    manifest["documents"].append({
                        "id": doc_id, "filename": document.get("filename"),
                        "status": document.get("status"),
                        "provenance": {
                            "document": {k: document[k] for k in ("engine", "stats") if k in document},
                            "transcript": {k: transcript[k] for k in (
                                "schema", "model", "engine", "stats", "language",
                                "language_probability", "created", "updated", "human_edited",
                                "retimestamped_at",
                            ) if k in transcript},
                        },
                    })
                    if include_media:
                        media = document.get("media_path")
                        if not isinstance(media, str) or not _artifact_allowed(media, True) or not media.startswith("media/"):
                            raise SnapshotError("Snapshot source media reference is unsafe or missing.")
                        names.add(media)
                manifest["documents"].sort(key=lambda d: d["id"])
                for name in sorted(names):
                    path = _regular_file(root, name)
                    digest = hashlib.sha256()
                    size = 0
                    with archive.open(name, "w", force_zip64=True) as target:
                        if name in metadata:
                            data = metadata[name][0]
                            target.write(data)
                            digest.update(data)
                            size = len(data)
                        else:
                            with path.open("rb") as source:
                                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                                    target.write(chunk)
                                    digest.update(chunk)
                                    size += len(chunk)
                    manifest["artifacts"].append({
                        "path": name, "size_bytes": size, "sha256": digest.hexdigest(),
                    })
                archive.writestr(MANIFEST_FILE, json.dumps(
                    manifest, indent=2, sort_keys=True, ensure_ascii=False,
                ).encode("utf-8"))
            output.flush()
            os.fsync(output.fileno())
        validate_snapshot(temp)
        os.replace(temp, dest)
        return dest
    finally:
        temp.unlink(missing_ok=True)
