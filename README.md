# ConversionPro2 — Phase 2

Engineering unit conversions, tank geometry, Advanced Engineering, and Phase 2 pipe/pump calculations through NPSH Available.

## Run locally

```sh
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

## Test

```sh
python3 -B -m unittest discover -s tests -v
```

The complete regression suite has 122 tests. Seven additional correction checks, cross-module scenarios, edge checks and live-browser acceptance were completed separately. Local verification used Python 3.11 and Streamlit 1.59.1.

## Streamlit Community Cloud

Upload all contents of this folder to your GitHub repository, retaining the `piping_hydraulics/` and `tests/` directories. Do not upload only app.py. Choose the repository and branch, use `app.py` as the main file, and select Python 3.11 if offered to match local verification. Requirements are pinned. No secrets or fluid-property service are required. Deployment and its resulting URL must be verified separately.

## Engineering scope

Steady-state, single-phase incompressible liquid calculations within the stated module assumptions. Friction correlations assume Newtonian flow in a full circular pipe. Representative roughness/K data require engineer confirmation. No nominal pipe schedule selection, NPSHR prediction or pump selection. NPSHA alone does not establish adequate cavitation margin. Verify actual fluid properties, pressure/elevation references and project requirements.

Phase 1 remains unchanged. The Stage 2D head adapter delegates to the Phase 1 minor-loss function. Stage 2C intentionally retains its unrestricted descriptive roughness ratio, distinct from the friction calculator's applicability-limited ratio.
