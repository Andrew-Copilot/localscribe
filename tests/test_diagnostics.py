"""Privacy-safe diagnostics tests. Run: python -m tests.test_diagnostics"""

from __future__ import annotations

import json

from app.diagnostics import build_diagnostics

FAILURES: list = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} {detail}")
        FAILURES.append(label)


def test_diagnostics_are_allowlisted_and_path_free():
    private_values = {
        "title": "Synthetic private project",
        "transcript": "Synthetic transcript text",
        "token": "synthetic-secret-token",
        "media_path": "/home/researcher/private/interview.wav",
    }
    report = build_diagnostics(
        hardware={
            "cpu_cores": 8,
            "gpus": ["/private/device/name"],
            "cuda_usable": True,
            "apple_silicon": False,
            "mlx_available": False,
            **private_values,
        },
        offline_lock=True,
        check_for_updates=False,
    )
    serialized = json.dumps(report)
    check("diagnostics report app/runtime data", bool(report["app_version"] and report["runtime"]["python"]))
    check("diagnostics includes coarse hardware health", report["hardware"]["gpu_count"] == 1)
    check("diagnostics includes dependency versions", "fastapi" in report["dependencies"])
    check("diagnostics includes privacy status", report["privacy"]["offline_lock"] is True)
    check("diagnostics explicitly has no remote backup configuration", report["privacy"]["remote_backup_configured"] is False)
    check("report excludes project content and credentials", all(value not in serialized for value in private_values.values()))
    check("report excludes absolute paths", "/home/" not in serialized and "/private/" not in serialized)
    check("report excludes transcript/media fields", "transcript" not in serialized and "media_path" not in serialized)


def main() -> int:
    test_diagnostics_are_allowlisted_and_path_free()
    if FAILURES:
        print(f"\n{len(FAILURES)} test(s) failed: {', '.join(FAILURES)}")
        return 1
    print("\nAll diagnostics tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
