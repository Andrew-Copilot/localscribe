"""Allowlisted, local-only diagnostics that exclude user content and paths."""

from __future__ import annotations

import importlib.metadata
import platform
import sys

from .config import app_version

_DEPENDENCIES = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "faster_whisper": "faster-whisper",
    "av": "av",
    "python_docx": "python-docx",
    "huggingface_hub": "huggingface-hub",
}


def _version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def build_diagnostics(
    *, hardware: dict, offline_lock: bool, check_for_updates: bool,
) -> dict:
    gpus = hardware.get("gpus")
    return {
        "app_version": app_version(),
        "runtime": {
            "python": platform.python_version(),
            "os": platform.system(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
        },
        "hardware": {
            "cpu_cores": max(0, int(hardware.get("cpu_cores") or 0)),
            "gpu_count": len(gpus) if isinstance(gpus, list) else 0,
            "cuda_usable": bool(hardware.get("cuda_usable")),
            "apple_silicon": bool(hardware.get("apple_silicon")),
            "mlx_available": bool(hardware.get("mlx_available")),
        },
        "dependencies": {
            key: _version(distribution)
            for key, distribution in _DEPENDENCIES.items()
        },
        "privacy": {
            "offline_lock": bool(offline_lock),
            "update_checks_enabled": bool(check_for_updates),
            "local_snapshots_enabled": True,
            "remote_backup_configured": False,
        },
    }
