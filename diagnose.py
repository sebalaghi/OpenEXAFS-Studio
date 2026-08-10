from __future__ import annotations

import argparse
import importlib.metadata as metadata
from pathlib import Path
import os
import platform
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "OpenEXAFS_diagnostic.log"

log_lines: list[str] = []


def emit(text=""):
    text = str(text)
    print(text, flush=True)
    log_lines.append(text)


def version(name: str) -> str:
    try:
        return metadata.version(name)
    except Exception:
        return "NOT INSTALLED"


def timed_check(label: str, code: str) -> bool:
    emit(f"Checking {label} ...")
    start = time.perf_counter()
    try:
        ns = {}
        exec(code, ns, ns)
        elapsed = time.perf_counter() - start
        emit(f"OK   {label}  ({elapsed:.2f} s)")
        emit()
        return True
    except Exception:
        elapsed = time.perf_counter() - start
        emit(f"FAIL {label}  ({elapsed:.2f} s)")
        emit(traceback.format_exc())
        emit()
        return False


def main() -> int:
    emit("OpenEXAFS Studio v0.1.6 live diagnostic")
    emit("=" * 78)
    emit(f"Python executable: {sys.executable}")
    emit(f"Python version:    {sys.version}")
    emit(f"CONDA_PREFIX:      {os.environ.get('CONDA_PREFIX', '<not set>')}")
    emit(f"CONDA_DEFAULT_ENV: {os.environ.get('CONDA_DEFAULT_ENV', '<not set>')}")
    emit(f"Platform:          {platform.platform()}")
    emit()
    emit("Installed distributions:")
    emit(f"  xraylarch = {version('xraylarch')}")
    emit(f"  larixite  = {version('larixite')}")
    emit(f"  PySide6   = {version('PySide6')}")
    emit(f"  pymatgen  = {version('pymatgen')}")
    emit()

    checks = [
        ("larch", "import larch"),
        ("larixite", "import larixite"),
        ("FEFF runner/path/fit", "from larch.xafs import feffrunner, feffpath, feffit"),
        ("Structure-to-FEFF", "from larch.xrd.structure2feff import structure2feffinp"),
        ("PySide6", "import PySide6"),
        ("OpenEXAFS core", "from openexafs_studio.core import OpenFeffEngine"),
        ("OpenEXAFS GUI module", "from openexafs_studio.main_window import MainWindow"),
    ]

    ok_all = True
    for label, code in checks:
        ok_all &= timed_check(label, code)

    emit("Checking packaged Feff8L modules ...")
    start = time.perf_counter()
    try:
        from larch.utils import bindir
        bindir = Path(bindir)
        required = [
            "feff8l_rdinp.exe",
            "feff8l_pot.exe",
            "feff8l_xsph.exe",
            "feff8l_pathfinder.exe",
            "feff8l_genfmt.exe",
            "feff8l_ff2x.exe",
        ]
        missing = [name for name in required if not (bindir / name).exists()]
        emit(f"Larch bindir: {bindir}")
        if missing:
            ok_all = False
            emit("FAIL packaged Feff8L modules: " + ", ".join(missing))
        else:
            emit(f"OK   packaged Feff8L modules ({time.perf_counter()-start:.2f} s)")
    except Exception:
        ok_all = False
        emit("FAIL packaged Feff8L modules")
        emit(traceback.format_exc())
    emit()

    emit("Checking Qt offscreen QApplication ...")
    start = time.perf_counter()
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(
            ["OpenEXAFS-diagnostic", "-platform", "offscreen"]
        )
        emit(f"OK   Qt offscreen QApplication ({time.perf_counter()-start:.2f} s)")
        app.quit()
    except Exception:
        ok_all = False
        emit("FAIL Qt offscreen QApplication")
        emit(traceback.format_exc())
    emit()

    emit("=" * 78)
    emit("RESULT: PASS" if ok_all else "RESULT: FAIL")
    LOG.write_text("\n".join(log_lines), encoding="utf-8")
    emit(f"Diagnostic log: {LOG}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true")
    parser.parse_args()
    raise SystemExit(main())
