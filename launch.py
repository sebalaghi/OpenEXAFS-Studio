from __future__ import annotations

from pathlib import Path
import ctypes
import os
import sys
import traceback


ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
LOG = ROOT / "OpenEXAFS_launch_error.log"


def show_native_error(title: str, message: str) -> None:
    """Show an error even when Python/Qt fails before QApplication exists."""
    try:
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
    except Exception:
        pass


def main() -> int:
    try:
        from openexafs_studio.main_window import main as gui_main
        return int(gui_main())
    except Exception:
        trace = traceback.format_exc()
        LOG.write_text(
            "OpenEXAFS Studio startup failure\n\n"
            f"Python: {sys.executable}\n"
            f"Version: {sys.version}\n"
            f"Working directory: {os.getcwd()}\n\n"
            f"{trace}",
            encoding="utf-8",
        )
        last = trace.strip().splitlines()[-1] if trace.strip() else "Unknown startup error"
        show_native_error(
            "OpenEXAFS Studio startup error",
            f"The GUI could not start.\n\n{last}\n\n"
            f"Full details were written to:\n{LOG}",
        )
        print(trace, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
