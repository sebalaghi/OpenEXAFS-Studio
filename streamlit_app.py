from __future__ import annotations

from pathlib import Path
import io
import tempfile
import zipfile

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from openexafs_studio.core import FitSettings, OpenFeffEngine, PreviewSettings, OpenEXAFSError

st.set_page_config(page_title="OpenEXAFS Studio", layout="wide", page_icon="🧪")
st.title("OpenEXAFS Studio")
st.caption("CIF / structure -> Feff8L -> XrayLarch path modeling and FEFFIT")
st.info("Feff8L is an EXAFS engine. This web edition is not a FEFF9 XANES replacement.")

if "workdir" not in st.session_state:
    st.session_state.workdir = Path(tempfile.mkdtemp(prefix="openexafs_web_"))
if "engine" not in st.session_state:
    st.session_state.engine = OpenFeffEngine(st.session_state.workdir / "feff_run")
if "paths" not in st.session_state:
    st.session_state.paths = []
if "xas_groups" not in st.session_state:
    st.session_state.xas_groups = {}

engine: OpenFeffEngine = st.session_state.engine

tab1, tab2, tab3, tab4 = st.tabs(["1 Structure + Feff8L", "2 Paths + Preview", "3 Data + FEFFIT", "4 Help"])

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
            site_labels = [f"Site {s.index}: {s.species} | {s.coordinates}" for s in sites]
            site_pick = c2.selectbox("Absorber site", range(len(sites)), format_func=lambda i: site_labels[i] if site_labels else "None") if sites else None
            edge = c3.selectbox("Edge", ["K", "L3", "L2", "L1"], index=1)
            radius = c4.number_input("Cluster radius (Å)", 2.0, 15.0, 8.0, 0.5)
            include_h = st.checkbox("Include hydrogen atoms", False)
            if st.button("Generate feff.inp", type="primary"):
                text = engine.generate_feff_input(absorber, edge, radius, sites[site_pick].index if sites else None, include_h)
                engine.save_feff_input(text)
                st.session_state.feffinp = text
            text = st.text_area("Editable feff.inp", value=st.session_state.get("feffinp", ""), height=360)
            if st.button("Run Feff8L"):
                with st.spinner("Running Feff8L..."):
                    records = engine.run_feff8l(text)
                    st.session_state.paths = records
                    st.success(f"Finished: {len(records)} paths")
            if engine.run_dir.exists() and any(engine.run_dir.iterdir()):
                bio = io.BytesIO()
                with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
                    for p in engine.run_dir.rglob("*"):
                        if p.is_file(): zf.write(p, p.relative_to(engine.run_dir))
                st.download_button("Download Feff run ZIP", bio.getvalue(), "feff8l_run.zip", "application/zip")
        except Exception as exc:
            st.exception(exc)

with tab2:
    records = st.session_state.paths or engine.scan_paths()
    if not records:
        st.warning("Run Feff8L first.")
    else:
        df = pd.DataFrame([{"file":Path(r.filename).name,"type":r.kind,"nleg":r.nleg,"degen":r.degen,"reff":r.reff,"geometry":r.geometry,"path":r.filename} for r in records])
        filt = st.radio("Path filter", ["All", "Single scattering", "Multiple scattering"], horizontal=True)
        show = df.copy()
        if filt == "Single scattering": show = show[show.type == "SS"]
        if filt == "Multiple scattering": show = show[show.type == "MS"]
        st.dataframe(show.drop(columns=["path"]), use_container_width=True, hide_index=True)
        default = list(show[show.type=="SS"].path.head(6))
        selected = st.multiselect("Selected paths", options=list(show.path), default=default, format_func=lambda p: Path(p).name)
        c = st.columns(6)
        mode=c[0].selectbox("Mode", ["chi(k)","k chi(k)","k^2 chi(k)","k^3 chi(k)","|chi(R)|","Re chi(R)","Im chi(R)"], index=3)
        kmin=c[1].number_input("k min",0.0,20.0,2.5,0.1)
        kmax=c[2].number_input("k max",1.0,25.0,12.0,0.1)
        kw=c[3].selectbox("FT k weight",[0,1,2,3],index=3)
        e0=c[4].number_input("Delta E0",-30.0,30.0,0.0,0.1)
        sig2=c[5].number_input("sigma2",0.0,0.05,0.0,0.0001,format="%.5f")
        if st.button("Plot selected paths", disabled=not selected):
            payload=engine.build_preview(selected,PreviewSettings(kmin,kmax,kw,1.0,"hanning",1.0,e0,0.0,sig2)); st.session_state.preview=payload
        payload=st.session_state.get("preview")
        if payload:
            fig,ax=plt.subplots(figsize=(10,5.5))
            isr=mode in {"|chi(R)|","Re chi(R)","Im chi(R)"}; power={"chi(k)":0,"k chi(k)":1,"k^2 chi(k)":2,"k^3 chi(k)":3}.get(mode,0); ykey={"|chi(R)|":"chir_mag","Re chi(R)":"chir_re","Im chi(R)":"chir_im"}.get(mode,"chi")
            for s in payload["series"]:
                x=s["r"] if isr else s["k"]; y=s[ykey] if isr else s[ykey]*(x**power); ax.plot(x,y,lw=1,alpha=.65)
            s=payload.get("sum")
            if s:
                x=s["r"] if isr else s["k"]; y=s[ykey] if isr else s[ykey]*(x**power); ax.plot(x,y,lw=2.4,color="black",label="sum")
            ax.set_xlabel("R (Å)" if isr else "k (Å$^{-1}$)"); ax.set_ylabel(mode); ax.axhline(0,color="0.8",lw=.7); st.pyplot(fig,clear_figure=True)
            tmp=st.session_state.workdir/"preview.csv"; engine.export_preview_csv(payload,mode,tmp); st.download_button("Download plotted CSV",tmp.read_bytes(),"openexafs_preview.csv","text/csv")

with tab3:
    dataup=st.file_uploader("Experimental XAS data or Athena project", type=["prj","athena","xdi","dat","txt","csv"], key="xas")
    if dataup:
        dpath=st.session_state.workdir/dataup.name; dpath.write_bytes(dataup.getvalue())
        try:
            st.session_state.xas_groups=engine.load_xas_file(dpath)
        except Exception as exc: st.exception(exc)
    if st.session_state.xas_groups:
        name=st.selectbox("Spectrum",list(st.session_state.xas_groups)); g=st.session_state.xas_groups[name]
        c=st.columns(7)
        rbkg=c[0].number_input("Rbkg",0.2,3.0,1.0,.05)
        fkmin=c[1].number_input("k min",0.0,20.0,3.0,.1,key="fkmin")
        fkmax=c[2].number_input("k max",1.0,25.0,11.0,.1,key="fkmax")
        fkw=c[3].selectbox("k weight",[0,1,2,3],index=3,key="fkw")
        rmin=c[4].number_input("R min",0.0,10.0,1.0,.05)
        rmax=c[5].number_input("R max",0.0,10.0,3.2,.05)
        s02=c[6].number_input("S0^2 init",0.2,1.5,.9,.01)
        vary_n=st.checkbox("Fit path degeneracy N", True, help="Recommended when S0^2 has been calibrated/fixed. Avoid unconstrained simultaneous S0^2 and N refinement.")
        vary_s02=st.checkbox("Vary S0^2", False)
        settings=FitSettings(rbkg=rbkg,kmin=fkmin,kmax=fkmax,kweight=fkw,rmin=rmin,rmax=rmax,s02_init=s02,s02_vary=vary_s02,vary_degen=vary_n)
        if st.button("Process XAS data"):
            engine.process_group(g,settings); st.session_state.processed=g
        if st.session_state.get("processed") is g:
            fig,ax=plt.subplots(figsize=(9,4.5)); k=np.asarray(g.k); ax.plot(k,(k**fkw)*np.asarray(g.chi)); ax.set_xlabel("k (Å$^{-1}$)"); ax.set_ylabel(f"k^{fkw} chi(k)"); st.pyplot(fig,clear_figure=True)
            records=st.session_state.paths or engine.scan_paths(); choices=[r.filename for r in records]
            fitpaths=st.multiselect("Paths for FEFFIT",choices,default=[r.filename for r in records if r.kind=="SS"][:4],format_func=lambda p:Path(p).name)
            if st.button("Run Larch FEFFIT",disabled=not fitpaths):
                with st.spinner("Fitting..."):
                    fit=engine.fit_paths(g,fitpaths,settings); st.session_state.fit=fit
            fit=st.session_state.get("fit")
            if fit:
                st.code(fit["report"],language="text")
                st.dataframe(pd.DataFrame(fit["rows"]),use_container_width=True,hide_index=True)

with tab4:
    st.markdown("""
### Workflow
1. Load a structure, select absorber/site/edge, generate `feff.inp`, and run Feff8L.
2. Inspect and filter single-scattering or multiple-scattering paths.
3. Preview individual paths or their sum in k or R space.
4. Load experimental data, process with Larch `pre_edge`, `autobk`, and `xftf`, then fit selected paths with Larch FEFFIT.

### Scientific boundary
Feff8L is for EXAFS calculations. For full XANES multiple-scattering work, use a suitable full FEFF installation or another XANES engine.

### Hosted deployment
The browser edition depends on the host allowing the native Feff8L executable. The desktop edition is the reference implementation and is recommended for research workflows.
""")
