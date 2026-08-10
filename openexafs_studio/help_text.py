HELP_HTML = r"""
<h2>OpenEXAFS Studio</h2>
<p><b>CIF / structure to Feff8L to Larch path modeling and FEFFIT</b></p>

<h3>Why this edition?</h3>
<p>This application uses the open-source XrayLarch ecosystem and the freely redistributable
Feff8L EXAFS engine bundled for use with Larch. It is intended for EXAFS path generation,
inspection, visualization, and quantitative path fitting.</p>

<p><b>Important:</b> Feff8L is an EXAFS engine. It is not a replacement for full FEFF9 XANES
multiple-scattering calculations. Use this application for EXAFS workflows.</p>

<h3>1. Structure and Feff8L</h3>
<ul>
<li>Load CIF, POSCAR, CONTCAR, CSSR, or another structure supported by Larch/pymatgen.</li>
<li>Select absorber, crystallographic absorber site, absorption edge, and cluster radius.</li>
<li>Generate an editable <code>feff.inp</code>.</li>
<li>Run Feff8L and keep a conventional Feff run directory containing <code>paths.dat</code>,
<code>files.dat</code>, and <code>feffNNNN.dat</code>.</li>
</ul>

<h3>2. Path browser</h3>
<p>Each Feff path is displayed with effective path length, degeneracy, number of legs, geometry,
and SS/MS classification. For FEFF convention, a single-scattering path has <code>NLEG = 2</code>.</p>

<h3>3. Path preview</h3>
<p>Preview individual paths and their sum as chi(k), k chi(k), k^2 chi(k), k^3 chi(k),
|chi(R)|, Re chi(R), or Im chi(R). The default preview energy shift is Delta E0 = 0 eV because
there is no experimental edge alignment in a raw path preview. Apply or refine Delta E0 during
comparison or fitting.</p>

<h3>4. Data and FEFFIT</h3>
<p>Load ASCII/XDI data or Athena project files. Processing uses Larch pre_edge(), autobk(), and
xftf(). Quantitative fitting uses Larch feffpath(), feffit_transform(), feffit_dataset(), and feffit().</p>

<h3>5. R-prime versus fitted R</h3>
<p>The peak position in an uncorrected Fourier-transform magnitude is an apparent radial coordinate,
often written R-prime. A fitted FEFF path distance is phase-corrected through the FEFF scattering
phase and the fitted Delta R term. Do not equate an FT peak position directly with a crystallographic
bond length.</p>

<h3>Exports</h3>
<p>Plots can be exported as PNG, PDF, or SVG. Current plotted numerical arrays can be exported as
CSV. The full Feff run directory can be exported as a ZIP for use in Larch/Larix/Artemis.</p>
"""
