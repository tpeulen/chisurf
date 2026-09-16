# !chisurf: ipython
"""Protein unfolding FRET line — interactive GUI version.

Opens three fit windows in the ChiSurf MDI area so you can interact with them:
  • Gaussian model   — folded state
  • WLC model        — unfolded state
  • Lifetime mixer   — weighted combination of the two

The ``# !chisurf: ipython`` line above is a ChiSurf endpoint shebang.
It tells the Code Editor to always send this script to the IPython console
(``%run -i``), regardless of what the toolbar dropdown is set to.
Valid values: ``console`` · ``ipython`` · ``process``.

Usage
-----
Just press ▶ Run in the Code Editor — the shebang picks the right endpoint.

For headless/terminal use (no GUI needed) see: scripts/protein_unfolding_fret_line.py
"""
import sys
import numpy as np

# ── guard: must run inside ChiSurf (Console or IPython endpoint, not Process) ─
try:
    cs  # noqa: F821 — injected by Console/IPython endpoints
except NameError:
    print(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  Use the 'Console' or 'IPython' endpoint, not 'Process'.\n"
        "  Change the dropdown in the toolbar, then press ▶ again.\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    sys.exit(0)

# ── parameters — edit these before running ────────────────────────────────────
TAU_D0     = 4.0    # donor lifetime without acceptor (ns)
R0         = 52.0   # Förster radius (Å)
GAUSS_MEAN = 35.0   # folded-state mean distance (Å)  →  E ≈ 0.91
GAUSS_SIG  = 4.0    # width (Å)
WLC_LC     = 80.0   # contour length (Å)  — kappa = Lp/Lc = 0.75 (valid regime)
WLC_LP     = 60.0   # persistence length (Å)

# ── create a synthetic TCSPC dataset and register it ─────────────────────────
print("Creating synthetic dataset ...")
t = np.linspace(0, 25, 4096)
y = np.random.default_rng(42).poisson(np.exp(-t / TAU_D0) * 1e4 + 1).astype(float)
dc = cs.core.data.DataCurve(x=t, y=y, name="protein_FRET_sim")
dc.experiment = cs.experiment.get("TCSPC")   # attach TCSPC experiment so models resolve
cs.imported_datasets.append(dc)
idx = len(cs.imported_datasets) - 1
print(f"  Registered as cs.imported_datasets[{idx}]")

# ── open three fit windows ────────────────────────────────────────────────────
print("Opening fit windows ...")
cs.macros.core_fit.add_fit(dataset_indices=[idx], model_name="FRET: Gaussian distances")
gauss_fit = cs.fits[-1]

cs.macros.core_fit.add_fit(dataset_indices=[idx], model_name="FRET: worm-like chain")
wlc_fit = cs.fits[-1]

cs.macros.core_fit.add_fit(dataset_indices=[idx], model_name="Lifetime mixture")
mix_fit = cs.fits[-1]

# ── set the parameters ────────────────────────────────────────────────────────
# Every model is a view on a BFF description, so a parameter is addressed by its
# canonical id and reached the same way here as in the headless script.
from chisurf.core.fluorescence.fret import fret_line


def set_parameters(model, **values):
    """Set parameters of *model* by canonical id (``__`` reads as ``.``)."""
    for canonical, value in values.items():
        fret_line.find_parameter(model, canonical.replace("__", ".")).value = float(value)


gm = gauss_fit.model
set_parameters(gm,
               fret__tau0=TAU_D0, fret__forster_radius=R0, fret__kappa2=2 / 3,
               fret__x_donly=0.0, donor__tau__0=TAU_D0, donor__amplitude__0=1.0,
               distance__mean__0=GAUSS_MEAN, distance__sigma__0=GAUSS_SIG,
               distance__amplitude__0=1.0)
# The family carries three distances; the folded state is the first alone.
set_parameters(gm, distance__amplitude__1=0.0, distance__amplitude__2=0.0)

wm = wlc_fit.model
set_parameters(wm,
               fret__tau0=TAU_D0, fret__forster_radius=R0, fret__kappa2=2 / 3,
               fret__x_donly=0.0, donor__tau__0=TAU_D0, donor__amplitude__0=1.0,
               chain__contour_length=WLC_LC, chain__persistence_length=WLC_LP)

# ── wire the mixture: the two states are its sources ─────────────────────────
mm = mix_fit.model
mm.append_model(gm, name="x_folded")
mm.append_model(wm, name="x_unfolded")
fractions = mm._fractions
fractions[0].value, fractions[1].value = 0.5, 0.5   # 50 % folded / 50 % unfolded

# ── print a quick FRET-line sweep ─────────────────────────────────────────────
print(f"\n{'f_unfold':>10}  {'E_FRET':>8}  {'<tau> ns':>10}")
print("-" * 34)
line = fret_line.sweep([gm, wm], {"kind": "fraction", "component": 1},
                       np.linspace(0, 1, 11), fractions=[1.0, 0.0], tau_d0=TAU_D0)
for f, e, tau in zip(line["parameter_values"], line["e_fret"], line["tau_x"]):
    print(f"{f:>10.2f}  {e:>8.4f}  {tau:>10.4f}")

fractions[0].value, fractions[1].value = 0.5, 0.5

print("""
Three fit windows are open in the MDI area.
You can adjust any parameter interactively.

Console shortcuts (variables still in scope):
  gm   — Gaussian model   (folded)
  wm   — WLC model        (unfolded)
  mm   — Lifetime mixer

Examples:
  fractions[0].value, fractions[1].value = 0.2, 0.8   # 80% unfolded
  set_parameters(gm, distance__mean__0=40.0, distance__sigma__0=4.0)
  set_parameters(wm, chain__contour_length=100.0, chain__persistence_length=50.0)
""")
