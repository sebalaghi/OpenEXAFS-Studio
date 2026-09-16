from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable
import os
import re
import shutil
import tempfile
import zipfile

import numpy as np


class OpenEXAFSError(RuntimeError):
    """Raised for user-facing OpenEXAFS Studio errors."""


@dataclass
class StructureSite:
    index: int
    species: str
    coordinates: str


@dataclass
class StructureInfo:
    formula: str
    elements: list[str]
    sites: list[StructureSite]
    fmt: str


@dataclass
class PathRecord:
    index: int
    filename: str
    nleg: int
    degen: float
    reff: float
    geometry: str

    @property
    def kind(self) -> str:
        return "SS" if self.nleg == 2 else "MS"


@dataclass
class PreviewSettings:
    kmin: float = 2.5
    kmax: float = 12.0
    kweight: int = 3
    dk: float = 1.0
    window: str = "hanning"
    s02: float = 1.0
    e0: float = 0.0
    deltar: float = 0.0
    sigma2: float = 0.0


def safe_filename(text: str) -> str:
    out = re.sub(r"[^A-Za-z0-9._-]+", "_", text.strip())
    return out.strip("._") or "output"


def require_larch() -> None:
    try:
        import larch  # noqa: F401
    except Exception as exc:
        raise OpenEXAFSError(
            "XrayLarch is not available in this Python environment. Install the project "
            "dependencies first, for example: pip install -e ."
        ) from exc


def structure_format_from_path(path: str | Path) -> str:
    p = Path(path)
    name = p.name.lower()
    if name in {"poscar", "contcar"}:
        return name
    suffix = p.suffix.lower().lstrip(".")
    return suffix or "cif"


def _species_elements(site: Any) -> list[str]:
    out: list[str] = []
    try:
        for elem in site.species.elements:
            sym = str(elem.symbol)
            if sym not in out:
                out.append(sym)
    except Exception:
        text = str(getattr(site, "species_string", ""))
        for sym in re.findall(r"[A-Z][a-z]?", text):
            if sym not in out:
                out.append(sym)
    return out


class OpenFeffEngine:
    """Thin application layer around XrayLarch and Feff8L.

    The application intentionally stops at FEFF8L path generation and preview.
    Quantitative fitting is left to Artemis or another dedicated EXAFS fitting tool.
    """

    ARTEMIS_METADATA_FILES = (
        "feff.inp",
        "paths.dat",
        "files.dat",
        "list.dat",
        "phase.bin",
        "chi.dat",
        "xsect.bin",
    )

    def __init__(self, run_dir: str | Path | None = None):
        self.structure_path: Path | None = None
        self.structure_text: str | None = None
        self.structure_fmt: str = "cif"
        self.structure_info: StructureInfo | None = None
        self.run_dir = Path(run_dir) if run_dir else Path(tempfile.mkdtemp(prefix="openexafs_"))
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.path_records: list[PathRecord] = []

    def set_run_dir(self, run_dir: str | Path) -> Path:
        self.run_dir = Path(run_dir).expanduser().resolve()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        return self.run_dir

    def load_structure(self, path: str | Path) -> StructureInfo:
        require_larch()
        from larch.xrd.structure2feff import read_structure

        path = Path(path).expanduser().resolve()
        if not path.exists():
            raise OpenEXAFSError(f"Structure file does not exist: {path}")

        self.structure_path = path
        self.structure_text = path.read_text(encoding="utf-8", errors="replace")
        self.structure_fmt = structure_format_from_path(path)
        struct = read_structure(self.structure_text, fmt=self.structure_fmt)

        formula = str(getattr(getattr(struct, "composition", None), "reduced_formula", "Molecule"))
        elements: list[str] = []
        sites: list[StructureSite] = []
        for idx, site in enumerate(struct.sites, start=1):
            for sym in _species_elements(site):
                if sym not in elements:
                    elements.append(sym)
            species = str(getattr(site, "species_string", "?"))
            coords_obj = getattr(site, "frac_coords", None)
            if coords_obj is None:
                coords_obj = getattr(site, "coords", [0, 0, 0])
            coords = np.asarray(coords_obj, dtype=float)
            ctext = ", ".join(f"{x:.5f}" for x in coords[:3])
            sites.append(StructureSite(idx, species, ctext))

        info = StructureInfo(formula=formula, elements=elements, sites=sites, fmt=self.structure_fmt)
        self.structure_info = info
        return info

    def absorber_sites(self, absorber: str) -> list[StructureSite]:
        if self.structure_info is None:
            return []
        out = []
        for site in self.structure_info.sites:
            if absorber in re.findall(r"[A-Z][a-z]?", site.species):
                out.append(site)
        return out

    def generate_feff_input(
        self,
        absorber: str,
        edge: str = "L3",
        cluster_size: float = 8.0,
        site_index: int | None = None,
        with_h: bool = False,
    ) -> str:
        require_larch()
        from larch.xrd.structure2feff import structure2feffinp

        if not self.structure_text:
            raise OpenEXAFSError("Load a structure file first.")

        text = structure2feffinp(
            self.structure_text,
            absorber=absorber,
            edge=edge,
            cluster_size=float(cluster_size),
            site_index=site_index,
            with_h=bool(with_h),
            version8=True,
            fmt=self.structure_fmt,
            rng_seed=20260810,
            extra_titles=["Generated by OpenEXAFS Studio using XrayLarch / Feff8L"],
        )
        if not text or str(text).lstrip().startswith("# could not"):
            raise OpenEXAFSError("Larch could not generate a Feff8L input from this structure.")
        return str(text)

    def save_feff_input(self, text: str) -> Path:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        path = self.run_dir / "feff.inp"
        path.write_text(text, encoding="utf-8")
        return path

    def run_feff8l(self, input_text: str | None = None, verbose: bool = False) -> list[PathRecord]:
        require_larch()
        from larch.xafs import feff8l

        if input_text is not None:
            self.save_feff_input(input_text)
        inp = self.run_dir / "feff.inp"
        if not inp.exists():
            raise OpenEXAFSError("No feff.inp exists in the current run directory.")

        previous = Path.cwd()
        try:
            # Keep FeffRunner quiet in the desktop application.  XrayLarch's verbose
            # writer uses sys.stdout, which is intentionally absent in a windowed
            # PyInstaller executable.  feff8l() already runs the complete FEFF8L
            # module chain, so a second FeffRunner fallback is unnecessary and can
            # leave feffrun_*.log locked after a failed first attempt on Windows.
            feff8l(folder=str(self.run_dir), feffinp="feff.inp", verbose=False)
        except Exception as exc:
            raise OpenEXAFSError(
                "Feff8L did not run successfully. Confirm that XrayLarch contains the "
                "Feff8L executable and that native executables are allowed on this system."
            ) from exc
        finally:
            os.chdir(previous)

        records = self.scan_paths()
        if not records:
            raise OpenEXAFSError("Feff8L finished but no feffNNNN.dat path files were found.")
        return records

    def scan_paths(self) -> list[PathRecord]:
        require_larch()
        from larch.xafs import feffpath

        records: list[PathRecord] = []
        for path in sorted(self.run_dir.glob("feff[0-9][0-9][0-9][0-9].dat")):
            try:
                p = feffpath(str(path))
                stem_num = int(re.findall(r"(\d{4})", path.name)[0])
                atoms = []
                for atom in getattr(p, "geom", []):
                    try:
                        atoms.append(str(atom[0]))
                    except Exception:
                        pass
                geom = " - ".join(atoms) or "path"
                records.append(
                    PathRecord(
                        index=stem_num,
                        filename=str(path),
                        nleg=int(getattr(p, "nleg", 0)),
                        degen=float(getattr(p, "degen", np.nan)),
                        reff=float(getattr(p, "reff", np.nan)),
                        geometry=geom,
                    )
                )
            except Exception:
                continue
        self.path_records = records
        return records

    def build_preview(
        self,
        path_files: Iterable[str | Path],
        settings: PreviewSettings,
    ) -> dict[str, Any]:
        require_larch()
        from larch import Group
        from larch.xafs import feffpath, path2chi, ff2chi, xftf

        paths = []
        series = []
        for path_file in path_files:
            p = feffpath(str(path_file))
            p.s02 = float(settings.s02)
            p.e0 = float(settings.e0)
            p.deltar = float(settings.deltar)
            p.sigma2 = float(settings.sigma2)
            path2chi(p, kmax=float(settings.kmax))
            xftf(
                p.k,
                p.chi,
                group=p,
                kmin=float(settings.kmin),
                kmax=float(settings.kmax),
                kweight=int(settings.kweight),
                dk=float(settings.dk),
                window=str(settings.window),
            )
            paths.append(p)
            series.append(self._path_payload(p, Path(path_file).name))

        total = None
        if paths:
            gsum = Group(name="sum")
            ff2chi(paths, group=gsum, kmax=float(settings.kmax))
            xftf(
                gsum.k,
                gsum.chi,
                group=gsum,
                kmin=float(settings.kmin),
                kmax=float(settings.kmax),
                kweight=int(settings.kweight),
                dk=float(settings.dk),
                window=str(settings.window),
            )
            total = self._path_payload(gsum, "Sum")

        return {"series": series, "sum": total, "settings": asdict(settings)}

    @staticmethod
    def _path_payload(group: Any, label: str) -> dict[str, Any]:
        def arr(name: str) -> np.ndarray:
            return np.asarray(getattr(group, name, []), dtype=float)

        return {
            "label": label,
            "k": arr("k"),
            "chi": arr("chi"),
            "r": arr("r"),
            "chir_mag": arr("chir_mag"),
            "chir_re": arr("chir_re"),
            "chir_im": arr("chir_im"),
        }

    @staticmethod
    def export_preview_csv(payload: dict[str, Any], mode: str, output: str | Path) -> Path:
        items = list(payload.get("series", []))
        if payload.get("sum") is not None:
            items.append(payload["sum"])
        if not items:
            raise OpenEXAFSError("There is no plotted path data to export.")

        is_r = mode in {"|chi(R)|", "Re chi(R)", "Im chi(R)"}
        xkey = "r" if is_r else "k"
        ykey = {
            "chi(k)": "chi",
            "k chi(k)": "chi",
            "k^2 chi(k)": "chi",
            "k^3 chi(k)": "chi",
            "|chi(R)|": "chir_mag",
            "Re chi(R)": "chir_re",
            "Im chi(R)": "chir_im",
        }[mode]
        power = {"chi(k)": 0, "k chi(k)": 1, "k^2 chi(k)": 2, "k^3 chi(k)": 3}.get(mode, 0)

        base_x = np.asarray(items[0][xkey], dtype=float)
        columns = {xkey: base_x}
        for item in items:
            x = np.asarray(item[xkey], dtype=float)
            y = np.asarray(item[ykey], dtype=float)
            if not is_r and power:
                y = y * (x ** power)
            if x.size != base_x.size or not np.allclose(x, base_x):
                y = np.interp(base_x, x, y)
            columns[safe_filename(item["label"])] = y

        output = Path(output)
        if output.suffix.lower() != ".csv":
            output = output.with_suffix(".csv")
        names = list(columns)
        matrix = np.column_stack([columns[name] for name in names])
        np.savetxt(output, matrix, delimiter=",", header=",".join(names), comments="")
        return output

    def artemis_files(self) -> list[Path]:
        """Return only FEFF8 files useful for importing into Artemis."""
        files: list[Path] = []
        for name in self.ARTEMIS_METADATA_FILES:
            p = self.run_dir / name
            if p.is_file():
                files.append(p)
        files.extend(sorted(self.run_dir.glob("feff[0-9][0-9][0-9][0-9].dat")))
        return files

    def validate_artemis_run(self) -> tuple[bool, str]:
        inp = self.run_dir / "feff.inp"
        paths = sorted(self.run_dir.glob("feff[0-9][0-9][0-9][0-9].dat"))
        if not inp.is_file():
            return False, "Missing feff.inp."
        if not paths:
            return False, "No feffNNNN.dat scattering-path files were found."
        phase_note = "phase.bin present" if (self.run_dir / "phase.bin").is_file() else "no phase.bin (normal for current Feff8L; Artemis patch handles this)"
        return True, f"External-Artemis package ready: feff.inp, {len(paths)} FEFF8 path files, {phase_note}."

    def _synthetic_files_dat(self) -> str:
        paths = sorted(self.run_dir.glob("feff[0-9][0-9][0-9][0-9].dat"))
        lines = [
            "# files.dat compatibility index written by OpenEXAFS Studio",
            "# filename        sig2   amp_ratio",
        ]
        for path in paths:
            lines.append(f"{path.name:<16s}  0.0000  0.0000")
        return "\n".join(lines) + "\n"

    def _artemis_readme(self) -> str:
        ok, status = self.validate_artemis_run()
        return (
            "OpenEXAFS Studio - Artemis external FEFF8 package\n"
            "==================================================\n\n"
            f"{status}\n\n"
            "IMPORTANT: Do NOT import this with Artemis' normal 'a feff.inp file' route "
            "and do not click 'Run Feff'. That creates an Artemis-managed FEFF calculation.\n\n"
            "Artemis 0.9.26 contains an external-FEFF importer, but its menu item is disabled "
            "in the distributed GUI. The OpenEXAFS Studio repository includes "
            "ENABLE_ARTEMIS_EXTERNAL_IMPORT.ps1 to expose that existing importer.\n\n"
            "After enabling it and restarting Artemis:\n"
            "1. File > Import... > an external Feff calculation.\n"
            "2. Select feff.inp from this folder.\n"
            "3. Accept the Artemis warning about external FEFF calculations.\n"
            "4. Artemis should build its path list from the existing feffNNNN.dat files.\n\n"
            "Current Feff8L commonly writes phase.pad rather than the legacy FEFF6-style phase.bin. "
            "The supplied Artemis patch therefore relaxes Demeter's external-import phase.bin check; "
            "the actual fitting theory is read from the existing feffNNNN.dat path files.\n\n"
            "The feffNNNN.dat files are the original Feff8L outputs. OpenEXAFS Studio does "
            "not convert them to FEFF6 and does not ask Artemis to recalculate them.\n"
        )

    def export_artemis_zip(self, output: str | Path) -> Path:
        ok, message = self.validate_artemis_run()
        if not ok:
            raise OpenEXAFSError(message)

        output = Path(output)
        if output.suffix.lower() != ".zip":
            output = output.with_suffix(".zip")
        output.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            names = set()
            for path in self.artemis_files():
                zf.write(path, arcname=path.name)
                names.add(path.name.lower())
            if "files.dat" not in names:
                zf.writestr("files.dat", self._synthetic_files_dat())
            zf.writestr("ARTEMIS_IMPORT.txt", self._artemis_readme())
        return output

    def export_artemis_folder(self, destination: str | Path) -> Path:
        ok, message = self.validate_artemis_run()
        if not ok:
            raise OpenEXAFSError(message)

        destination = Path(destination).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        copied = set()
        for path in self.artemis_files():
            shutil.copy2(path, destination / path.name)
            copied.add(path.name.lower())
        if "files.dat" not in copied:
            (destination / "files.dat").write_text(self._synthetic_files_dat(), encoding="utf-8")
        (destination / "ARTEMIS_IMPORT.txt").write_text(self._artemis_readme(), encoding="utf-8")
        return destination
