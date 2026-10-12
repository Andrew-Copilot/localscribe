"""Static accessibility baseline checks for the server-rendered interface.

Run with: python -m tests.test_accessibility
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CSS = ROOT / "app" / "static" / "css" / "app.css"
BASE = ROOT / "app" / "templates" / "base.html"
DOCUMENT = ROOT / "app" / "templates" / "document.html"
EDITOR = ROOT / "app" / "static" / "js" / "editor.js"
SPEAKERS = ROOT / "app" / "static" / "js" / "speakers.js"

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} {detail}")
        FAILURES.append(label)


def _color(css: str, name: str) -> str | None:
    match = re.search(rf"--{re.escape(name)}:\s*(#[0-9a-fA-F]{{6}})", css)
    return match.group(1) if match else None


def _luminance(color: str) -> float:
    channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    a, b = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def test_landmarks_and_keyboard_entry():
    base = BASE.read_text(encoding="utf-8")
    document = DOCUMENT.read_text(encoding="utf-8")
    check("skip link targets the main landmark",
          'href="#main-content"' in base and 'id="main-content" tabindex="-1"' in base)
    check("primary navigation has a name and active page state",
          '<nav class="nav" aria-label="Primary navigation">' in base
          and 'aria-current="page"' in base)
    check("main transcript controls expose labels and the waveform slider",
          'aria-label="Number of speakers"' in document
          and 'role="slider"' in document
          and 'aria-valuemin="0"' in document
          and 'aria-valuenow="0"' in document)


def test_keyboard_speaker_workflow_and_color_cues():
    editor = EDITOR.read_text(encoding="utf-8")
    speakers = SPEAKERS.read_text(encoding="utf-8")
    check("speaker assignment supports focused-turn number shortcuts",
          "focusedTurn()" in editor and "assignTurn(turnEl, speaker.id)" in editor)
    check("speaker rows include visible text labels independent of color",
          "speaker.short || speaker.name" in editor
          and "class=\"speaker-key\"" in speakers)


def test_focus_scaling_contrast_and_motion_preferences():
    css = CSS.read_text(encoding="utf-8")
    check("default type scales with the user's root font size",
          bool(re.search(r"body\s*\{[^}]*font:\s*1rem/", css, re.S)))
    check("keyboard focus is visible",
          ":focus-visible" in css and "outline-offset" in css)
    check("forced-colors mode preserves focus and control boundaries",
          "@media (forced-colors: active)" in css
          and "outline: 3px solid Highlight" in css)
    check("reduced-motion preference is respected",
          "@media (prefers-reduced-motion: reduce)" in css)

    ink = _color(css, "ink-3")
    surfaces = [_color(css, token) for token in ("paper", "surface", "surface-2")]
    check("muted text reaches 4.5:1 on standard surfaces",
          bool(ink and all(surface and _contrast(ink, surface) >= 4.5
                           for surface in surfaces)),
          f"ink-3={ink}, surfaces={surfaces}")


def main() -> int:
    for test in (
        test_landmarks_and_keyboard_entry,
        test_keyboard_speaker_workflow_and_color_cues,
        test_focus_scaling_contrast_and_motion_preferences,
    ):
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
