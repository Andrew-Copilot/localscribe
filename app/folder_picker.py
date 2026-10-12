"""Native local folder selection for settings that require filesystem paths."""

from __future__ import annotations

from pathlib import Path


def choose_folder(initial_path: str = "") -> str:
    """Show a native directory chooser and return its absolute path or empty."""
    import tkinter as tk
    from tkinter import filedialog

    initial = Path(initial_path).expanduser() if initial_path else None
    if initial and not initial.is_dir():
        initial = initial.parent

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
        root.update_idletasks()
        selected = filedialog.askdirectory(
            parent=root,
            title="Choose a local Box Sync folder",
            initialdir=str(initial) if initial and initial.is_dir() else None,
            mustexist=True,
        )
        return str(Path(selected).expanduser().resolve()) if selected else ""
    finally:
        root.destroy()
