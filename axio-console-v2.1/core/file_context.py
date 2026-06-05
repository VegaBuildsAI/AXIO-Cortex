"""
AXIO Core — Shared File Context
Unified file/folder loading used by Cowork, RevRec, Code, and any future mode.

Provides:
  - FileContext   : holds loaded paths, builds context blocks for prompts
  - browse_folder : opens native OS folder picker (tkinter)
  - browse_files  : opens native OS multi-file picker (tkinter)
  - scan_folder   : walks a folder and returns matching files

Usage:
    from core.file_context import FileContext, browse_folder

    ctx = FileContext(extensions={".pdf", ".txt", ".docx"})
    folder = browse_folder()          # opens Windows folder picker
    ctx.load_folder(folder)
    prompt = ctx.inject(user_prompt)  # prepends file list to prompt
"""

from __future__ import annotations

from pathlib import Path

# ─────────────────────────────────────────────────────────
#  Supported extension sets  (importable by any mode)
# ─────────────────────────────────────────────────────────
TEXT_EXTS     = {".txt", ".md", ".py", ".js", ".ts", ".html", ".css",
                 ".json", ".yaml", ".yml", ".toml", ".csv", ".xml", ".rst"}
CONTRACT_EXTS = {".pdf", ".txt", ".md", ".docx", ".doc", ".csv"}
ALL_EXTS      = TEXT_EXTS | CONTRACT_EXTS


# ─────────────────────────────────────────────────────────
#  Native OS picker  (tkinter — ships with Python on Windows)
# ─────────────────────────────────────────────────────────

def _tk_available() -> bool:
    try:
        import tkinter  # noqa: F401
        return True
    except ImportError:
        return False


def browse_folder(title: str = "Select folder") -> str | None:
    """
    Open the native Windows folder-picker dialog.
    Returns the selected path as a string, or None if cancelled.
    Must be called from the main thread on Windows.
    """
    if not _tk_available():
        return None
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()          # hide the empty root window
    root.lift()
    root.attributes("-topmost", True)
    path = filedialog.askdirectory(title=title)
    root.destroy()
    return path or None


def browse_files(
    title: str = "Select contract file(s)",
    extensions: set[str] | None = None,
) -> list[str]:
    """
    Open the native Windows multi-file picker dialog.
    Returns a list of selected file paths (may be empty).
    """
    if not _tk_available():
        return []
    import tkinter as tk
    from tkinter import filedialog

    exts = extensions or CONTRACT_EXTS
    # Build filetypes tuple for the dialog
    desc = " ".join(f"*{e}" for e in sorted(exts))
    filetypes = [("Supported files", desc), ("All files", "*.*")]

    root = tk.Tk()
    root.withdraw()
    root.lift()
    root.attributes("-topmost", True)
    paths = filedialog.askopenfilenames(title=title, filetypes=filetypes)
    root.destroy()
    return list(paths)


# ─────────────────────────────────────────────────────────
#  Folder scanner
# ─────────────────────────────────────────────────────────

def scan_folder(
    folder: str | Path,
    extensions: set[str] | None = None,
    max_files: int = 200,
) -> list[Path]:
    """
    Walk a folder recursively and return matching files sorted by name.
    Skips .git / __pycache__ / node_modules automatically.
    """
    p = Path(folder)
    if not p.is_dir():
        return []
    exts = extensions or CONTRACT_EXTS
    skip = {".git", "__pycache__", "node_modules", ".venv", "venv"}
    results = []
    for f in sorted(p.rglob("*")):
        if any(part in skip for part in f.parts):
            continue
        if f.is_file() and f.suffix.lower() in exts:
            results.append(f)
        if len(results) >= max_files:
            break
    return results


# ─────────────────────────────────────────────────────────
#  FileContext  —  the shared state object
# ─────────────────────────────────────────────────────────

class FileContext:
    """
    Holds a list of file paths queued for agent processing.
    Modes instantiate one FileContext and call its methods from their REPL.

    Example REPL integration:
        ctx = FileContext()

        # "browse" command
        folder = browse_folder()
        if folder:
            msg = ctx.load_folder(folder)
            print(msg)

        # "load <path>" command
        msg = ctx.load_path(user_input_path)
        print(msg)

        # inject into agent prompt
        final_prompt = ctx.inject(user_prompt, mode="list")
    """

    def __init__(self, extensions: set[str] | None = None):
        self.extensions: set[str] = extensions or CONTRACT_EXTS
        self.files: list[Path] = []

    # ── loading ───────────────────────────────────────────

    def load_path(self, path_str: str) -> str:
        """Load a single file or scan a folder. Returns a status string."""
        p = Path(path_str.strip().strip('"').strip("'"))
        if not p.exists():
            return f"\033[31m  Not found: {p}\033[0m"
        if p.is_file():
            return self._add_file(p)
        if p.is_dir():
            return self.load_folder(p)
        return f"\033[31m  Not a file or folder: {p}\033[0m"

    def load_folder(self, folder: str | Path) -> str:
        """Scan a folder and add all matching files."""
        found = scan_folder(folder, self.extensions)
        if not found:
            return f"\033[33m  No supported files found in: {folder}\033[0m"
        added = 0
        for f in found:
            if f not in self.files:
                self.files.append(f)
                added += 1
        lines = [f"\033[32m  Loaded {added} file(s) from: {Path(folder).name}/\033[0m"]
        for f in found:
            lines.append(f"    \033[90m{f.name}\033[0m")
        return "\n".join(lines)

    def load_browse_folder(self) -> str:
        """Open the native folder picker and load the chosen folder."""
        if not _tk_available():
            return (
                "\033[33m  tkinter not available — type the path manually:\033[0m\n"
                "  \033[90mload \"C:\\path\\to\\folder\"\033[0m"
            )
        path = browse_folder("Select contract folder to load")
        if not path:
            return "\033[90m  Cancelled.\033[0m"
        return self.load_folder(path)

    def load_browse_files(self) -> str:
        """Open the native multi-file picker and load chosen files."""
        if not _tk_available():
            return (
                "\033[33m  tkinter not available — type the path manually:\033[0m\n"
                "  \033[90mload \"C:\\path\\to\\file.pdf\"\033[0m"
            )
        paths = browse_files(extensions=self.extensions)
        if not paths:
            return "\033[90m  Cancelled.\033[0m"
        msgs = []
        for p in paths:
            msgs.append(self._add_file(Path(p)))
        return "\n".join(msgs)

    def _add_file(self, p: Path) -> str:
        if p.suffix.lower() not in self.extensions:
            supported = "  ".join(sorted(self.extensions))
            return (
                f"\033[33m  Unsupported type: {p.suffix}\033[0m\n"
                f"  \033[90mSupported: {supported}\033[0m"
            )
        if p not in self.files:
            self.files.append(p)
        return f"\033[32m  Loaded:\033[0m \033[35m{p.name}\033[0m  \033[90m({p})\033[0m"

    # ── listing / clearing ────────────────────────────────

    def list_str(self) -> str:
        if not self.files:
            return (
                "\033[90m  No files loaded.\033[0m\n"
                "  Use \033[35mbrowse\033[0m (folder picker) or "
                "\033[35mload <path>\033[0m (manual path)."
            )
        lines = [f"\n  \033[1mLoaded files ({len(self.files)}):\033[0m"]
        for f in self.files:
            lines.append(f"    \033[35m{f.name:<40}\033[0m \033[90m{f.parent}\033[0m")
        return "\n".join(lines) + "\n"

    def clear(self) -> str:
        n = len(self.files)
        self.files.clear()
        return f"\033[32m  Cleared {n} file(s).\033[0m"

    def remove(self, name: str) -> str:
        before = len(self.files)
        self.files = [f for f in self.files if f.name != name and str(f) != name]
        removed = before - len(self.files)
        return (
            f"\033[32m  Removed {removed} file(s).\033[0m"
            if removed else
            f"\033[33m  Not found: {name}\033[0m"
        )

    # ── prompt injection ──────────────────────────────────

    def inject(self, prompt: str, mode: str = "list") -> str:
        """
        Prepend loaded file paths to a prompt so the agent knows what to read.

        mode="list"   → bullet list of absolute paths  (for RevRec, Code)
        mode="block"  → workspace context block        (for Cowork)
        """
        if not self.files:
            return prompt

        if mode == "list":
            paths_block = "\n".join(f"  - {f}" for f in self.files)
            return (
                f"{prompt}\n\n"
                f"Use these files (call read_pdf for .pdf, read_file for others):\n"
                f"{paths_block}"
            )
        elif mode == "block":
            parts = ["\n\n--- LOADED FILES CONTEXT ---"]
            for f in self.files:
                parts.append(f"\n## File: {f.name}\nPath: {f}")
            parts.append("--- END ---\n")
            return prompt + "\n".join(parts)

        return prompt

    # ── properties ────────────────────────────────────────

    @property
    def count(self) -> int:
        return len(self.files)

    @property
    def has_pdf(self) -> bool:
        return any(f.suffix.lower() == ".pdf" for f in self.files)


# ─────────────────────────────────────────────────────────
#  Session-level singleton — shared across ALL modes
# ─────────────────────────────────────────────────────────
#
#  Usage in any mode:
#      from core.file_context import SESSION_CONTEXT
#
#  Loading a folder in Cowork, switching to RevRec, and
#  typing 'analyze' will find the files already loaded.
#
SESSION_CONTEXT = FileContext()
