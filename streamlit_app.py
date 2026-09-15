from __future__ import annotations

from pathlib import Path
import io
import tempfile
import zipfile

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from openexafs_studio.core import OpenFeffEngine, PreviewSettings

st.set_page_config(page_title="OpenEXAFS Studio", layout="wide", page_icon="🧪")
st.title("OpenEXAFS Studio")
st.caption("Structure -> Feff8L -> FEFF8 scattering paths -> Artemis")
st.info("This edition generates and previews Feff8L paths. Quantitative fitting is intentionally left to Artemis.")

if "workdir" not in st.session_state:
    st.session_state.workdir = Path(tempfile.mkdtemp(prefix="openexafs_web_"))
if "engine" not in st.session_state:
    st.session_state.engine = OpenFeffEngine(st.session_state.workdir / "feff_run")
if "paths" not in st.session_state:
    st.session_state.paths = []

engine: OpenFeffEngine = st.session_state.engine

tab1, tab2, tab3 = st.tabs(["1 Structure + Feff8L", "2 Paths + Preview", "3 Artemis export"])

with tab1:
    upload = st.file_uploader("Structure file", type=["cif", "vasp", "cssr", "xyz", "txt"], key="structure")
    if upload is not None:
        spath = st.session_state.workdir / upload.name
        spath.write_bytes(upload.getvalue())
        try:
            info = engine.load_structure(spath)
            st.success(f"Loaded {info.formula} with {len(info.sites)} sites")
            c1, c2, c3, c4 = st.columns(4)
            absorber = c1.selectbox("Absorber", info.elements, index=info.elements.index("Pt") if "Pt" in info.elements else 0)
            sites = engine.absorber_sites(absorber)
            labels = [f"Site {s.index}: {s.species} | {s.coordinates}" for s in sites]
            site_pick = c2.selectbox("Absorber site", range(len(sites)), format_func=lambda i: labels[i]) if sites else None
            edge = c3.selectbox("Edge", ["K", "L3", "L2", "L1"], index=1)
            radius = c4.number_input("Cluster radius (Å)", 2.0, 15.0, 8.0, 0.5)
            include_h = st.checkbox("Include hydrogen atoms", False)

            if st.button("Generate feff.inp", type="primary"):
                text = engine.generate_feff_input(
                    absorber,
                    edge,
                    radius,
                    sites[site_pick].index if sites else None,
                    include_h,
                )
                engine.save_feff_input(text)
                st.session_state.feffinp = text

            text = st.text_area("Editable FEFF8 feff.inp", value=st.session_state.get("feffinp", ""), height=360)

            if st.button("Run Feff8L"):
                with st.spinner("Running Feff8L..."):
                    records = engine.run_feff8l(text)
                    st.session_state.paths = records
                    st.success(f"Finished: {len(records)} paths")
        except Exception as exc:
            st.exception(exc)

with tab2:
    records = st.session_state.paths or engine.scan_paths()
    if not records:
        st.warning("Run Feff8L first.")
    else:
        df = pd.DataFrame([
            {
                "file": Path(r.filename).name,
                "type": r.kind,
                "nleg": r.nleg,
                "degen": r.degen,
                "reff": r.reff,
                "geometry": r.geometry,
                "path": r.filename,
            }
            for r in records
        ])
        filt = st.radio("Path filter", ["All", "Single scattering", "Multiple scattering"], horizontal=True)
        show = df.copy()
        if filt == "Single scattering":
            show = show[show.type == "SS"]
        if filt == "Multiple scattering":
            show = show[show.type == "MS"]
        st.dataframe(show.drop(columns=["path"]), use_container_width=True, hide_index=True)

        default = list(show[show.type == "SS"].path.head(6))
        selected = st.multiselect(
            "Selected paths",
            options=list(show.path),
            default=default,
            format_func=lambda p: Path(p).name,
        )

        c = st.columns(6)
        mode = c[0].selectbox("Mode", ["chi(k)", "k chi(k)", "k^2 chi(k)", "k^3 chi(k)", "|chi(R)|", "Re chi(R)", "Im chi(R)"], index=4)
        kmin = c[1].number_input("k min", 0.0, 20.0, 2.5, 0.1)
        kmax = c[2].number_input("k max", 1.0, 25.0, 12.0, 0.1)
        kw = c[3].selectbox("FT k weight", [0, 1, 2, 3], index=3)
        e0 = c[4].number_input("Delta E0", -30.0, 30.0, 0.0, 0.1)
        sig2 = c[5].number_input("sigma2", 0.0, 0.05, 0.0, 0.0001, format="%.5f")

        if st.button("Plot selected paths", disabled=not selected):
            st.session_state.preview = engine.build_preview(
                selected,
                PreviewSettings(kmin=kmin, kmax=kmax, kweight=kw, e0=e0, sigma2=sig2),
            )

        payload = st.session_state.get("preview")
        if payload:
            fig, ax = plt.subplots(figsize=(10, 5.5))
            isr = mode in {"|chi(R)|", "Re chi(R)", "Im chi(R)"}
            power = {"chi(k)": 0, "k chi(k)": 1, "k^2 chi(k)": 2, "k^3 chi(k)": 3}.get(mode, 0)
            ykey = {"|chi(R)|": "chir_mag", "Re chi(R)": "chir_re", "Im chi(R)": "chir_im"}.get(mode, "chi")
            for s in payload["series"]:
                x = s["r"] if isr else s["k"]
                y = s[ykey] if isr else s[ykey] * (x ** power)
                ax.plot(x, y, lw=1, alpha=0.65)
            s = payload.get("sum")
            if s:
                x = s["r"] if isr else s["k"]
                y = s[ykey] if isr else s[ykey] * (x ** power)
                ax.plot(x, y, lw=2.4, color="black", label="sum")
            ax.set_xlabel("R (Å)" if isr else "k (Å$^{-1}$)")
            ax.set_ylabel(mode)
            st.pyplot(fig, clear_figure=True)

with tab3:
    ok, status = engine.validate_artemis_run()
    st.success(status) if ok else st.warning(status)

    st.markdown(
        """
### Export for Artemis

The package keeps the original Feff8L `feffNNNN.dat` path files and the FEFF8 input.
No FEFF6 conversion is performed.

In Artemis choose **File -> Import... -> a feff.inp file**, then select the exported
`feff.inp` while keeping all `feffNNNN.dat` files in the same directory.
"""
    )

    if ok:
        tmpzip = st.session_state.workdir / "Artemis_FEFF8.zip"
        engine.export_artemis_zip(tmpzip)
        st.download_button(
            "Download Artemis FEFF8 ZIP",
            tmpzip.read_bytes(),
            "Artemis_FEFF8.zip",
            "application/zip",
            type="primary",
        )
