# !chisurf: process
"""Protein unfolding FRET line — headless / standalone.

Computes a two-state folding FRET line (Gaussian folded + WLC unfolded)
and writes results to text files. No GUI needed.

The two states are ordinary described models — ``tcspc_fret_gaussian`` for the
folded state, ``tcspc_fret_worm_like_chain`` for the unfolded one — mixed by
the fraction unfolded. The FRET-line engine
(:mod:`chisurf.core.fluorescence.fret.fret_line`) does the mixing and reads the
lifetime spectrum back, so this script and the plugin compute the same line.

The ``# !chisurf: process`` shebang tells the Code Editor to run this as a
subprocess regardless of the toolbar dropdown. Valid values: console · ipython · process.

Run from terminal::

    conda activate arm64
    python scripts/protein_unfolding_fret_line.py

For the interactive GUI version see: scripts/protein_unfolding_gui.py
"""
import pathlib
import numpy as np
from chisurf.core.fluorescence.fret import fret_line

# ── parameters ────────────────────────────────────────────────────────────────
TAU_D0     = 4.0          # donor lifetime without acceptor (ns)
R0         = 52.0         # Förster radius (Å)
GAUSS_MEAN = 35.0         # folded-state mean distance (Å)  →  E ≈ 0.91
GAUSS_SIG  = 4.0          # width (Å)
WLC_LC     = 80.0         # contour length (Å)  — kappa = Lp/Lc = 0.75 (valid regime)
WLC_LP     = 60.0         # persistence length (Å)

FRACS = np.linspace(0, 1, 21)          # fraction unfolded: 0 → 1
TIME  = np.linspace(0, 25, 256)        # time axis for synthetic decays (ns)
OUT   = pathlib.Path(__file__).parent  # output folder = same dir as this script


def _set(view, **values):
    """Set parameters of *view* by canonical id."""
    for canonical, value in values.items():
        fret_line.find_parameter(view, canonical.replace("__", ".")).value = float(value)


def folded_state():
    """The folded state: one Gaussian distance between the dyes."""
    view = fret_line.model_view("tcspc_fret_gaussian")
    _set(view,
         fret__tau0=TAU_D0, fret__forster_radius=R0, fret__kappa2=2 / 3,
         fret__x_donly=0.0, donor__tau__0=TAU_D0, donor__amplitude__0=1.0,
         distance__mean__0=GAUSS_MEAN, distance__sigma__0=GAUSS_SIG,
         distance__amplitude__0=1.0)
    # The family carries three distances; the folded state is the first alone.
    for index in (1, 2):
        _set(view, **{f"distance__amplitude__{index}": 0.0})
    return view


def unfolded_state(contour_length=WLC_LC, persistence_length=WLC_LP):
    """The unfolded state: a worm-like chain of the given stiffness."""
    view = fret_line.model_view("tcspc_fret_worm_like_chain")
    _set(view,
         fret__tau0=TAU_D0, fret__forster_radius=R0, fret__kappa2=2 / 3,
         fret__x_donly=0.0, donor__tau__0=TAU_D0, donor__amplitude__0=1.0,
         chain__contour_length=contour_length,
         chain__persistence_length=persistence_length)
    return view


def unfolding_line(unfolded, fractions=FRACS):
    """Sweep the fraction unfolded and return ``(E_FRET, <tau>_x)``."""
    line = fret_line.sweep(
        [folded_state(), unfolded],
        {"kind": "fraction", "component": 1},
        fractions,
        fractions=[1.0, 0.0],
        tau_d0=TAU_D0,
    )
    return np.asarray(line["e_fret"]), np.asarray(line["tau_x"])


# ── the two-state line ────────────────────────────────────────────────────────
print("Sweeping fraction unfolded ...")
effs, taus = unfolding_line(unfolded_state())
for f, e, tau in zip(FRACS, effs, taus):
    print(f"  f={f:.2f}  E={e:.4f}  <tau>={tau:.4f} ns")

# A single-exponential decay per point, for plotting: the average lifetime is
# what the line is made of, so that is what the curve shows.
decays = []
for tau in taus:
    decay = np.exp(-TIME / tau) if tau > 0 else np.zeros_like(TIME)
    total = decay.sum()
    decays.append(decay / total if total > 0 else decay)

# ── WLC parameter sweep (grid of Lc × Lp) ────────────────────────────────────
print("\nWLC parameter sweep ...")
sweep_rows = []
for lc in [60, 80, 100, 120]:
    for lp in [40, 60, 80, 100]:
        print(f"  Lc={lc} Å  Lp={lp} Å ...")
        grid_effs, grid_taus = unfolding_line(unfolded_state(lc, lp))
        for f, e, tau in zip(FRACS, grid_effs, grid_taus):
            sweep_rows.append([lp, lc, f, e, tau])

# ── write output files ────────────────────────────────────────────────────────
print("\nWriting output files ...")

np.savetxt(
    OUT / "unfolding_fret_line.txt",
    np.column_stack([FRACS, effs, taus]),
    header=(
        f"tau_D0={TAU_D0} ns  R0={R0} A  "
        f"Gaussian R_mean={GAUSS_MEAN} A sigma={GAUSS_SIG} A  "
        f"WLC Lc={WLC_LC} A Lp={WLC_LP} A\n"
        "fraction_unfolded\tE_FRET\ttau_avg_ns"
    ),
    delimiter="\t", fmt="%.6f",
)

np.savetxt(
    OUT / "unfolding_decays.txt",
    np.column_stack([TIME] + decays),
    header="time_ns\t" + "\t".join(f"f={f:.2f}" for f in FRACS),
    delimiter="\t", fmt="%.8f", comments="",
)

np.savetxt(
    OUT / "wlc_sweep_fret_lines.txt",
    np.array(sweep_rows),
    header="Lp_A\tLc_A\tfraction_unfolded\tE_FRET\ttau_avg_ns",
    delimiter="\t", fmt=["%.1f", "%.1f", "%.6f", "%.6f", "%.6f"], comments="",
)

print(f"Done. Files written to {OUT}/")
