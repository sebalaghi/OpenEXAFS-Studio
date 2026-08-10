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
    QDialog,
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
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from .core import (
    FitSettings,
    OpenEXAFSError,
    OpenFeffEngine,
    PreviewSettings,
)
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
    """Practical three-zone scientific workflow UI.

    Left: workflow navigation
    Center: controls for the active step
    Right: visualization / activity report
    """

    PAGE_META = [
        ("1", "Structure", "Load a crystal structure and generate the Feff8L input."),
        ("2", "Paths", "Inspect and select FEFF scattering paths."),
        ("3", "Preview", "Preview selected path contributions in k or R space."),
        ("4", "Fit", "Load experimental XAS data and run Larch FEFFIT."),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenEXAFS Studio | XrayLarch + Feff8L")
        self.resize(1480, 900)
        self.setMinimumSize(1180, 720)

        self.engine = OpenFeffEngine()
        self.path_records = []
        self.preview_payload = None
        self.xas_groups = {}
        self.current_group = None
        self.last_fit = None
        self.worker = None

        self._build_menu()
        self._build_ui()
        self._apply_style()
        self._draw_empty_state()
        self.statusBar().showMessage("Ready")

    # ------------------------------------------------------------------
    # Shell / navigation
    # ------------------------------------------------------------------
    def _build_menu(self):
        file_menu = self.menuBar().addMenu("File")

        open_structure = QAction("Open structure...", self)
        open_structure.setShortcut("Ctrl+O")
        open_structure.triggered.connect(self.open_structure)
        file_menu.addAction(open_structure)

        open_data = QAction("Open XAS data...", self)
        open_data.setShortcut("Ctrl+Shift+O")
        open_data.triggered.connect(self.open_xas_data)
        file_menu.addAction(open_data)

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

        # Center workflow panel
        work = QWidget()
        work.setObjectName("WorkPanel")
        work_layout = QVBoxLayout(work)
        work_layout.setContentsMargins(22, 18, 18, 18)
        work_layout.setSpacing(12)

        header = QWidget()
        hv = QVBoxLayout(header)
        hv.setContentsMargins(0, 0, 0, 4)
        hv.setSpacing(3)
        self.page_title = QLabel()
        self.page_title.setObjectName("PageTitle")
        self.page_subtitle = QLabel()
        self.page_subtitle.setObjectName("PageSubtitle")
        self.page_subtitle.setWordWrap(True)
        hv.addWidget(self.page_title)
        hv.addWidget(self.page_subtitle)
        work_layout.addWidget(header)

        self.stack = QStackedWidget()
        self.left_tabs = self.stack  # compatibility with workflow callbacks
        self.stack.addWidget(self._structure_page())
        self.stack.addWidget(self._paths_page())
        self.stack.addWidget(self._preview_page())
        self.stack.addWidget(self._fit_page())
        work_layout.addWidget(self.stack, 1)

        # Right analysis panel
        analysis = QWidget()
        analysis.setObjectName("AnalysisPanel")
        av = QVBoxLayout(analysis)
        av.setContentsMargins(12, 18, 18, 18)
        av.setSpacing(8)

        analysis_title = QLabel("Visualization")
        analysis_title.setObjectName("AnalysisTitle")
        av.addWidget(analysis_title)

        self.right_tabs = QTabWidget()
        self.right_tabs.setDocumentMode(True)

        plot_widget = QWidget()
        pv = QVBoxLayout(plot_widget)
        pv.setContentsMargins(0, 4, 0, 0)
        pv.setSpacing(4)
        self.figure = Figure(figsize=(7.5, 6), constrained_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        toolbar = NavigationToolbar(self.canvas, self)
        toolbar.setObjectName("PlotToolbar")
        pv.addWidget(toolbar)
        pv.addWidget(self.canvas, 1)
        self.right_tabs.addTab(plot_widget, "Plot")

        activity_widget = QWidget()
        actv = QVBoxLayout(activity_widget)
        actv.setContentsMargins(4, 8, 4, 4)
        actv.addWidget(QLabel("Run log / FEFFIT report"))
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(10000)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        self.console.setFont(mono)
        actv.addWidget(self.console, 1)
        self.right_tabs.addTab(activity_widget, "Activity")

        av.addWidget(self.right_tabs, 1)

        split.addWidget(work)
        split.addWidget(analysis)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([560, 850])

        # Status bar
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

        engine = QLabel("XrayLarch + Feff8L")
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

        quick = QLabel(
            "Workflow\n"
            "Structure → FEFF paths → Preview → Experimental fit"
        )
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

    # ------------------------------------------------------------------
    # Reusable UI helpers
    # ------------------------------------------------------------------
    def _apply_style(self):
        QApplication.setStyle("Fusion")
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #f5f7fa;
                color: #17202a;
                font-size: 10.5pt;
            }
            QMenuBar {
                background: #ffffff;
                border-bottom: 1px solid #dfe4ea;
            }
            QMenuBar::item:selected, QMenu::item:selected {
                background: #eaf1fb;
            }

            #Sidebar {
                background: #202938;
                border: none;
            }
            #Brand {
                color: #ffffff;
                font-size: 19pt;
                font-weight: 700;
                line-height: 1.0;
            }
            #EngineLabel {
                color: #9fb0c3;
                font-size: 9pt;
            }
            #SidebarHint {
                color: #9fb0c3;
                font-size: 9pt;
                line-height: 1.35;
                padding: 8px 2px;
            }
            QPushButton#NavButton {
                background: transparent;
                color: #cbd5e1;
                border: 0;
                border-radius: 6px;
                text-align: left;
                padding: 11px 12px;
                font-weight: 600;
            }
            QPushButton#NavButton:hover {
                background: #2c3748;
                color: #ffffff;
            }
            QPushButton#NavButton:checked {
                background: #334155;
                color: #ffffff;
            }
            QPushButton#SidebarSecondary {
                background: #2c3748;
                color: #dbe5f0;
                border: 1px solid #435269;
                border-radius: 6px;
                padding: 8px;
            }

            #WorkPanel, #AnalysisPanel {
                background: #f5f7fa;
            }
            #PageTitle {
                color: #17202a;
                font-size: 18pt;
                font-weight: 700;
            }
            #PageSubtitle {
                color: #667085;
                font-size: 9.5pt;
            }
            #AnalysisTitle {
                color: #17202a;
                font-size: 14pt;
                font-weight: 700;
            }

            QGroupBox {
                background: #ffffff;
                border: 1px solid #dfe4ea;
                border-radius: 8px;
                margin-top: 14px;
                padding: 14px 12px 12px 12px;
                font-weight: 650;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #344054;
                background: #f5f7fa;
            }

            QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QPlainTextEdit,
            QTableWidget, QTextBrowser {
                background: #ffffff;
                border: 1px solid #cfd6df;
                border-radius: 5px;
                padding: 5px 7px;
                selection-background-color: #3973b8;
            }
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus,
            QSpinBox:focus, QPlainTextEdit:focus, QTableWidget:focus {
                border: 1px solid #3973b8;
            }

            QPushButton {
                background: #ffffff;
                border: 1px solid #c9d2dc;
                border-radius: 6px;
                padding: 7px 11px;
                min-height: 18px;
            }
            QPushButton:hover {
                background: #f0f4f8;
                border-color: #aeb8c4;
            }
            QPushButton[primary="true"] {
                background: #2f6fb3;
                color: #ffffff;
                border-color: #2f6fb3;
                font-weight: 650;
            }
            QPushButton[primary="true"]:hover {
                background: #285f99;
            }

            QTabWidget::pane {
                background: #ffffff;
                border: 1px solid #dfe4ea;
                border-radius: 7px;
            }
            QTabBar::tab {
                background: #e9edf2;
                color: #52606f;
                border: 0;
                padding: 8px 14px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #17202a;
                font-weight: 650;
            }

            QHeaderView::section {
                background: #eef2f6;
                color: #344054;
                border: 0;
                border-bottom: 1px solid #d8dee6;
                padding: 7px;
                font-weight: 650;
            }
            QTableWidget {
                gridline-color: #edf0f3;
            }
            #PlotToolbar {
                background: #ffffff;
                border: 0;
            }
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

    def _form_row(
        self,
        layout: QGridLayout,
        row: int,
        label: str,
        widget: QWidget,
        help_text: str = "",
    ):
        lab = QLabel(label)
        lab.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        if help_text:
            lab.setToolTip(help_text)
            widget.setToolTip(help_text)
        layout.addWidget(lab, row, 0)
        layout.addWidget(widget, row, 1)
        layout.setColumnStretch(1, 1)

    def _pair_grid(self, items):
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        for idx, (label, widget, help_text) in enumerate(items):
            col = (idx % 2) * 2
            row = idx // 2
            lab = QLabel(label)
            lab.setToolTip(help_text)
            widget.setToolTip(help_text)
            grid.addWidget(lab, row, col)
            grid.addWidget(widget, row, col + 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        return grid

    # ------------------------------------------------------------------
    # Page 1: Structure + Feff8L
    # ------------------------------------------------------------------
    def _structure_page(self):
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        structure_box = QGroupBox("Structure model")
        grid = QGridLayout(structure_box)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(9)

        self.structure_path = QLineEdit()
        self.structure_path.setPlaceholderText("Select a CIF / POSCAR / CONTCAR...")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.open_structure)
        file_row = QWidget()
        file_layout = QHBoxLayout(file_row)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.setSpacing(7)
        file_layout.addWidget(self.structure_path, 1)
        file_layout.addWidget(browse)
        self._form_row(
            grid, 0, "Structure file", file_row,
            "Load a CIF, POSCAR, CONTCAR, CSSR, or another structure supported by Larch/pymatgen."
        )

        self.absorber = QComboBox()
        self.absorber.currentTextChanged.connect(self.refresh_absorber_sites)
        self._form_row(grid, 1, "Absorber", self.absorber, "Absorbing element for the FEFF calculation.")

        self.abs_site = QComboBox()
        self._form_row(
            grid, 2, "Absorber site", self.abs_site,
            "Choose the crystallographic absorber site when the element occupies multiple sites."
        )

        model_params = QWidget()
        model_params.setLayout(self._pair_grid([
            ("Edge", self._edge_combo(), "Absorption edge used by Feff8L."),
            ("Cluster radius", self._cluster_spin(), "Atom-cluster radius around the absorber."),
        ]))
        self._form_row(grid, 3, "FEFF model", model_params, "Core FEFF model controls.")

        self.include_h = QCheckBox("Include hydrogen atoms in the generated cluster")
        self._form_row(
            grid, 4, "Hydrogen", self.include_h,
            "Usually disabled for inorganic catalyst EXAFS models."
        )

        outer.addWidget(structure_box)

        run_box = QGroupBox("Run folder and actions")
        rg = QGridLayout(run_box)
        self.run_dir = QLineEdit(str(self.engine.run_dir))
        runbrowse = QPushButton("Choose...")
        runbrowse.clicked.connect(self.choose_run_dir)
        run_row = QWidget()
        rr = QHBoxLayout(run_row)
        rr.setContentsMargins(0, 0, 0, 0)
        rr.setSpacing(7)
        rr.addWidget(self.run_dir, 1)
        rr.addWidget(runbrowse)
        self._form_row(
            rg, 0, "Run directory", run_row,
            "Folder containing feff.inp, paths.dat, files.dat and feffNNNN.dat."
        )

        actions = QHBoxLayout()
        gen = QPushButton("Generate feff.inp")
        gen.clicked.connect(self.generate_input)
        run = self._make_primary(QPushButton("Run Feff8L"))
        run.clicked.connect(self.run_feff)
        export = QPushButton("Export run ZIP")
        export.clicked.connect(self.export_run_zip)
        actions.addWidget(gen)
        actions.addWidget(run)
        actions.addWidget(export)
        actions.addStretch(1)
        rg.addLayout(actions, 1, 0, 1, 2)
        outer.addWidget(run_box)

        editor_box = QGroupBox("Generated FEFF input")
        ev = QVBoxLayout(editor_box)
        note = QLabel("Editable before running. Changes are written back to feff.inp.")
        note.setObjectName("PageSubtitle")
        ev.addWidget(note)
        self.feff_editor = QPlainTextEdit()
        self.feff_editor.setPlaceholderText(
            "Load a structure and click “Generate feff.inp”.\n\n"
            "The generated Feff8L input will appear here."
        )
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        self.feff_editor.setFont(mono)
        self.feff_editor.setMinimumHeight(250)
        ev.addWidget(self.feff_editor, 1)
        outer.addWidget(editor_box, 1)

        return self._scroll(content)

    def _edge_combo(self):
        self.edge = QComboBox()
        self.edge.addItems(["K", "L3", "L2", "L1"])
        self.edge.setCurrentText("L3")
        return self.edge

    def _cluster_spin(self):
        self.cluster = QDoubleSpinBox()
        self.cluster.setRange(2.0, 15.0)
        self.cluster.setValue(8.0)
        self.cluster.setSingleStep(0.5)
        self.cluster.setSuffix(" Å")
        return self.cluster

    # ------------------------------------------------------------------
    # Page 2: Paths
    # ------------------------------------------------------------------
    def _paths_page(self):
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        controls = QGroupBox("Path selection")
        cv = QVBoxLayout(controls)

        top = QHBoxLayout()
        self.path_filter = QComboBox()
        self.path_filter.addItems(["All paths", "Single scattering", "Multiple scattering"])
        self.path_filter.currentTextChanged.connect(self.populate_path_table)

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_paths)
        allb = QPushButton("Select all")
        allb.clicked.connect(lambda: self.set_path_checks("all"))
        noneb = QPushButton("Select none")
        noneb.clicked.connect(lambda: self.set_path_checks("none"))
        ssb = QPushButton("Select SS only")
        ssb.clicked.connect(lambda: self.set_path_checks("ss"))

        top.addWidget(QLabel("Show"))
        top.addWidget(self.path_filter)
        top.addStretch(1)
        top.addWidget(refresh)
        cv.addLayout(top)

        select_row = QHBoxLayout()
        select_row.addWidget(allb)
        select_row.addWidget(noneb)
        select_row.addWidget(ssb)
        go_preview = self._make_primary(QPushButton("Preview selected →"))
        go_preview.clicked.connect(lambda: self._switch_page(2))
        select_row.addStretch(1)
        select_row.addWidget(go_preview)
        cv.addLayout(select_row)

        outer.addWidget(controls)

        self.path_table = QTableWidget(0, 7)
        self.path_table.setHorizontalHeaderLabels(
            ["Use", "File", "Type", "NLEG", "Degeneracy", "Reff (Å)", "Geometry"]
        )
        self.path_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.path_table.setAlternatingRowColors(True)
        self.path_table.verticalHeader().setVisible(False)

        header = self.path_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)

        outer.addWidget(self.path_table, 1)
        return w

    # ------------------------------------------------------------------
    # Page 3: Preview
    # ------------------------------------------------------------------
    def _preview_page(self):
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        display_box = QGroupBox("Display")
        dg = QGridLayout(display_box)
        self.preview_mode = QComboBox()
        self.preview_mode.addItems([
            "chi(k)", "k chi(k)", "k^2 chi(k)", "k^3 chi(k)",
            "|chi(R)|", "Re chi(R)", "Im chi(R)"
        ])
        self.preview_mode.setCurrentText("k^3 chi(k)")
        self._form_row(
            dg, 0, "Representation", self.preview_mode,
            "Choose the displayed path representation."
        )
        outer.addWidget(display_box)

        transform_box = QGroupBox("Fourier transform")
        self.pkmin = self._dspin(0, 20, 2.5, 0.1)
        self.pkmax = self._dspin(1, 25, 12.0, 0.1)
        self.pkw = QSpinBox()
        self.pkw.setRange(0, 3)
        self.pkw.setValue(3)
        self.pdk = self._dspin(0, 5, 1.0, 0.1)
        self.pwindow = QComboBox()
        self.pwindow.addItems(["hanning", "kaiser", "parzen", "welch", "sine"])
        transform_box.setLayout(self._pair_grid([
            ("k min", self.pkmin, "Lower k limit."),
            ("k max", self.pkmax, "Upper k limit."),
            ("k weight", self.pkw, "FT k weighting."),
            ("dk", self.pdk, "Window taper width."),
            ("Window", self.pwindow, "FT window function."),
        ]))
        outer.addWidget(transform_box)

        path_box = QGroupBox("Path parameters")
        self.ps02 = self._dspin(0, 2, 1.0, 0.01)
        self.pe0 = self._dspin(-30, 30, 0.0, 0.1)
        self.pdr = self._dspin(-0.5, 0.5, 0.0, 0.001, decimals=4)
        self.psig = self._dspin(0, 0.1, 0.003, 0.0005, decimals=5)
        path_box.setLayout(self._pair_grid([
            ("S0²", self.ps02, "Amplitude reduction factor for path preview."),
            ("ΔE0 (eV)", self.pe0, "Energy shift."),
            ("ΔR (Å)", self.pdr, "Path-length shift."),
            ("σ² (Å²)", self.psig, "Debye-Waller factor."),
        ]))
        outer.addWidget(path_box)

        options = QGroupBox("Series")
        oh = QHBoxLayout(options)
        self.show_individual = QCheckBox("Individual paths")
        self.show_individual.setChecked(True)
        self.show_sum = QCheckBox("Summed path signal")
        self.show_sum.setChecked(True)
        oh.addWidget(self.show_individual)
        oh.addWidget(self.show_sum)
        oh.addStretch(1)
        outer.addWidget(options)

        actions = QHBoxLayout()
        pb = self._make_primary(QPushButton("Plot selected paths"))
        pb.clicked.connect(self.plot_preview)
        csvb = QPushButton("Save plotted data")
        csvb.clicked.connect(self.save_preview_csv)
        figb = QPushButton("Save figure")
        figb.clicked.connect(self.save_figure)
        actions.addWidget(pb)
        actions.addWidget(csvb)
        actions.addWidget(figb)
        actions.addStretch(1)
        outer.addLayout(actions)
        outer.addStretch(1)

        return self._scroll(content)

    # ------------------------------------------------------------------
    # Page 4: Data + FEFFIT
    # ------------------------------------------------------------------
    def _fit_page(self):
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        data_box = QGroupBox("Experimental XAS data")
        dg = QGridLayout(data_box)

        self.data_path = QLineEdit()
        self.data_path.setPlaceholderText("Select ASCII / XDI / Athena project...")
        db = QPushButton("Browse...")
        db.clicked.connect(self.open_xas_data)
        drow = QWidget()
        dhl = QHBoxLayout(drow)
        dhl.setContentsMargins(0, 0, 0, 0)
        dhl.setSpacing(7)
        dhl.addWidget(self.data_path, 1)
        dhl.addWidget(db)
        self._form_row(dg, 0, "XAS file", drow, "Load ASCII/XDI data or an Athena project.")

        self.data_group = QComboBox()
        self.data_group.currentTextChanged.connect(self.select_data_group)
        self._form_row(
            dg, 1, "Data group", self.data_group,
            "Spectrum selected from the loaded file or Athena project."
        )
        outer.addWidget(data_box)

        transform_box = QGroupBox("Data reduction and fit range")
        self.frbkg = self._dspin(0.2, 3.0, 1.0, 0.05)
        self.fkmin = self._dspin(0, 20, 3.0, 0.1)
        self.fkmax = self._dspin(1, 25, 11.0, 0.1)
        self.fkw = QSpinBox()
        self.fkw.setRange(0, 3)
        self.fkw.setValue(3)
        self.fdk = self._dspin(0, 5, 1.0, 0.1)
        self.frmin = self._dspin(0, 10, 1.0, 0.05)
        self.frmax = self._dspin(0, 10, 3.2, 0.05)

        transform_box.setLayout(self._pair_grid([
            ("Rbkg (Å)", self.frbkg, "AUTOBK background cutoff."),
            ("k min", self.fkmin, "Lower k boundary."),
            ("k max", self.fkmax, "Upper k boundary."),
            ("k weight", self.fkw, "k weighting used for FEFFIT."),
            ("dk", self.fdk, "Transform window taper."),
            ("R min (Å)", self.frmin, "Lower R-space fit boundary."),
            ("R max (Å)", self.frmax, "Upper R-space fit boundary."),
        ]))
        outer.addWidget(transform_box)

        model_box = QGroupBox("Fit model")
        mg = QGridLayout(model_box)
        self.fs02 = self._dspin(0.2, 1.5, 0.9, 0.01)
        self._form_row(
            mg, 0, "Initial S0²", self.fs02,
            "Usually fixed after calibration to a reference foil."
        )

        self.fs02vary = QCheckBox("Vary S0² during fit")
        self.fs02vary.setChecked(False)
        self._form_row(
            mg, 1, "Amplitude", self.fs02vary,
            "Avoid freely varying S0² and N together unless justified."
        )

        self.fvaryn = QCheckBox("Fit path degeneracy / apparent coordination N")
        self.fvaryn.setChecked(True)
        self._form_row(
            mg, 2, "Coordination", self.fvaryn,
            "Uses FEFF degeneracy as the initial value."
        )
        outer.addWidget(model_box)

        actions = QHBoxLayout()
        proc = QPushButton("Process data")
        proc.clicked.connect(self.process_data)
        fit = self._make_primary(QPushButton("Run FEFFIT"))
        fit.clicked.connect(self.run_fit)
        save = QPushButton("Save fit table")
        save.clicked.connect(self.save_fit_table)
        actions.addWidget(proc)
        actions.addWidget(fit)
        actions.addWidget(save)
        actions.addStretch(1)
        outer.addLayout(actions)

        report_box = QGroupBox("Latest fit summary")
        rv = QVBoxLayout(report_box)
        self.fit_notes = QPlainTextEdit()
        self.fit_notes.setReadOnly(True)
        self.fit_notes.setPlaceholderText(
            "The numerical FEFFIT report will appear here after fitting.\n"
            "The full activity log is also available in the right-side Activity tab."
        )
        self.fit_notes.setMinimumHeight(150)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        self.fit_notes.setFont(mono)
        rv.addWidget(self.fit_notes)
        outer.addWidget(report_box, 1)

        return self._scroll(content)

    # ------------------------------------------------------------------
    # Generic helpers / actions
    # ------------------------------------------------------------------
    def _dspin(self, lo, hi, val, step, decimals=2):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        s.setSingleStep(step)
        s.setDecimals(decimals)
        return s

    def log(self, text):
        self.console.appendPlainText(str(text).rstrip())

    def show_help(self):
        d = QDialog(self)
        d.setWindowTitle("OpenEXAFS Studio Help")
        d.resize(860, 700)
        v = QVBoxLayout(d)
        b = QTextBrowser()
        b.setHtml(HELP_HTML)
        v.addWidget(b)
        d.exec()

    def show_about(self):
        QMessageBox.information(
            self,
            "About",
            "OpenEXAFS Studio v0.2.0\n"
            "XrayLarch + Feff8L\n"
            "Open-source EXAFS structure, path preview, and FEFFIT workflow."
        )

    def open_structure(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open structure",
            "",
            "Structures (*.cif *.CIF POSCAR CONTCAR *.cssr *.xyz *.vasp);;All files (*)",
        )
        if not path:
            return
        try:
            self.structure_path.setText(path)
            info = self.engine.load_structure(path)
            self.absorber.clear()
            self.absorber.addItems(info.elements)
            for e in ["Pt", "Au", "Ir"]:
                if e in info.elements:
                    self.absorber.setCurrentText(e)
                    break
            self.refresh_absorber_sites()
            self.log(f"Loaded structure: {info.formula}; {len(info.sites)} sites")
            self.statusBar().showMessage(f"Structure loaded: {info.formula}", 5000)
        except Exception as exc:
            self._error(exc)

    def refresh_absorber_sites(self):
        self.abs_site.clear()
        absorber = self.absorber.currentText()
        for site in self.engine.absorber_sites(absorber):
            self.abs_site.addItem(
                f"Site {site.index}: {site.species} | {site.coordinates}",
                site.index,
            )

    def choose_run_dir(self):
        path = QFileDialog.getExistingDirectory(
            self,
            "Choose Feff run directory",
            self.run_dir.text(),
        )
        if path:
            self.run_dir.setText(path)
            self.engine.set_run_dir(path)

    def _sync_run_dir(self):
        self.engine.set_run_dir(self.run_dir.text())

    def generate_input(self):
        try:
            self._sync_run_dir()
            text = self.engine.generate_feff_input(
                self.absorber.currentText(),
                self.edge.currentText(),
                self.cluster.value(),
                self.abs_site.currentData(),
                self.include_h.isChecked(),
            )
            self.feff_editor.setPlainText(text)
            self.engine.save_feff_input(text)
            self.log(f"Generated {self.engine.run_dir / 'feff.inp'}")
        except Exception as exc:
            self._error(exc)

    def run_feff(self):
        try:
            self._sync_run_dir()
            text = self.feff_editor.toPlainText().strip()
            if not text:
                self.generate_input()
                text = self.feff_editor.toPlainText().strip()
            if not text:
                return
            self._start_task(
                "Running Feff8L...",
                self.engine.run_feff8l,
                text,
                False,
                callback=self._after_feff,
            )
        except Exception as exc:
            self._error(exc)

    def _after_feff(self, records):
        self.path_records = records
        self.populate_path_table()
        self.log(f"Feff8L finished. Found {len(records)} feffNNNN.dat paths.")
        self._switch_page(1)
        self.statusBar().showMessage(
            f"Feff8L complete: {len(records)} paths found", 7000
        )

    def refresh_paths(self):
        try:
            self.path_records = self.engine.scan_paths()
            self.populate_path_table()
        except Exception as exc:
            self._error(exc)

    def populate_path_table(self):
        if not hasattr(self, "path_table"):
            return
        filt = self.path_filter.currentText() if hasattr(self, "path_filter") else "All paths"
        records = []
        for r in self.path_records:
            if filt == "Single scattering" and r.kind != "SS":
                continue
            if filt == "Multiple scattering" and r.kind != "MS":
                continue
            records.append(r)

        self.path_table.setRowCount(len(records))
        for row, r in enumerate(records):
            use = QTableWidgetItem()
            use.setFlags(use.flags() | Qt.ItemIsUserCheckable)
            use.setCheckState(Qt.Checked)
            use.setData(Qt.UserRole, r.filename)
            self.path_table.setItem(row, 0, use)

            vals = [
                Path(r.filename).name,
                r.kind,
                str(r.nleg),
                f"{r.degen:.3g}",
                f"{r.reff:.5f}",
                r.geometry,
            ]
            for col, val in enumerate(vals, start=1):
                self.path_table.setItem(row, col, QTableWidgetItem(val))

    def set_path_checks(self, mode):
        for row in range(self.path_table.rowCount()):
            item = self.path_table.item(row, 0)
            kind = self.path_table.item(row, 2).text()
            state = (
                Qt.Checked
                if mode == "all" or (mode == "ss" and kind == "SS")
                else Qt.Unchecked
            )
            item.setCheckState(state)

    def selected_paths(self):
        paths = []
        for row in range(self.path_table.rowCount()):
            item = self.path_table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                paths.append(item.data(Qt.UserRole))
        return paths

    def _preview_settings(self):
        return PreviewSettings(
            self.pkmin.value(),
            self.pkmax.value(),
            self.pkw.value(),
            self.pdk.value(),
            self.pwindow.currentText(),
            self.ps02.value(),
            self.pe0.value(),
            self.pdr.value(),
            self.psig.value(),
        )

    def plot_preview(self):
        paths = self.selected_paths()
        if not paths:
            QMessageBox.warning(
                self,
                "No paths",
                "Select at least one path on the Paths page.",
            )
            return
        try:
            payload = self.engine.build_preview(paths, self._preview_settings())
            self.preview_payload = payload
            self._draw_preview(payload)
            self.right_tabs.setCurrentIndex(0)
        except Exception as exc:
            self._error(exc)

    def _draw_preview(self, payload):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        mode = self.preview_mode.currentText()
        isr = mode in {"|chi(R)|", "Re chi(R)", "Im chi(R)"}
        power = {
            "chi(k)": 0,
            "k chi(k)": 1,
            "k^2 chi(k)": 2,
            "k^3 chi(k)": 3,
        }.get(mode, 0)
        ykey = {
            "|chi(R)|": "chir_mag",
            "Re chi(R)": "chir_re",
            "Im chi(R)": "chir_im",
        }.get(mode, "chi")

        if self.show_individual.isChecked():
            for s in payload["series"]:
                x = s["r"] if isr else s["k"]
                y = s[ykey]
                y = y if isr else y * (x ** power)
                ax.plot(x, y, lw=1.0, alpha=0.78, label=s["label"])

        if self.show_sum.isChecked() and payload.get("sum"):
            s = payload["sum"]
            x = s["r"] if isr else s["k"]
            y = s[ykey]
            y = y if isr else y * (x ** power)
            ax.plot(x, y, lw=2.4, color="black", label="Sum")

        ax.set_xlabel("R (Å)" if isr else r"k (Å$^{-1}$)")
        ax.set_ylabel(mode)
        ax.axhline(0, color="0.75", lw=0.7)
        ax.legend(fontsize=8, ncol=2)
        ax.set_title(
            f"Feff8L path preview | k = {self.pkmin.value():.1f}–"
            f"{self.pkmax.value():.1f} Å⁻¹ | ΔE0 = {self.pe0.value():.2f} eV"
        )
        self.canvas.draw_idle()

    def _draw_empty_state(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_axis_off()
        ax.text(
            0.5,
            0.57,
            "OpenEXAFS Studio",
            ha="center",
            va="center",
            fontsize=20,
            fontweight="bold",
            color="#334155",
            transform=ax.transAxes,
        )
        ax.text(
            0.5,
            0.47,
            "Load a structure, run Feff8L, then preview paths or fit experimental XAS data.",
            ha="center",
            va="center",
            fontsize=10.5,
            color="#7a8697",
            transform=ax.transAxes,
            wrap=True,
        )
        ax.text(
            0.5,
            0.39,
            "The plot area updates automatically as you move through the workflow.",
            ha="center",
            va="center",
            fontsize=9.5,
            color="#98a2b3",
            transform=ax.transAxes,
        )
        self.canvas.draw_idle()

    def save_preview_csv(self):
        if not self.preview_payload:
            QMessageBox.warning(self, "No plot", "Plot paths first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save plotted data",
            "openexafs_paths.csv",
            "CSV (*.csv)",
        )
        if path:
            try:
                out = self.engine.export_preview_csv(
                    self.preview_payload,
                    self.preview_mode.currentText(),
                    path,
                )
                self.log(f"Saved {out}")
            except Exception as exc:
                self._error(exc)

    def save_figure(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save figure",
            "openexafs_plot.png",
            "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)",
        )
        if path:
            try:
                self.figure.savefig(
                    path,
                    dpi=600,
                    bbox_inches="tight",
                    facecolor="white",
                )
                self.log(f"Saved figure: {path}")
            except Exception as exc:
                self._error(exc)

    def export_run_zip(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Feff run",
            "feff8l_run.zip",
            "ZIP (*.zip)",
        )
        if path:
            try:
                out = self.engine.export_run_zip(path)
                self.log(f"Exported run: {out}")
            except Exception as exc:
                self._error(exc)

    def open_xas_data(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open XAS data",
            "",
            "XAS data (*.prj *.athena *.xdi *.dat *.txt *.csv);;All files (*)",
        )
        if not path:
            return
        try:
            self.data_path.setText(path)
            self.xas_groups = self.engine.load_xas_file(path)
            self.data_group.clear()
            self.data_group.addItems(list(self.xas_groups))
            self.select_data_group(self.data_group.currentText())
            self.log(f"Loaded {len(self.xas_groups)} XAS group(s) from {path}")
            self._switch_page(3)
        except Exception as exc:
            self._error(exc)

    def select_data_group(self, name):
        self.current_group = self.xas_groups.get(name)

    def _fit_settings(self):
        return FitSettings(
            rbkg=self.frbkg.value(),
            kmin=self.fkmin.value(),
            kmax=self.fkmax.value(),
            kweight=self.fkw.value(),
            dk=self.fdk.value(),
            window="hanning",
            rmin=self.frmin.value(),
            rmax=self.frmax.value(),
            s02_init=self.fs02.value(),
            s02_vary=self.fs02vary.isChecked(),
            vary_degen=self.fvaryn.isChecked(),
        )

    def process_data(self):
        if self.current_group is None:
            QMessageBox.warning(self, "No data", "Load and select XAS data first.")
            return
        try:
            self.engine.process_group(self.current_group, self._fit_settings())
            self._draw_data(self.current_group)
            self.log("Processed data with Larch pre_edge + autobk + xftf.")
        except Exception as exc:
            self._error(exc)

    def _draw_data(self, g):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        k = np.asarray(g.k)
        chi = np.asarray(g.chi)
        kw = self.fkw.value()
        ax.plot(k, (k ** kw) * chi, lw=1.5)
        ax.set_xlabel(r"k (Å$^{-1}$)")
        ax.set_ylabel(fr"k$^{kw}$ χ(k)")
        ax.set_title(self.data_group.currentText() or "XAS data")
        self.canvas.draw_idle()
        self.right_tabs.setCurrentIndex(0)

    def run_fit(self):
        if self.current_group is None:
            QMessageBox.warning(
                self,
                "No data",
                "Load and process XAS data first.",
            )
            return
        paths = self.selected_paths()
        if not paths:
            QMessageBox.warning(
                self,
                "No paths",
                "Select fitting paths on the Paths page.",
            )
            return
        try:
            self.engine.process_group(self.current_group, self._fit_settings())
            self._start_task(
                "Running Larch FEFFIT...",
                self.engine.fit_paths,
                self.current_group,
                paths,
                self._fit_settings(),
                callback=self._after_fit,
            )
        except Exception as exc:
            self._error(exc)

    def _after_fit(self, payload):
        self.last_fit = payload
        report = payload["report"]
        self.fit_notes.setPlainText(report)
        self.log(report)
        self._draw_fit(payload)
        self.right_tabs.setCurrentIndex(0)

    def _draw_fit(self, payload):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        d = payload["dataset"]
        data = getattr(d, "data", self.current_group)
        model = getattr(d, "model", None)

        if hasattr(data, "r") and hasattr(data, "chir_mag"):
            ax.plot(data.r, data.chir_mag, "o", ms=3, label="data |χ(R)|")
        if model is not None and hasattr(model, "r") and hasattr(model, "chir_mag"):
            ax.plot(model.r, model.chir_mag, lw=2, label="fit |χ(R)|")

        ax.axvspan(
            self.frmin.value(),
            self.frmax.value(),
            color="0.8",
            alpha=0.25,
            label="fit interval",
        )
        ax.set_xlim(0, max(5.0, self.frmax.value() + 1))
        ax.set_xlabel("R (Å)")
        ax.set_ylabel("|χ(R)|")
        ax.legend()
        ax.set_title("Larch FEFFIT result")
        self.canvas.draw_idle()

    def save_fit_table(self):
        if not self.last_fit:
            QMessageBox.warning(self, "No fit", "Run a fit first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save fit parameters",
            "feffit_parameters.csv",
            "CSV (*.csv)",
        )
        if path:
            try:
                out = self.engine.save_fit_table(self.last_fit, path)
                self.log(f"Saved fit table: {out}")
            except Exception as exc:
                self._error(exc)

    def _start_task(self, label, func, *args, callback=None):
        self.statusBar().showMessage(label)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.worker = TaskThread(func, *args)
        self.worker.done.connect(
            lambda result: self._task_done(result, callback)
        )
        self.worker.failed.connect(self._task_failed)
        self.worker.start()

    def _task_done(self, result, callback):
        self.progress.hide()
        self.statusBar().showMessage("Ready")
        if callback:
            callback(result)

    def _task_failed(self, trace):
        self.progress.hide()
        self.statusBar().showMessage("Failed")
        self.log(trace)
        QMessageBox.critical(
            self,
            "Task failed",
            trace.splitlines()[-1] if trace else "Unknown error",
        )

    def _error(self, exc):
        self.log(traceback.format_exc())
        QMessageBox.critical(self, "OpenEXAFS Studio", str(exc))


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("OpenEXAFS Studio")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
