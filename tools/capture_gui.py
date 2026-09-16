from __future__ import annotations

import os
import tempfile
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from openexafs_studio.main_window import MainWindow


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)


def _font(size: int, bold: bool = False):
    candidates = [
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def prepare_demo(window: MainWindow) -> None:
    """Populate the GUI with a real PtO2 Feff8L example when possible."""
    example = ROOT / "examples" / "PtO2_P4415.cif"
    run_dir = Path(tempfile.mkdtemp(prefix="openexafs_demo_"))

    info = window.engine.load_structure(example)
    window.structure_path.setText("examples/PtO2_P4415.cif")

    window.absorber.blockSignals(True)
    window.absorber.clear()
    window.absorber.addItems(info.elements)
    if "Pt" in info.elements:
        window.absorber.setCurrentText("Pt")
    window.absorber.blockSignals(False)
    window.refresh_absorber_sites()

    window.engine.set_run_dir(run_dir)
    window.run_dir.setText(str(run_dir))
    window.edge.setCurrentText("L3")
    window.cluster.setValue(8.0)

    text = window.engine.generate_feff_input(
        absorber=window.absorber.currentText(),
        edge=window.edge.currentText(),
        cluster_size=window.cluster.value(),
        site_index=window.abs_site.currentData(),
        with_h=False,
    )
    window.engine.save_feff_input(text)
    window.feff_editor.setPlainText(text)

    records = window.engine.run_feff8l(text, True)
    window.path_records = records
    window.refresh_path_table()

    # Keep the preview readable while still showing a real multipath calculation.
    for row in range(window.path_table.rowCount()):
        item = window.path_table.item(row, 0)
        if item is not None:
            item.setCheckState(Qt.Checked if row < 6 else Qt.Unchecked)

    window._switch_page(2)
    window.preview_mode.setCurrentText("|chi(R)|")
    window.plot_preview()
    window._log(f"PtO2 example | Feff8L completed | {len(records)} paths available")


def make_hero(raw_path: Path, hero_path: Path) -> None:
    screenshot = Image.open(raw_path).convert("RGB")

    width, height = 1800, 1120
    hero = Image.new("RGB", (width, height), "#111827")
    draw = ImageDraw.Draw(hero)

    # Subtle layered background, keeping the actual GUI as the focal point.
    draw.rounded_rectangle((46, 40, width - 46, height - 40), radius=34, fill="#172033")
    draw.rounded_rectangle((74, 68, width - 74, height - 68), radius=26, fill="#0f172a")

    title_font = _font(58, True)
    subtitle_font = _font(30, False)
    badge_font = _font(26, True)

    draw.text((112, 100), "FEFF8L -> Artemis, without the Python setup", font=title_font, fill="#f8fafc")
    draw.text(
        (114, 177),
        "OpenEXAFS Studio for Windows",
        font=subtitle_font,
        fill="#cbd5e1",
    )

    badge_text = "Portable Windows EXE  |  double-click and run"
    bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    badge_w = bbox[2] - bbox[0] + 42
    badge_h = bbox[3] - bbox[1] + 24
    draw.rounded_rectangle((114, 230, 114 + badge_w, 230 + badge_h), radius=16, fill="#2563eb")
    draw.text((135, 240), badge_text, font=badge_font, fill="white")

    max_w = width - 224
    max_h = height - 380
    ratio = min(max_w / screenshot.width, max_h / screenshot.height)
    screenshot = screenshot.resize(
        (int(screenshot.width * ratio), int(screenshot.height * ratio)),
        Image.Resampling.LANCZOS,
    )

    x = (width - screenshot.width) // 2
    y = 330
    shadow = Image.new("RGBA", hero.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle(
        (x - 18, y - 18, x + screenshot.width + 18, y + screenshot.height + 18),
        radius=24,
        fill=(0, 0, 0, 110),
    )
    hero = Image.alpha_composite(hero.convert("RGBA"), shadow).convert("RGB")
    hero.paste(screenshot, (x, y))

    hero.save(hero_path, optimize=True)


def main() -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.resize(1480, 900)

    try:
        prepare_demo(window)
    except Exception:
        # A screenshot is still useful if the Feff8L demo cannot run on a CI host.
        window._switch_page(0)
        window._log("GUI preview build")
        window._log(traceback.format_exc().splitlines()[-1])

    window.show()
    app.processEvents()

    raw = ASSETS / "openexafs-studio-gui.png"
    hero = ASSETS / "openexafs-studio-windows.png"

    if not window.grab().save(str(raw)):
        raise RuntimeError("Qt could not save the GUI screenshot.")

    make_hero(raw, hero)
    window.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
