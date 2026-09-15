# Scientific notes

## Engine boundary

OpenEXAFS Studio uses Feff8L for EXAFS scattering-path calculations. Feff8L is not the full FEFF9
code and is not intended here for full XANES multiple-scattering calculations.

## Scope of this project

The application intentionally stops before quantitative EXAFS fitting. Its job is to:

1. build a FEFF8-style input from a structure,
2. run Feff8L,
3. inspect and preview the generated scattering paths,
4. export the original Feff8L path files for Artemis.

This avoids maintaining a second fitting implementation when Artemis is already a mature fitting
environment.

## Single scattering

The GUI classifies a path as single scattering when `NLEG == 2`, matching FEFF path convention.

## Path preview

Preview parameters such as S0^2, Delta E0, Delta R, and sigma^2 are visualization controls only.
They do not represent a fitted model.

## Artemis compatibility

The Artemis export preserves the original Feff8L `feffNNNN.dat` files. It also includes
`feff.inp` and available FEFF metadata such as `paths.dat`, `files.dat`, `list.dat`, and
`phase.bin`.

The exported path files are not converted to FEFF6.

Historically, Artemis developer Bruce Ravel stated that externally generated `feffNNNN.dat` files
can be imported independently of the FEFF version because the relevant path-file format did not
change between FEFF6 and FEFF8.

## References

- M. Newville, Larch: An Analysis Package for XAFS and Related Spectroscopies, J. Phys.: Conf. Ser. 430,
  012007 (2013), DOI 10.1088/1742-6596/430/1/012007.
- J. J. Rehr, J. J. Kas, F. D. Vila, M. P. Prange, K. Jorissen, Parameter-free calculations of X-ray
  spectra with FEFF9, Phys. Chem. Chem. Phys. 12, 5503-5513 (2010), DOI 10.1039/B926434E.
