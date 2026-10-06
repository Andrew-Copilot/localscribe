"""Tests for Windows native-library discovery (app/winlibs.py).

Pure logic only: the Windows branch is exercised on any OS by flipping
IS_WINDOWS and pointing site-packages at a temporary directory, so no real
DLL is loaded.

Run with:  .venv/bin/python -m tests.test_winlibs
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import winlibs as W

FAILURES: list = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} {detail}")
        FAILURES.append(label)


class _Simulated:
    """Pretend to be Windows with a fake site-packages and CUDA_PATH."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def __enter__(self):
        self.saved = (
            W.IS_WINDOWS, W._site_packages, os.environ.get("PATH", ""),
            os.environ.get("CUDA_PATH"), list(W._added),
        )
        W.IS_WINDOWS = True
        W._site_packages = lambda: [self.root / "site-packages"]
        os.environ["CUDA_PATH"] = str(self.root / "cuda")
        W._added.clear()
        return self

    def __exit__(self, *exc):
        is_win, site_fn, path, cuda, added = self.saved
        W.IS_WINDOWS = is_win
        W._site_packages = site_fn
        os.environ["PATH"] = path
        if cuda is None:
            os.environ.pop("CUDA_PATH", None)
        else:
            os.environ["CUDA_PATH"] = cuda
        W._added[:] = added


def test_noop_off_windows():
    if W.IS_WINDOWS:
        print("  skip (running on Windows)")
        return
    before = os.environ.get("PATH", "")
    check("prepare() adds nothing", W.prepare() == [])
    check("PATH untouched", os.environ.get("PATH", "") == before)
    check("probe() is empty", W.probe() == {})
    check("missing() is empty", W.missing(W.CUDA_DLLS) == [])


def test_finds_nvidia_wheels_and_cuda_toolkit():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cublas = root / "site-packages" / "nvidia" / "cublas" / "bin"
        cudnn = root / "site-packages" / "nvidia" / "cudnn" / "bin"
        toolkit = root / "cuda" / "bin"
        for d in (cublas, cudnn, toolkit):
            d.mkdir(parents=True)
        with _Simulated(root):
            added = W.prepare()
            path = os.environ["PATH"].split(os.pathsep)
            for d in (cublas, cudnn, toolkit):
                check(f"adds {d.relative_to(root)}", str(d) in added, str(added))
                check(f"PATH has {d.relative_to(root)}", str(d) in path)
            check("missing dirs are skipped",
                  not any("torch" in a for a in added), str(added))
            check("second call adds nothing", W.prepare() == [])
            check("PATH not duplicated",
                  os.environ["PATH"].split(os.pathsep).count(str(cublas)) == 1)


def test_probe_reports_each_dll():
    original = W.can_load
    saved = W.IS_WINDOWS
    try:
        W.IS_WINDOWS = True
        W.can_load = lambda name: name.startswith("cublas")
        result = W.probe(W.CUDA_DLLS)
        check("probe covers every name", set(result) == set(W.CUDA_DLLS))
        check("missing() lists only unloadable",
              W.missing(W.CUDA_DLLS) == [n for n in W.CUDA_DLLS if not n.startswith("cublas")])
    finally:
        W.can_load = original
        W.IS_WINDOWS = saved


def main() -> int:
    tests = [
        test_noop_off_windows,
        test_finds_nvidia_wheels_and_cuda_toolkit,
        test_probe_reports_each_dll,
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
