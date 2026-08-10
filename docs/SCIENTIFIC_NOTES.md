# Scientific notes

## Engine boundary

OpenEXAFS Studio uses Feff8L for EXAFS path calculations. Feff8L is not the full FEFF9 code and is not
intended here for full XANES multiple-scattering calculations.

## Single scattering

The GUI classifies a path as single scattering when `NLEG == 2`, matching FEFF path convention.

## Delta E0 default

Raw path preview uses Delta E0 = 0 eV by default. A nonzero value without experimental edge alignment
would be arbitrary. Delta E0 can be adjusted for preview and is normally refined during FEFFIT.

## R-prime versus R-path

The radial coordinate of an uncorrected FT-EXAFS magnitude is an apparent coordinate, often written
R-prime. It is shifted by absorber/scatterer photoelectron phase shifts. FEFFIT evaluates the full FEFF
complex scattering function, and a fitted path distance can be reported as `Reff + Delta R`. This fitted
path distance should not be confused with an uncorrected FT peak position.

## Path fitting

The built-in fitting page intentionally starts with a transparent parameterization:

- one global S0^2,
- one global Delta E0,
- one path degeneracy N per selected path when enabled,
- one Delta R per selected path,
- one sigma^2 per selected path.

The GUI defaults to fitting path degeneracy N while keeping S0^2 fixed. This is intended for cases where S0^2 has been calibrated independently. Simultaneously varying N and S0^2 is strongly correlated and should normally be avoided.

For publication-quality analysis, reduce parameter count according to chemical symmetry, calibrate or
fix S0^2 when justified, inspect correlations and independent-point limits, compare alternative path
models, and document parameter bounds.

## References

- M. Newville, Larch: An Analysis Package for XAFS and Related Spectroscopies, J. Phys.: Conf. Ser. 430,
  012007 (2013), DOI 10.1088/1742-6596/430/1/012007.
- J. J. Rehr, J. J. Kas, F. D. Vila, M. P. Prange, K. Jorissen, Parameter-free calculations of X-ray
  spectra with FEFF9, Phys. Chem. Chem. Phys. 12, 5503-5513 (2010), DOI 10.1039/B926434E.
