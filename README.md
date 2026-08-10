# OpenEXAFS Studio

**CIF / structure -> Feff8L -> XrayLarch path modeling and FEFFIT**

OpenEXAFS Studio is a research-oriented Python GUI for a fully open EXAFS workflow built around
[XrayLarch](https://xraypy.github.io/xraylarch/) and the Feff8L EXAFS engine distributed for use
with Larch.

> Scientific scope: Feff8L is for EXAFS calculations. OpenEXAFS Studio does not claim to replace
> full FEFF9 XANES calculations.

## What it does

- Load CIF / crystal structures supported by Larch and pymatgen
- Select absorber, crystallographic absorber site, and K/L edge
- Generate editable Feff8L `feff.inp`
- Run Feff8L from the Larch installation
- Browse `feffNNNN.dat` paths with SS/MS filtering
- Select all, none, or single-scattering paths
- Preview `chi(k)`, `k chi(k)`, `k^2 chi(k)`, `k^3 chi(k)`, `|chi(R)|`, `Re chi(R)`, and `Im chi(R)`
- Preview S0^2, Delta E0, Delta R, and sigma^2
- Export plot data to CSV and figures to PNG/PDF/SVG
- Export a conventional Feff run folder as ZIP
- Load ASCII/XDI-style spectra and Athena project files
- Process data with Larch `pre_edge`, `autobk`, and `xftf`
- Fit selected FEFF paths with Larch FEFFIT in R space
- Desktop PySide6 application plus a Streamlit browser edition

## Quick start on Windows

For the easiest local setup, double-click `INSTALL_AND_RUN.bat`. It creates a local virtual environment, installs the desktop dependencies, and launches the GUI.

Manual setup:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
python launch.py
```

The first dependency installation is large because XrayLarch, Qt, and crystallographic packages
are scientific Python stacks.

## One-click-ish GitHub publish

The package includes `PUBLISH_TO_GITHUB.bat`. Double-click it from Windows Explorer. It will:

1. verify Git and GitHub CLI (`gh`),
2. ask GitHub CLI to authenticate when needed,
3. create `sebalaghi/OpenEXAFS-Studio` as a public repository when it does not exist,
4. push the project to `main`, and
5. open the repository and GitHub Pages settings/actions links.

GitHub Pages hosts the static project landing page from `site/`. GitHub Pages cannot execute the
Python/Feff8L application itself. For a browser-running app, deploy `streamlit_app.py` with
Streamlit Community Cloud from the same repository.

See [docs/DEPLOY.md](docs/DEPLOY.md) for exact deployment steps.

## Desktop versus web

The desktop application is the reference research workflow because it can execute the native Feff8L
binary locally. The Streamlit version provides the same structure/path/preview/fitting concepts in a
browser, but hosted platforms may restrict or omit the native Feff8L executable.

## Project structure

```text
openexafs_studio/core.py          Larch/Feff8L workflow engine
openexafs_studio/main_window.py   PySide6 desktop GUI
streamlit_app.py                  browser edition
site/                             GitHub Pages landing site
examples/                         sample structures
docs/                             deployment and scientific notes
```

## Citation

Please cite XrayLarch and the FEFF methodology used by your scientific work. See `CITATION.cff` and
`docs/SCIENTIFIC_NOTES.md`.

## License

OpenEXAFS Studio application code is MIT licensed. XrayLarch, Feff8L, pymatgen, Qt/PySide, and other
dependencies retain their own upstream licenses. No FEFF9 binaries or licensed FEFF9 components are
included in this repository.


## Windows startup troubleshooting

For Windows, use `INSTALL_AND_RUN.bat`. Version 0.1.1 performs an explicit
startup smoke test before launching the GUI and does not silently ignore failed
`pip` or Python commands.

After the first successful installation, use `RUN_GUI.bat` for normal startup.

If the GUI does not open, run `DIAGNOSTIC.bat`. It checks Python, NumPy,
Matplotlib, PySide6 / Qt, XrayLarch, pymatgen, larixite, and the OpenEXAFS
modules and writes `OpenEXAFS_diagnostic.log`.

The installer also writes `OpenEXAFS_install.log`. A startup exception that
occurs before Qt can open is written to `OpenEXAFS_launch_error.log` and is
shown in a native Windows error dialog when possible.

OpenEXAFS Studio currently selects Python 3.13 first, then 3.12 or 3.11. Python
3.14 is not selected by the installer because the project currently declares
support through Python 3.13.


## Windows installation v0.1.2

`INSTALL_AND_RUN.bat` is now self-bootstrapping. A system Python installation is
not required. When no suitable XrayLarch runtime is found, the installer creates
a Miniforge-based XrayLarch environment following the current official Larch
Windows installation recipe, installs the OpenEXAFS GUI dependencies, runs a
startup smoke test, and launches the application.

After installation use `RUN_GUI.bat`. For troubleshooting use `DIAGNOSTIC.bat`.


## v0.2.0 interface redesign

The desktop application now uses a practical three-zone layout: a persistent
workflow navigator on the left, step-specific controls in the center, and
visualization/activity on the right. Structure generation, path selection,
path preview and FEFFIT remain the four workflow stages, but the controls are
grouped into task-oriented cards instead of compressed top tabs.

The scientific engine and file formats are unchanged from v0.1.6.


## GitHub publisher v0.2.1

Run `PUBLISH_TO_GITHUB.bat` from the extracted project folder. The publisher
uses the authenticated GitHub CLI account, creates `OpenEXAFS-Studio` when it
does not yet exist, repairs the `origin` remote when necessary, pushes `main`,
and then enables / triggers the GitHub Pages workflow.

The publisher checks native command exit codes explicitly so a failed
`gh repo view` is no longer mistaken for an existing repository.
