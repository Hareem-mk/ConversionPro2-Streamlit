# ConversionPro2 — Advanced Engineering Phase 1

Run from this folder:

```sh
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502
```

Run tests:

```sh
python3 -B -m unittest discover -s tests -v
```

Keep `advanced_engineering.py` alongside `app.py`. Only Streamlit is required; the new numerical code uses the standard library. No deployment has been performed.

This is a standalone project copy. The validated baseline, timestamped checkpoint and original Phase 1 deliverables are preserved separately in the source workspace.

## Changes

- Added `advanced_engineering.py`: pure SI calculation functions and five form-based panels under one new Advanced Engineering tab.
- Changed this copy of `app.py` only to append the tab and call the new renderer. Everything before `main()`, including validated constants and calculations, is byte-identical to the baseline.
- Adapted this copy of the baseline UI test to expect 14 tabs and leave the new buttons to the new UI tests. Existing numerical tests are unchanged. Original baseline tests remain unchanged in the parent folder.
- Tests are in `tests/test_app.py` and `tests/test_advanced_engineering.py`. Verification reports remain in the original Phase 1 deliverables.
- Requirements unchanged: no additional third-party dependency.

## Engineering behavior

Reynolds: Re = rho V D / mu. Re = 0 is no flow; 0 < Re < 2300 is laminar; 2300 ≤ Re < 4000 is transitional; Re ≥ 4000 is turbulent. These are the explicitly chosen classification limits.

All friction factors are Darcy factors (four times Fanning). Laminar f = 64/Re. No factor is assigned at zero flow or in transition.

Colebrook–White uses bisection in x = 1/sqrt(f), bounded to 200 iterations. Acceptance requires bracket width ≤ 1e-12 max(1, |x|) AND residual ≤ 1e-10. The residual is then recomputed from the returned f in the original equation and checked again. Failure raises an error instead of returning an unchecked factor. The calculator supports Re ≥ 4000 and 0 ≤ roughness/diameter ≤ 0.05; this roughness ceiling is an explicit calculator domain restriction.

Swamee–Jain: f = 0.25 / [log10(epsilon/(3.7D) + 5.74/Re^0.9)]². Comparison is provided only for 5000 ≤ Re ≤ 1e8 and 1e-6 ≤ epsilon/D ≤ 1e-2. Outside this adopted applicability envelope, the factor is withheld, including perfectly smooth pipes. Percentage difference is signed: 100(SJ−CW)/CW. No blanket error bound is claimed.

Major loss: hf = f(L/D)V²/(2g). Minor loss: hm = K V²/(2g). Pressure loss = rho g h. g = 9.80665 m/s². Head outputs are metres of the entered fluid; pressure is shown in Pa, kPa and bar.

Total result is explicitly **major + minor frictional pressure loss**. It excludes static elevation head, equipment pressure losses, pump/compressor head and other system effects. K factors must share the entered velocity reference; this is not a multi-segment network solver.

Inputs are blank initially. Density, viscosity, diameter and supplied Darcy factor must be positive; other physical inputs are nonnegative. Zero roughness and zero K require explicit entry. Non-finite/missing/negative values and numerical range errors are rejected. Loss calculations require a supplied positive Darcy factor even at zero velocity; they do not derive it from an undefined zero-flow Reynolds factor.

Assumptions: full circular pipe, steady single-phase incompressible Newtonian flow, fully developed flow for friction-factor correlations, fluid properties at operating conditions. Gas/compressible and non-Newtonian system design is outside this phase.

## References

- Swamee and Jain, *Explicit Equations for Pipe-Flow Problems* (1976): https://doi.org/10.1061/JYCEAJ.0004542
- Comparative numerical study and tabulated correlation ranges: https://www.univ-soukahras.dz/wpuploads/eprints/2019-114-8b6ed.pdf
- EPA EPANET 2.2 manual, head-loss and friction-factor context: https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P10113EM.TXT

The app's displayed transition policy and Swamee–Jain applicability gate are stated explicitly; they are not a reproduction of EPANET's transition interpolation policy.
