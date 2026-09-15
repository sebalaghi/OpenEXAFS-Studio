HELP_HTML = r"""
<h2>OpenEXAFS Studio</h2>
<p><b>Structure to Feff8L to Artemis</b></p>

<p>OpenEXAFS Studio is intentionally focused on generating and inspecting Feff8L EXAFS
scattering paths, then exporting the original FEFF8 path files for fitting in Artemis.</p>

<h3>1. Structure and Feff8L</h3>
<ul>
<li>Load a CIF, POSCAR, CONTCAR, CSSR, or another structure supported by Larch/pymatgen.</li>
<li>Select absorber, crystallographic absorber site, absorption edge, and cluster radius.</li>
<li>Generate an editable FEFF8-style <code>feff.inp</code>.</li>
<li>Run Feff8L to create <code>feffNNNN.dat</code> scattering-path files.</li>
</ul>

<h3>2. Path browser</h3>
<p>Inspect path length, degeneracy, NLEG, geometry, and SS/MS classification. A FEFF
single-scattering path has <code>NLEG = 2</code>.</p>

<h3>3. Path preview</h3>
<p>Preview individual paths and their sum as chi(k), k-weighted chi(k), or complex
Fourier-transform components. Preview parameters are for visualization only.</p>

<h3>4. Artemis export</h3>
<p>Use <b>Export Artemis folder</b> or <b>Export Artemis ZIP</b>. The package contains
the original Feff8L <code>feff.inp</code>, available FEFF metadata files, and all
<code>feffNNNN.dat</code> files. OpenEXAFS Studio does not convert the path data to FEFF6.</p>

<p>For Artemis 0.9.26, first run <code>ENABLE_ARTEMIS_EXTERNAL_IMPORT.ps1</code> once to expose
the dormant external-FEFF importer, then restart Artemis. Use
<b>File &gt; Import... &gt; an external Feff calculation</b> and select the exported
<code>feff.inp</code>. Do not click <b>Run Feff</b>.</p>

<h3>Scientific scope</h3>
<p>Feff8L is an EXAFS engine and is not a replacement for full FEFF9 XANES calculations.
Quantitative EXAFS fitting is intentionally not implemented in this application.</p>
"""