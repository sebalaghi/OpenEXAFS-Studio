# OpenEXAFS Studio

**Structure -> Feff8L -> FEFF8 scattering paths -> Artemis**

OpenEXAFS Studio is a focused Python GUI for generating Feff8L EXAFS scattering paths with XrayLarch,
inspecting and previewing those paths, and exporting the original FEFF8 calculation files for use in
Artemis.

The project intentionally does **not** implement its own EXAFS fitting page. Quantitative fitting is
left to Artemis or another dedicated EXAFS fitting environment.

## What it does

- Load CIF and other crystal structures supported by Larch/pymatgen
- Select absorber, crystallographic site, K/L edge, and cluster radius
- Generate editable FEFF8-style `feff.inp`
- Run Feff8L from XrayLarch
- Browse `feffNNNN.dat` paths with SS/MS filtering
- Preview chi(k), k-weighted chi(k), |chi(R)|, Re chi(R), and Im chi(R)
- Export preview data and figures
- Export an **Artemis FEFF8 folder** or **Artemis FEFF8 ZIP**
- Preserve the original Feff8L path files without converting them to FEFF6

## Artemis workflow

After running Feff8L, use the **Artemis export** page.

The export contains:

```text
feff.inp
paths.dat        if generated
files.dat        if generated
list.dat         if generated
phase.bin        if generated
feff0001.dat
feff0002.dat
...
ARTEMIS_IMPORT.txt
```

Then in Artemis:

1. Extract the ZIP if needed.
2. Choose **File -> Import... -> a feff.inp file**.
3. Select the exported `feff.inp`.
4. Keep all `feffNNNN.dat` files in the same folder.

The numerical scattering-path files are the original Feff8L outputs.

Bruce Ravel has noted that externally generated `feffNNNN.dat` files can be used by Artemis
independently of the FEFF version because the relevant path-file format did not change between
FEFF6 and FEFF8.

## Quick start on Windows

```powershell
git clone https://github.com/sebalaghi/OpenEXAFS-Studio.git
cd OpenEXAFS-Studio

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -e .

python launch.py
```

The repository also includes `INSTALL_AND_RUN.bat`, `RUN_GUI.bat`, and diagnostic helpers.

## Scientific scope

Feff8L is used here for EXAFS path calculations. OpenEXAFS Studio does not claim to replace full
FEFF9 XANES calculations.

## Project structure

```text
openexafs_studio/core.py          Feff8L engine and Artemis export
openexafs_studio/main_window.py   PySide6 desktop GUI
streamlit_app.py                  browser edition
site/                             GitHub Pages landing page
examples/                         sample structures
docs/                             deployment and scientific notes
```

## Citation

Please cite XrayLarch and the FEFF methodology used in your scientific work. Software authorship is
listed in `CITATION.cff`.

## License

OpenEXAFS Studio application code is MIT licensed. XrayLarch, Feff8L, pymatgen, Qt/PySide, and
other dependencies retain their upstream licenses.
