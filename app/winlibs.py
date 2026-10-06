"""Native library discovery on Windows.

CTranslate2 loads the CUDA math libraries (cuBLAS 12, cuDNN 9) lazily, by
name, the first time the model actually computes something on the GPU, not
when the model loads. On a clean Windows PC those DLLs exist nowhere on the
search path, so a model could load "successfully" on CUDA and then fail the
moment transcription started. Likewise onnxruntime (used by the voice
activity filter) needs the Visual C++ runtime, which a fresh Windows install
does not always have.

This module does two things:

* ``prepare()`` puts every directory that can hold those DLLs on the search
  path: the pip-installed ``nvidia-*`` wheels from "Install GPU support", a
  system CUDA toolkit, PyTorch's bundled copies, and the interpreter folder
  where the installer ships the Visual C++ runtime.
* ``probe()`` reports which of them can actually be loaded, so the hardware
  probe only calls CUDA usable when it really is.

Everything here is a no-op on macOS and Linux.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"

# What CTranslate2 4.5+ needs to run Whisper on an NVIDIA GPU.
CUDA_DLLS = (
    "cublas64_12.dll",
    "cublasLt64_12.dll",
    "cudnn64_9.dll",
    "cudnn_ops64_9.dll",
    "cudnn_cnn64_9.dll",
)

# The Visual C++ 2015-2022 runtime that the native wheels are built against.
VCRUNTIME_DLLS = (
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "msvcp140.dll",
    "msvcp140_1.dll",
)

_added: list[str] = []
_handles: list = []  # keep add_dll_directory handles alive


def _site_packages() -> list[Path]:
    roots: list[Path] = []
    try:
        import site

        roots.extend(Path(p) for p in site.getsitepackages())
    except Exception:
        pass
    roots.append(Path(sys.prefix) / "Lib" / "site-packages")
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        key = os.path.normcase(str(root))
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def candidate_dirs() -> list[Path]:
    """Every directory that may hold the DLLs above, existing or not."""
    dirs: list[Path] = []

    # nvidia-cublas-cu12 / nvidia-cudnn-cu12 wheels: site-packages/nvidia/*/bin
    for root in _site_packages():
        nvidia = root / "nvidia"
        if nvidia.is_dir():
            dirs.extend(sorted(p / "bin" for p in nvidia.iterdir() if p.is_dir()))

    # A system-wide CUDA toolkit (also covers CUDA_PATH_V12_x variants).
    for name, value in sorted(os.environ.items()):
        if name.upper().startswith("CUDA_PATH") and value:
            dirs.append(Path(value) / "bin")

    # PyTorch with CUDA ships cuBLAS and cuDNN in torch/lib.
    for root in _site_packages():
        dirs.append(root / "torch" / "lib")

    # The base interpreter folder, where the installer places the Visual C++
    # runtime app-locally (see packaging/windows/build.ps1).
    dirs.append(Path(sys.base_prefix))
    return dirs


def prepare() -> list[str]:
    """Add every existing candidate directory to the DLL search path.

    Both ``os.add_dll_directory`` (used for dependent DLLs of Python
    extension modules) and ``PATH`` (used by CTranslate2's own by-name
    ``LoadLibrary`` of cuBLAS/cuDNN) are updated. Safe to call repeatedly;
    returns the directories added by this call.
    """
    if not IS_WINDOWS:
        return []

    added: list[str] = []
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    known = {os.path.normcase(p) for p in path_parts if p}

    for directory in candidate_dirs():
        if not directory.is_dir():
            continue
        text = str(directory)
        key = os.path.normcase(text)
        if key in {os.path.normcase(a) for a in _added}:
            continue
        try:
            _handles.append(os.add_dll_directory(text))
        except (OSError, AttributeError):
            pass
        if key not in known:
            path_parts.insert(0, text)
            known.add(key)
        _added.append(text)
        added.append(text)

    os.environ["PATH"] = os.pathsep.join(p for p in path_parts if p)
    return added


def can_load(name: str) -> bool:
    """True when ``name`` loads with the current search path."""
    if not IS_WINDOWS:
        return False
    import ctypes

    try:
        ctypes.WinDLL(name)
        return True
    except OSError:
        return False


def probe(names=CUDA_DLLS + VCRUNTIME_DLLS) -> dict[str, bool]:
    """Map each DLL name to whether it can be loaded. Empty off Windows."""
    if not IS_WINDOWS:
        return {}
    return {name: can_load(name) for name in names}


def missing(names) -> list[str]:
    """The subset of ``names`` that cannot be loaded (empty off Windows)."""
    return [name for name, ok in probe(names).items() if not ok]


def search_dirs() -> list[str]:
    """Directories this module has added so far (for diagnostics)."""
    return list(_added)
