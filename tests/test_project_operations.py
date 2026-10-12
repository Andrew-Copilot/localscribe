"""Regression checks for project-level transcription and translation choices."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import ModuleType

from app import folder_picker, projects

FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        FAILURES.append(label)


def test_project_operation_and_queued_task():
    project = projects._normalize_project({
        "data_sensitivity": "no_phi",
        "operation": "translate",
    })
    root = Path(__file__).resolve().parent.parent
    jobs = (root / "app/jobs.py").read_text(encoding="utf-8")
    project_module = (root / "app/projects.py").read_text(encoding="utf-8")
    check("projects preserve the selected operation", project["operation"] == "translate")
    check("legacy projects use the current default without changing archive metadata",
          "operation" not in projects._normalize_project({"data_sensitivity": "no_phi"}))
    check("missing project operation follows the current AI setting",
          projects.project_operation({"operation": "translate"}) == "translate")
    check("translation is carried into the queued job",
          "doc_id=doc_id, operation=operation" in jobs)
    check("engine task is explicitly set by the selected operation",
          'overrides["task"] = operation' in jobs)
    check("new project records validate explicit operation choices",
          'if key == "operation" and key in fields:' in project_module)
    try:
        projects.new_project_record("Study", operation="unsupported")
    except projects.ProjectValidationError:
        invalid_rejected = True
    else:
        invalid_rejected = False
    check("invalid project operations are rejected", invalid_rejected)


def test_native_picker_result_and_cancel():
    with tempfile.TemporaryDirectory() as directory:
        root_path = Path(directory)

        class FakeRoot:
            def withdraw(self):
                pass

            def attributes(self, *_args):
                pass

            def update_idletasks(self):
                pass

            def destroy(self):
                pass

        tkinter = ModuleType("tkinter")
        tkinter.__path__ = []
        tkinter.Tk = FakeRoot
        filedialog = ModuleType("tkinter.filedialog")
        selected = [str(root_path), ""]
        filedialog.askdirectory = lambda **_kwargs: selected.pop(0)

        old_tkinter = sys.modules.get("tkinter")
        old_filedialog = sys.modules.get("tkinter.filedialog")
        sys.modules["tkinter"] = tkinter
        sys.modules["tkinter.filedialog"] = filedialog
        try:
            check("picker returns the selected absolute folder",
                  folder_picker.choose_folder() == str(root_path.resolve()))
            check("picker cancellation leaves the path unchanged",
                  folder_picker.choose_folder() == "")
        finally:
            if old_tkinter is None:
                sys.modules.pop("tkinter", None)
            else:
                sys.modules["tkinter"] = old_tkinter
            if old_filedialog is None:
                sys.modules.pop("tkinter.filedialog", None)
            else:
                sys.modules["tkinter.filedialog"] = old_filedialog


def test_project_and_settings_controls_are_present():
    root = Path(__file__).resolve().parent.parent
    project_template = (root / "app/templates/project.html").read_text(encoding="utf-8")
    settings_template = (root / "app/templates/settings.html").read_text(encoding="utf-8")
    project_js = (root / "app/static/js/project.js").read_text(encoding="utf-8")
    settings_js = (root / "app/static/js/settings.js").read_text(encoding="utf-8")
    main = (root / "app/main.py").read_text(encoding="utf-8")
    check("project page offers both transcription operations",
          'value="transcribe"' in project_template
          and 'value="translate"' in project_template
          and "Translate to English" in project_template
          and "Translated" in project_js
          and "All ${operation === 'translate' ? 'translated' : 'transcribed'}"
          in project_js)
    check("operation choice is saved per project",
          "LS.put(`/api/projects/" in project_js
          and "operation });" in project_js)
    check("translation rejects an English-only model when source language is unknown",
          "Translate to English needs a multilingual Whisper model" in main)
    check("Box path includes a browse action",
          'id="browse-box-folder"' in settings_template
          and "LS.post('/api/folder-picker'" in settings_js)


def main() -> int:
    for test in (
        test_project_operation_and_queued_task,
        test_native_picker_result_and_cancel,
        test_project_and_settings_controls_are_present,
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
