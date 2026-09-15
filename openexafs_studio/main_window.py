from __future__ import annotations

from pathlib import Path
import sys
import traceback

import numpy as np

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from .core import OpenEXAFSError, OpenFeffEngine, PreviewSettings
from .help_text import HELP_HTML


class TaskThread(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            self.done.emit(self.func(*self.args, **self.kwargs))
        except Exception:
            self.failed.emit(traceback.format_exc())


class MainWindow(QMainWindow):
    PAGE_META = [
        ("1", "Structure", "Load a structure and generate a FEFF8L input."),
        ("2", "Paths", "Inspect the FEFF8 scattering paths."),
        ("3", "Preview", "Preview selected paths in k or R space."),
        ("4", "Artemis export", "Export only the FEFF8 files needed for Artemis."),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenEXAFS Studio | Feff8L to Artemis")
        self.resize(1480, 900)
        self.setMinimumSize(1180, 720)

        self.engine = OpenFeffEngine()
        self.path_records = []
        self.preview_payload = None
        self.worker = None

        self._build_menu()
        self._build_ui()
        self._apply_style()
        self._draw_empty_state()
        self.statusBar().showMessage("Ready")

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("File")

        open_structure = QAction("Open structure...", self)
        open_structure.setShortcut("Ctrl+O")
        open_structure.triggered.connect(self.open_structure)
        file_menu.addAction(open_structure)

        file_menu.addSeparator()

        export_folder = QAction("Export Artemis folder...", self)
        export_folder.triggered.connect(self.export_artemis_folder)
        file_menu.addAction(export_folder)

        export_zip = QAction("Export Artemis ZIP...", self)
        export_zip.triggered.connect(self.export_artemis_zip)
        file_menu.addAction(export_zip)

        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = self.menuBar().addMenu("Help")
        help_action = QAction("OpenEXAFS Studio Help", self)
        help_action.setShortcut("F1")
        help_action.triggered.connect(self.show_help)
        help_menu.addAction(help_action)

        about = QAction("About", self)
        about.triggered.connect(self.show_about)
        help_menu.addAction(about)

    def _build_ui(self):
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        root_layout.addWidget(self._build_sidebar())

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        root_layout.addWidget(split, 1)

        work = QWidget()
        work.setObjectName("WorkPanel")
        work_layout = QVBoxLayout(work)
        work_layout.setContentsMargins(22, 18, 18, 18)
        work_layout.setSpacing(12)

        self.page_title = QLabel()
        self.page_title.setObjectName("PageTitle")
        self.page_subtitle = QLabel()
        self.page_subtitle.setObjectName("PageSubtitle")
        self.page_subtitle.setWordWrap(True)
        work_layout.addWidget(self.page_title)
        work_layout.addWidget(self.page_subtitle)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._structure_page())
        self.stack.addWidget(self._paths_page())
        self.stack.addWidget(self._preview_page())
        self.stack.addWidget(self._artemis_page())
        work_layout.addWidget(self.stack, 1)

        analysis = QWidget()
        analysis.setObjectName("AnalysisPanel")
        av = QVBoxLayout(analysis)
        av.setContentsMargins(12, 18, 18, 18)
        av.setSpacing(8)

        analysis_title = QLabel("Visualization / activity")
        analysis_title.setObjectName("AnalysisTitle")
        av.addWidget(analysis_title)

        self.figure = Figure(figsize=(7.5, 6), constrained_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        toolbar = NavigationToolbar(self.canvas, self)
        toolbar.setObjectName("PlotToolbar")
        av.addWidget(toolbar)
        av.addWidget(self.canvas, 1)

        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumHeight(150)
        self.console.setMaximumBlockCount(5000)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        self.console.setFont(mono)
        av.addWidget(self.console)

        split.addWidget(work)
        split.addWidget(analysis)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([560, 850])

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(180)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)

        self._switch_page(0)

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(208)
        v = QVBoxLayout(sidebar)
        v.setContentsMargins(16, 18, 16, 16)
        v.setSpacing(8)

        brand = QLabel("OpenEXAFS\nStudio")
        brand.setObjectName("Brand")
        v.addWidget(brand)

        engine = QLabel("Feff8L to Artemis")
        engine.setObjectName("EngineLabel")
        v.addWidget(engine)
        v.addSpacing(18)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = []
        for idx, (num, title, _) in enumerate(self.PAGE_META):
            button = QPushButton(f"{num}   {title}")
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked=False, i=idx: self._switch_page(i))
            self.nav_group.addButton(button, idx)
            self.nav_buttons.append(button)
            v.addWidget(button)

        v.addStretch(1)

        quick = QLabel("Workflow\nStructure -> FEFF8L -> paths -> Artemis")
        quick.setObjectName("SidebarHint")
        quick.setWordWrap(True)
        v.addWidget(quick)

        help_button = QPushButton("Help / field guide")
        help_button.setObjectName("SidebarSecondary")
        help_button.clicked.connect(self.show_help)
        v.addWidget(help_button)
        return sidebar

    def _switch_page(self, index: int):
        index = max(0, min(index, len(self.PAGE_META) - 1))
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        _, title, subtitle = self.PAGE_META[index]
        self.page_title.setText(title)
        self.page_subtitle.setText(subtitle)
        if index == 3:
            self.refresh_artemis_status()

    def _apply_style(self):
        QApplication.setStyle("Fusion")
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f5f7fa; color: #17202a; font-size: 10.5pt; }
            QMenuBar { background: #ffffff; border-bottom: 1px solid #dfe4ea; }
            QMenuBar::item:selected, QMenu::item:selected { background: #eaf1fb; }
            #Sidebar { background: #202938; border: none; }
            #Brand { color: #ffffff; font-size: 19pt; font-weight: 700; }
            #EngineLabel, #SidebarHint { color: #9fb0c3; font-size: 9pt; }
            QPushButton#NavButton {
                background: transparent; color: #cbd5e1; border: 0; border-radius: 6px;
                text-align: left; padding: 11px 12px; font-weight: 600;
            }
            QPushButton#NavButton:hover { background: #2c3748; color: #ffffff; }
            QPushButton#NavButton:checked { background: #334155; color: #ffffff; }
            QPushButton#SidebarSecondary {
                background: #2c3748; color: #dbe5f0; border: 1px solid #435269;
                border-radius: 6px; padding: 8px;
            }
            #PageTitle { color: #17202a; font-size: 18pt; font-weight: 700; }
            #PageSubtitle { color: #667085; font-size: 9.5pt; }
            #AnalysisTitle { color: #17202a; font-size: 14pt; font-weight: 700; }
            QGroupBox {
                background: #ffffff; border: 1px solid #dfe4ea; border-radius: 8px;
                margin-top: 14px; padding: 14px 12px 12px 12px; font-weight: 650;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #344054; }
            QLineEdit, QComboBox, QDoubleSpinBox, QPlainTextEdit, QTableWidget, QTextBrowser {
                background: #ffffff; border: 1px solid #cfd6df; border-radius: 5px;
                padding: 5px 7px; selection-background-color: #3973b8;
            }
            QPushButton {
                background: #ffffff; border: 1px solid #c9d2dc; border-radius: 6px;
                padding: 7px 11px; min-height: 18px;
            }
            QPushButton:hover { background: #f0f4f8; }
            QPushButton[primary="true"] {
                background: #2f6fb3; color: #ffffff; border-color: #2f6fb3; font-weight: 650;
            }
            QHeaderView::section {
                background: #eef2f6; color: #344054; border: 0;
                border-bottom: 1px solid #d8dee6; padding: 7px; font-weight: 650;
            }
            QTableWidget { gridline-color: #edf0f3; }
            #PlotToolbar { background: #ffffff; border: 0; }
            """
        )

    def _scroll(self, content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        return scroll

    def _make_primary(self, button: QPushButton):
        button.setProperty("primary", True)
        return button

    def _structure_page(self):
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        structure_box = QGroupBox("Structure model")
        grid = QGridLayout(structure_box)

        self.structure_path = QLineEdit()
        self.structure_path.setPlaceholderText("Select a CIF / POSCAR / CONTCAR...")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.open_structure)
        grid.addWidget(QLabel("Structure file"), 0, 0)
        grid.addWidget(self.structure_path, 0, 1)
        grid.addWidget(browse, 0, 2)

        self.absorber = QComboBox()
        self.absorber.currentTextChanged.connect(self.refresh_absorber_sites)
        grid.addWidget(QLabel("Absorber"), 1, 0)
        grid.addWidget(self.absorber, 1, 1, 1, 2)

        self.abs_site = QComboBox()
        grid.addWidget(QLabel("Absorber site"), 2, 0)
        grid.addWidget(self.abs_site, 2, 1, 1, 2)

        self.edge = QComboBox()
        self.edge.addItems(["K", "L3", "L2", "L1"])
        self.edge.setCurrentText("L3")
        grid.addWidget(QLabel("Edge"), 3, 0)
        grid.addWidget(self.edge, 3, 1)

        self.cluster = QDoubleSpinBox()
        self.cluster.setRange(2.0, 15.0)
        self.cluster.setValue(8.0)
        self.cluster.setSingleStep(0.5)
        self.cluster.setSuffix(" Å")
        grid.addWidget(QLabel("Cluster radius"), 4, 0)
        grid.addWidget(self.cluster, 4, 1)

        self.include_h = QCheckBox("Include hydrogen atoms")
        grid.addWidget(self.include_h, 5, 1, 1, 2)
        outer.addWidget(structure_box)

        run_box = QGroupBox("FEFF8L run")
        rg = QGridLayout(run_box)
        self.run_dir = QLineEdit(str(self.engine.run_dir))
        choose = QPushButton("Choose...")
        choose.clicked.connect(self.choose_run_dir)
        rg.addWidget(QLabel("Run directory"), 0, 0)
        rg.addWidget(self.run_dir, 0, 1)
        rg.addWidget(choose, 0, 2)

        gen = QPushButton("Generate feff.inp")
        gen.clicked.connect(self.generate_input)
        run = self._make_primary(QPushButton("Run Feff8L"))
        run.clicked.connect(self.run_feff)
        rg.addWidget(gen, 1, 1)
        rg.addWidget(run, 1, 2)
        outer.addWidget(run_box)

        editor_box = QGroupBox("Generated FEFF8 input")
        ev = QVBoxLayout(editor_box)
        self.feff_editor = QPlainTextEdit()
        self.feff_editor.setPlaceholderText("Generated feff.inp will appear here.")
        ev.addWidget(self.feff_editor)
        outer.addWidget(editor_box, 1)
        return self._scroll(content)

    def _paths_page(self):
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(0, 0, 0, 0)

        buttons = QHBoxLayout()
        refresh = QPushButton("Refresh paths")
        refresh.clicked.connect(self.refresh_paths)
        select_all = QPushButton("Select all")
        select_all.clicked.connect(lambda: self._select_visible_paths(True))
        select_none = QPushButton("Select none")
        select_none.clicked.connect(lambda: self._select_visible_paths(False))
        self.path_filter = QComboBox()
        self.path_filter.addItems(["All", "Single scattering", "Multiple scattering"])
        self.path_filter.currentTextChanged.connect(self.refresh_path_table)
        buttons.addWidget(refresh)
        buttons.addWidget(select_all)
        buttons.addWidget(select_none)
        buttons.addWidget(self.path_filter)
        buttons.addStretch(1)
        outer.addLayout(buttons)

        self.path_table = QTableWidget(0, 6)
        self.path_table.setHorizontalHeaderLabels(["Use", "File", "Type", "NLEG", "Degeneracy", "Reff / Å"])
        self.path_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.path_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.path_table.setAlternatingRowColors(True)
        outer.addWidget(self.path_table, 1)
        return content

    def _preview_page(self):
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(0, 0, 0, 0)

        controls = QGroupBox("Preview settings")
        grid = QGridLayout(controls)

        self.preview_mode = QComboBox()
        self.preview_mode.addItems(["|chi(R)|", "Re chi(R)", "Im chi(R)", "chi(k)", "k chi(k)", "k^2 chi(k)", "k^3 chi(k)"])
        grid.addWidget(QLabel("Representation"), 0, 0)
        grid.addWidget(self.preview_mode, 0, 1)

        self.kmin = QDoubleSpinBox(); self.kmin.setRange(0, 25); self.kmin.setValue(2.5)
        self.kmax = QDoubleSpinBox(); self.kmax.setRange(1, 30); self.kmax.setValue(12.0)
        self.kw = QComboBox(); self.kw.addItems(["0", "1", "2", "3"]); self.kw.setCurrentText("3")
        self.dk = QDoubleSpinBox(); self.dk.setRange(0, 5); self.dk.setValue(1.0)
        self.s02 = QDoubleSpinBox(); self.s02.setRange(0, 2); self.s02.setValue(1.0)
        self.e0 = QDoubleSpinBox(); self.e0.setRange(-50, 50); self.e0.setValue(0.0)
        self.dr = QDoubleSpinBox(); self.dr.setRange(-1, 1); self.dr.setDecimals(4)
        self.sig2 = QDoubleSpinBox(); self.sig2.setRange(0, 0.1); self.sig2.setDecimals(5)

        pairs = [
            ("k min", self.kmin), ("k max", self.kmax),
            ("k weight", self.kw), ("dk", self.dk),
            ("S0^2", self.s02), ("Delta E0", self.e0),
            ("Delta R", self.dr), ("sigma^2", self.sig2),
        ]
        for i, (label, widget) in enumerate(pairs, start=1):
            row = 1 + (i - 1) // 2
            col = ((i - 1) % 2) * 2
            grid.addWidget(QLabel(label), row, col)
            grid.addWidget(widget, row, col + 1)

        outer.addWidget(controls)

        actions = QHBoxLayout()
        plot = self._make_primary(QPushButton("Plot selected paths"))
        plot.clicked.connect(self.plot_preview)
        save_data = QPushButton("Save plotted data")
        save_data.clicked.connect(self.save_preview_data)
        save_fig = QPushButton("Save figure")
        save_fig.clicked.connect(self.save_figure)
        actions.addWidget(plot)
        actions.addWidget(save_data)
        actions.addWidget(save_fig)
        actions.addStretch(1)
        outer.addLayout(actions)
        outer.addStretch(1)
        return content

    def _artemis_page(self):
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        status_box = QGroupBox("Artemis compatibility")
        sv = QVBoxLayout(status_box)
        self.artemis_status = QLabel()
        self.artemis_status.setWordWrap(True)
        sv.addWidget(self.artemis_status)
        outer.addWidget(status_box)

        files_box = QGroupBox("Files exported")
        fv = QVBoxLayout(files_box)
        fv.addWidget(QLabel(
            "The export keeps the original Feff8L outputs: feff.inp, available FEFF metadata "
            "files, and all feffNNNN.dat scattering-path files. No FEFF6 conversion is applied."
        ))
        outer.addWidget(files_box)

        import_box = QGroupBox("Import into Artemis")
        iv = QVBoxLayout(import_box)
        instructions = QTextBrowser()
        instructions.setHtml(
            "<ol>"
            "<li>Export the Artemis folder or ZIP below.</li>"
            "<li>If ZIP is used, extract it.</li>"
            "<li>In Artemis choose <b>File &gt; Import... &gt; a feff.inp file</b>.</li>"
            "<li>Select the exported <code>feff.inp</code>.</li>"
            "<li>Keep all <code>feffNNNN.dat</code> files in the same directory.</li>"
            "</ol>"
        )
        iv.addWidget(instructions)
        outer.addWidget(import_box)

        actions = QHBoxLayout()
        folder = self._make_primary(QPushButton("Export Artemis folder"))
        folder.clicked.connect(self.export_artemis_folder)
        zip_button = QPushButton("Export Artemis ZIP")
        zip_button.clicked.connect(self.export_artemis_zip)
        actions.addWidget(folder)
        actions.addWidget(zip_button)
        actions.addStretch(1)
        outer.addLayout(actions)
        outer.addStretch(1)
        return content

    def open_structure(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open structure",
            "",
            "Structure files (*.cif *.vasp *.cssr *.xyz *.txt);;All files (*)",
        )
        if not path:
            return
        try:
            info = self.engine.load_structure(path)
            self.structure_path.setText(path)
            self.absorber.blockSignals(True)
            self.absorber.clear()
            self.absorber.addItems(info.elements)
            if "Pt" in info.elements:
                self.absorber.setCurrentText("Pt")
            self.absorber.blockSignals(False)
            self.refresh_absorber_sites()
            self._log(f"Loaded {info.formula}: {len(info.sites)} sites")
        except Exception as exc:
            self._error(exc)

    def refresh_absorber_sites(self):
        self.abs_site.clear()
        for site in self.engine.absorber_sites(self.absorber.currentText()):
            self.abs_site.addItem(
                f"Site {site.index}: {site.species} | {site.coordinates}",
                userData=site.index,
            )

    def choose_run_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Choose FEFF run directory")
        if path:
            self.engine.set_run_dir(path)
            self.run_dir.setText(str(self.engine.run_dir))

    def generate_input(self):
        try:
            self.engine.set_run_dir(self.run_dir.text())
            site_index = self.abs_site.currentData()
            text = self.engine.generate_feff_input(
                absorber=self.absorber.currentText(),
                edge=self.edge.currentText(),
                cluster_size=self.cluster.value(),
                site_index=site_index,
                with_h=self.include_h.isChecked(),
            )
            self.engine.save_feff_input(text)
            self.feff_editor.setPlainText(text)
            self._log("Generated FEFF8-style feff.inp")
        except Exception as exc:
            self._error(exc)

    def run_feff(self):
        try:
            self.engine.set_run_dir(self.run_dir.text())
            text = self.feff_editor.toPlainText().strip()
            if not text:
                self.generate_input()
                text = self.feff_editor.toPlainText().strip()
            self._start_task(self.engine.run_feff8l, self._run_finished, text, True)
        except Exception as exc:
            self._error(exc)

    def _run_finished(self, records):
        self.path_records = records
        self.refresh_path_table()
        self.refresh_artemis_status()
        self._log(f"Feff8L completed: {len(records)} paths")
        self._switch_page(1)

    def refresh_paths(self):
        try:
            self.engine.set_run_dir(self.run_dir.text())
            self.path_records = self.engine.scan_paths()
            self.refresh_path_table()
            self._log(f"Found {len(self.path_records)} FEFF paths")
        except Exception as exc:
            self._error(exc)

    def _filtered_records(self):
        mode = self.path_filter.currentText() if hasattr(self, "path_filter") else "All"
        if mode == "Single scattering":
            return [r for r in self.path_records if r.kind == "SS"]
        if mode == "Multiple scattering":
            return [r for r in self.path_records if r.kind == "MS"]
        return list(self.path_records)

    def refresh_path_table(self):
        records = self._filtered_records()
        self.path_table.setRowCount(len(records))
        for row, record in enumerate(records):
            use = QTableWidgetItem()
            use.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            use.setCheckState(Qt.Checked)
            use.setData(Qt.UserRole, record.filename)
            self.path_table.setItem(row, 0, use)
            self.path_table.setItem(row, 1, QTableWidgetItem(Path(record.filename).name))
            self.path_table.setItem(row, 2, QTableWidgetItem(record.kind))
            self.path_table.setItem(row, 3, QTableWidgetItem(str(record.nleg)))
            self.path_table.setItem(row, 4, QTableWidgetItem(f"{record.degen:.4g}"))
            self.path_table.setItem(row, 5, QTableWidgetItem(f"{record.reff:.5f}"))

    def _select_visible_paths(self, selected: bool):
        state = Qt.Checked if selected else Qt.Unchecked
        for row in range(self.path_table.rowCount()):
            self.path_table.item(row, 0).setCheckState(state)

    def selected_path_files(self):
        selected = []
        for row in range(self.path_table.rowCount()):
            item = self.path_table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                selected.append(item.data(Qt.UserRole))
        return selected

    def plot_preview(self):
        files = self.selected_path_files()
        if not files:
            QMessageBox.information(self, "OpenEXAFS Studio", "Select at least one FEFF path.")
            return
        settings = PreviewSettings(
            kmin=self.kmin.value(),
            kmax=self.kmax.value(),
            kweight=int(self.kw.currentText()),
            dk=self.dk.value(),
            s02=self.s02.value(),
            e0=self.e0.value(),
            deltar=self.dr.value(),
            sigma2=self.sig2.value(),
        )
        try:
            self.preview_payload = self.engine.build_preview(files, settings)
            self._draw_preview()
        except Exception as exc:
            self._error(exc)

    def _draw_preview(self):
        payload = self.preview_payload
        if not payload:
            return
        mode = self.preview_mode.currentText()
        is_r = mode in {"|chi(R)|", "Re chi(R)", "Im chi(R)"}
        ykey = {"|chi(R)|": "chir_mag", "Re chi(R)": "chir_re", "Im chi(R)": "chir_im"}.get(mode, "chi")
        power = {"chi(k)": 0, "k chi(k)": 1, "k^2 chi(k)": 2, "k^3 chi(k)": 3}.get(mode, 0)

        self.figure.clear()
        ax = self.figure.add_subplot(111)
        for s in payload["series"]:
            x = s["r"] if is_r else s["k"]
            y = s[ykey] if is_r else s[ykey] * (x ** power)
            ax.plot(x, y, lw=1, alpha=0.65, label=s["label"])
        s = payload.get("sum")
        if s:
            x = s["r"] if is_r else s["k"]
            y = s[ykey] if is_r else s[ykey] * (x ** power)
            ax.plot(x, y, lw=2.6, color="black", label="Sum")
        ax.set_xlabel("R (Å)" if is_r else "k (Å$^{-1}$)")
        ax.set_ylabel(mode)
        ax.axhline(0, color="0.8", lw=0.7)
        ax.legend(fontsize=7, ncol=2)
        self.canvas.draw_idle()

    def save_preview_data(self):
        if not self.preview_payload:
            QMessageBox.information(self, "OpenEXAFS Studio", "Plot paths first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save plotted data", "openexafs_preview.csv", "CSV (*.csv)")
        if path:
            self.engine.export_preview_csv(self.preview_payload, self.preview_mode.currentText(), path)
            self._log(f"Saved preview data: {path}")

    def save_figure(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save figure", "openexafs_preview.png", "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)"
        )
        if path:
            self.figure.savefig(path, dpi=300)
            self._log(f"Saved figure: {path}")

    def refresh_artemis_status(self):
        if not hasattr(self, "artemis_status"):
            return
        try:
            self.engine.set_run_dir(self.run_dir.text())
            ok, message = self.engine.validate_artemis_run()
            self.artemis_status.setText(("Ready: " if ok else "Not ready: ") + message)
        except Exception as exc:
            self.artemis_status.setText(str(exc))

    def export_artemis_folder(self):
        try:
            self.engine.set_run_dir(self.run_dir.text())
            path = QFileDialog.getExistingDirectory(self, "Choose destination for Artemis FEFF8 package")
            if not path:
                return
            out = self.engine.export_artemis_folder(path)
            self._log(f"Exported Artemis FEFF8 folder: {out}")
            QMessageBox.information(self, "OpenEXAFS Studio", f"Artemis package exported to:\n{out}")
        except Exception as exc:
            self._error(exc)

    def export_artemis_zip(self):
        try:
            self.engine.set_run_dir(self.run_dir.text())
            path, _ = QFileDialog.getSaveFileName(
                self, "Export Artemis FEFF8 ZIP", "Artemis_FEFF8.zip", "ZIP archive (*.zip)"
            )
            if not path:
                return
            out = self.engine.export_artemis_zip(path)
            self._log(f"Exported Artemis FEFF8 ZIP: {out}")
            QMessageBox.information(self, "OpenEXAFS Studio", f"Artemis ZIP exported:\n{out}")
        except Exception as exc:
            self._error(exc)

    def _start_task(self, func, callback, *args):
        self.progress.setRange(0, 0)
        self.progress.show()
        self.worker = TaskThread(func, *args)
        self.worker.done.connect(lambda result: self._task_done(callback, result))
        self.worker.failed.connect(self._task_failed)
        self.worker.start()

    def _task_done(self, callback, result):
        self.progress.hide()
        callback(result)
        self.worker = None

    def _task_failed(self, message):
        self.progress.hide()
        self.console.appendPlainText(message)
        QMessageBox.critical(self, "OpenEXAFS Studio", message)
        self.worker = None

    def _draw_empty_state(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.text(
            0.5, 0.5,
            "Load a structure, run Feff8L, and select paths.",
            ha="center", va="center", transform=ax.transAxes, color="0.45"
        )
        ax.set_axis_off()
        self.canvas.draw_idle()

    def _log(self, text):
        self.console.appendPlainText(text)
        self.statusBar().showMessage(text, 8000)

    def _error(self, exc):
        message = str(exc)
        self.console.appendPlainText(message)
        QMessageBox.critical(self, "OpenEXAFS Studio", message)

    def show_help(self):
        dialog = QMessageBox(self)
        dialog.setWindowTitle("OpenEXAFS Studio Help")
        dialog.setTextFormat(Qt.RichText)
        dialog.setText(HELP_HTML)
        dialog.exec()

    def show_about(self):
        QMessageBox.information(
            self,
            "About OpenEXAFS Studio",
            "OpenEXAFS Studio\n\n"
            "FEFF8L path generation, inspection, preview, and Artemis export.\n"
            "Built with Python, PySide6, XrayLarch, and Feff8L.",
        )


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
