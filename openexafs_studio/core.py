from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable
import csv
import json
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


@dataclass
class FitSettings:
    rbkg: float = 1.0
    kmin: float = 3.0
    kmax: float = 11.0
    kweight: int = 3
    dk: float = 1.0
    window: str = "hanning"
    rmin: float = 1.0
    rmax: float = 3.2
    s02_init: float = 0.9
    s02_vary: bool = False
    vary_degen: bool = True
    degen_min: float = 0.0
    degen_max: float = 24.0
    e0_init: float = 0.0
    e0_min: float = -15.0
    e0_max: float = 15.0
    dr_min: float = -0.25
    dr_max: float = 0.25
    sigma2_init: float = 0.003
    sigma2_min: float = 0.0
    sigma2_max: float = 0.03


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


def _group_mu(group: Any) -> np.ndarray:
    for name in ("mu", "mutrans", "mufluor", "xmu", "norm"):
        val = getattr(group, name, None)
        if val is not None:
            arr = np.asarray(val, dtype=float)
            if arr.size > 2:
                if name != "mu":
                    group.mu = arr
                return arr
    raise OpenEXAFSError("Could not find a mu(E) array in the selected data group.")


def _group_energy(group: Any) -> np.ndarray:
    for name in ("energy", "x", "ene"):
        val = getattr(group, name, None)
        if val is not None:
            arr = np.asarray(val, dtype=float)
            if arr.size > 2:
                if name != "energy":
                    group.energy = arr
                return arr
    raise OpenEXAFSError("Could not find an energy array in the selected data group.")


class OpenFeffEngine:
    """Thin application layer around XrayLarch and Feff8L."""

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
            extra_titles=["Generated by OpenEXAFS Studio using XrayLarch"],
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
        from larch.xafs import feff8l, feffrunner

        if input_text is not None:
            self.save_feff_input(input_text)
        inp = self.run_dir / "feff.inp"
        if not inp.exists():
            raise OpenEXAFSError("No feff.inp exists in the current run directory.")

        previous = Path.cwd()
        try:
            try:
                # Current XrayLarch public API for the bundled Feff8L EXAFS engine.
                feff8l(folder=str(self.run_dir), feffinp="feff.inp", verbose=verbose)
            except Exception:
                # Fallback to the lower-level runner used by Larch examples.
                runner = feffrunner(feffinp=inp, verbose=verbose)
                runner.run()
        except Exception as exc:
            raise OpenEXAFSError(
                "Feff8L did not run successfully. Confirm that the XrayLarch installation "
                "contains the Feff8L executable and that this platform allows native executables."
            ) from exc
        finally:
            os.chdir(previous)
        return self.scan_paths()

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

    def export_run_zip(self, output: str | Path) -> Path:
        output = Path(output)
        if output.suffix.lower() != ".zip":
            output = output.with_suffix(".zip")
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(self.run_dir.rglob("*")):
                if path.is_file():
                    zf.write(path, arcname=path.relative_to(self.run_dir))
        return output

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

    def load_xas_file(self, path: str | Path) -> dict[str, Any]:
        require_larch()
        from larch import Group
        from larch.io import read_ascii, read_athena, read_xdi

        path = Path(path).expanduser().resolve()
        suffix = path.suffix.lower()
        groups: dict[str, Any] = {}

        if suffix in {".prj", ".athena"}:
            project = read_athena(str(path), do_preedge=True, do_bkg=True, do_fft=True)
            candidates = getattr(project, "groups", None)
            if isinstance(candidates, dict):
                groups.update(candidates)
            elif isinstance(candidates, (list, tuple)):
                for i, g in enumerate(candidates, start=1):
                    groups[str(getattr(g, "label", getattr(g, "name", f"group_{i}")))] = g
            else:
                for key, value in vars(project).items():
                    if key.startswith("_"):
                        continue
                    if hasattr(value, "energy") or hasattr(value, "mu"):
                        groups[str(getattr(value, "label", key))] = value
            if not groups:
                raise OpenEXAFSError("No spectra were found in the Athena project.")
            return groups

        try:
            g = read_xdi(str(path)) if suffix == ".xdi" else read_ascii(str(path))
            _group_energy(g)
            _group_mu(g)
            groups[path.stem] = g
            return groups
        except Exception:
            data = np.loadtxt(path, comments="#", delimiter="," if suffix == ".csv" else None, ndmin=2)
            if data.shape[1] < 2:
                raise OpenEXAFSError("ASCII data must contain at least two numeric columns: energy and mu.")
            g = Group(name=path.stem, energy=data[:, 0], mu=data[:, 1])
            groups[path.stem] = g
            return groups

    @staticmethod
    def process_group(group: Any, settings: FitSettings) -> Any:
        require_larch()
        from larch.xafs import pre_edge, autobk, xftf

        energy = _group_energy(group)
        mu = _group_mu(group)
        pre_edge(energy, mu, group=group)
        autobk(
            energy,
            mu,
            group=group,
            rbkg=float(settings.rbkg),
            kmin=0.0,
            kmax=float(settings.kmax),
            kweight=2,
            win=str(settings.window),
        )
        xftf(
            group.k,
            group.chi,
            group=group,
            kmin=float(settings.kmin),
            kmax=float(settings.kmax),
            kweight=int(settings.kweight),
            dk=float(settings.dk),
            window=str(settings.window),
        )
        return group

    def fit_paths(
        self,
        data_group: Any,
        path_files: Iterable[str | Path],
        settings: FitSettings,
    ) -> dict[str, Any]:
        require_larch()
        from larch.fitting import param, param_group
        from larch.xafs import (
            feffpath,
            feffit_transform,
            feffit_dataset,
            feffit,
            feffit_report,
        )

        path_files = [Path(p) for p in path_files]
        if not path_files:
            raise OpenEXAFSError("Select at least one Feff path before fitting.")

        pars_dict: dict[str, Any] = {
            "amp": param(value=float(settings.s02_init), min=0.2, max=1.5, vary=bool(settings.s02_vary)),
            "del_e0": param(value=float(settings.e0_init), min=float(settings.e0_min), max=float(settings.e0_max)),
        }
        paths = []
        mapping = []
        for i, path_file in enumerate(path_files, start=1):
            dr_name = f"dr_{i}"
            sig_name = f"sig2_{i}"
            pars_dict[dr_name] = param(value=0.0, min=float(settings.dr_min), max=float(settings.dr_max))
            pars_dict[sig_name] = param(
                value=float(settings.sigma2_init),
                min=float(settings.sigma2_min),
                max=float(settings.sigma2_max),
            )
            # Read once to get the FEFF degeneracy, then optionally expose N as a fit parameter.
            p0 = feffpath(str(path_file))
            degen0 = float(getattr(p0, "degen", 1.0))
            n_name = f"n_{i}"
            degen_expr = None
            if settings.vary_degen:
                pars_dict[n_name] = param(value=degen0, min=float(settings.degen_min), max=float(settings.degen_max))
                degen_expr = n_name
            p = feffpath(
                str(path_file),
                degen=degen_expr if degen_expr is not None else degen0,
                s02="amp",
                e0="del_e0",
                deltar=dr_name,
                sigma2=sig_name,
            )
            paths.append(p)
            mapping.append((path_file.name, n_name if settings.vary_degen else None, degen0, dr_name, sig_name, float(getattr(p, "reff", np.nan))))

        pars = param_group(**pars_dict)
        trans = feffit_transform(
            fitspace="r",
            kmin=float(settings.kmin),
            kmax=float(settings.kmax),
            kweight=int(settings.kweight),
            dk=float(settings.dk),
            window=str(settings.window),
            rmin=float(settings.rmin),
            rmax=float(settings.rmax),
        )
        dset = feffit_dataset(data=data_group, pathlist=paths, transform=trans)
        result = feffit(pars, dset)
        report = feffit_report(result)

        def pvalue(name: str) -> tuple[float, float | None]:
            obj = getattr(pars, name)
            val = float(getattr(obj, "value", obj))
            err = getattr(obj, "stderr", None)
            return val, None if err is None else float(err)

        amp, amp_err = pvalue("amp")
        e0, e0_err = pvalue("del_e0")
        rows = []
        for name, n_name, degen0, dr_name, sig_name, reff in mapping:
            dr, dr_err = pvalue(dr_name)
            sig2, sig2_err = pvalue(sig_name)
            if n_name is not None:
                nval, nerr = pvalue(n_name)
            else:
                nval, nerr = degen0, None
            rows.append(
                {
                    "path": name,
                    "n": nval,
                    "n_stderr": nerr,
                    "reff": reff,
                    "deltar": dr,
                    "deltar_stderr": dr_err,
                    "r_path": reff + dr,
                    "sigma2": sig2,
                    "sigma2_stderr": sig2_err,
                }
            )

        return {
            "result": result,
            "dataset": dset,
            "params": pars,
            "report": report,
            "rows": rows,
            "s02": amp,
            "s02_stderr": amp_err,
            "e0": e0,
            "e0_stderr": e0_err,
        }

    @staticmethod
    def save_fit_table(fit_payload: dict[str, Any], output: str | Path) -> Path:
        output = Path(output)
        if output.suffix.lower() != ".csv":
            output = output.with_suffix(".csv")
        rows = fit_payload.get("rows", [])
        fieldnames = [
            "path", "n", "n_stderr", "reff", "deltar", "deltar_stderr", "r_path", "sigma2", "sigma2_stderr"
        ]
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return output
