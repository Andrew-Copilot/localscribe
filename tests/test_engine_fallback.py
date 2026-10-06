"""Tests for the engine's CPU fallback when a CUDA library is missing.

CTranslate2 loads cuBLAS/cuDNN lazily, so on a PC without them the model
loads on CUDA and only fails once transcription starts. The engine must then
retry once on CPU instead of failing the job. No model is loaded here: the
per-attempt transcription is replaced with a stub.

Run with:  .venv/bin/python -m tests.test_engine_fallback
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import engine as E

FAILURES: list = []

CUBLAS_ERROR = "Library cublas64_12.dll is not found or cannot be loaded"


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} {detail}")
        FAILURES.append(label)


def make_engine(script):
    """An engine whose attempts follow ``script``: a list of callables
    taking (engine, on_segment) and returning a result or raising."""
    eng = E.WhisperEngine()
    eng._hardware = {"cuda_usable": True, "warnings": [], "notes": []}
    eng.unload = lambda: setattr(eng, "unloaded", True)
    attempts = []

    def once(audio, *, duration, overrides=None, on_segment=None, should_cancel=None):
        step = script[len(attempts)]
        attempts.append(step)
        return step(eng, on_segment)

    eng._transcribe_once = once
    eng.attempts = attempts
    return eng


def on_cuda(eng):
    eng._backend = "ctranslate2"
    eng._loaded_device = "cuda"


def fail_on_cuda(message, segments_first=0):
    def step(eng, on_segment):
        on_cuda(eng)
        for i in range(segments_first):
            on_segment(i, object(), None)
        raise RuntimeError(message)
    return step


def succeed(eng, on_segment):
    eng._loaded_device = "cpu"
    return {"segments": ["ok"], "device": "cpu"}


def test_missing_cublas_retries_on_cpu():
    eng = make_engine([fail_on_cuda(CUBLAS_ERROR), succeed])
    result = eng.transcribe(None, duration=1.0)
    check("retried once", len(eng.attempts) == 2)
    check("result came from CPU", result.get("device") == "cpu")
    check("CUDA disabled", eng._hardware["cuda_usable"] is False)
    check("runtime failure remembered", eng.cuda_runtime_failed is True)
    check("model unloaded before retry", getattr(eng, "unloaded", False))
    check("warning mentions cuBLAS for the Install button",
          any("cuBLAS" in w for w in eng._hardware["warnings"]))


def test_missing_cudnn_retries_on_cpu():
    eng = make_engine([fail_on_cuda("Could not locate cudnn_ops64_9.dll"), succeed])
    eng.transcribe(None, duration=1.0)
    check("retried once", len(eng.attempts) == 2)


def test_no_retry_after_segments_emitted():
    eng = make_engine([fail_on_cuda(CUBLAS_ERROR, segments_first=2), succeed])
    try:
        eng.transcribe(None, duration=1.0, on_segment=lambda *a: None)
        check("raised", False)
    except RuntimeError:
        check("raised instead of retrying mid-transcript", len(eng.attempts) == 1)


def test_unrelated_errors_propagate():
    eng = make_engine([fail_on_cuda("CUDA out of memory"), succeed])
    try:
        eng.transcribe(None, duration=1.0)
        check("raised", False)
    except RuntimeError as exc:
        check("not retried", len(eng.attempts) == 1)
        check("CUDA still usable", eng._hardware["cuda_usable"] is True)
        check("original error kept", "out of memory" in str(exc))


def test_cpu_dll_error_is_explained():
    def onnx_fail(eng, on_segment):
        eng._backend = "ctranslate2"
        eng._loaded_device = "cpu"
        raise ImportError(
            "DLL load failed while importing onnxruntime_pybind11_state: "
            "The specified module could not be found."
        )
    eng = make_engine([onnx_fail])
    try:
        eng.transcribe(None, duration=1.0)
        check("raised", False)
    except E.EngineError as exc:
        check("points to the VC++ redistributable", "vc_redist" in str(exc), str(exc))
        check("not retried", len(eng.attempts) == 1)


def test_classifier():
    yes = [
        CUBLAS_ERROR,
        "Could not locate cudnn_ops64_9.dll. Please make sure it is in your library path!",
        "Unable to load any of {libcudnn_ops.so.9}",
    ]
    no = ["CUDA out of memory", "Invalid input features shape", ""]
    for text in yes:
        check(f"detects: {text[:40]}", E._is_missing_gpu_library(RuntimeError(text)))
    for text in no:
        check(f"ignores: {text[:40]!r}", not E._is_missing_gpu_library(RuntimeError(text)))


def main() -> int:
    tests = [
        test_missing_cublas_retries_on_cpu,
        test_missing_cudnn_retries_on_cpu,
        test_no_retry_after_segments_emitted,
        test_unrelated_errors_propagate,
        test_cpu_dll_error_is_explained,
        test_classifier,
    ]
    for test in tests:
        print(f"\n{test.__name__}")
        test()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
