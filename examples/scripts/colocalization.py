# !chisurf: process
"""Two-channel colocalization — headless / standalone.

Builds two synthetic images whose answer is known by construction, runs both
colocalization regimes on them, and writes the coefficients to a text file.
No GUI needed.

The ``# !chisurf: process`` shebang tells the Code Editor to run this as a
subprocess regardless of the toolbar dropdown. Valid values: console · ipython · process.

Run from terminal::

    conda activate arm64
    python examples/scripts/colocalization.py

The same analysis on a real file, from the shell::

    img-coloc IMAGE.ptu -a green -b red --auto-background --costes-threshold
    img-coloc IMAGE.ptu -a green -b red --costes-test --ccf-shift 12 --objects --json
"""

import pathlib

import numpy as np

from chisurf.core.fluorescence.imaging import (
    colocalization_metrics,
    cross_correlation_2d,
    object_colocalization,
    pearson,
    segment_objects,
)

# ── synthetic data ────────────────────────────────────────────────────────────
# Two regimes in one script, because they answer different questions:
#   * a continuous pair (structures that overlap) → intensity coefficients
#   * a punctate pair (discrete spots)            → object statistics
SHAPE = (160, 160)
RNG = np.random.default_rng(2026)
Y, X = np.mgrid[: SHAPE[0], : SHAPE[1]]


def blobs(centres, sigma=6.0, amplitude=120.0):
    """Return an image with Gaussian spots at *centres*."""
    image = np.zeros(SHAPE, dtype=float)
    for cy, cx in centres:
        image += amplitude * np.exp(-((Y - cy) ** 2 + (X - cx) ** 2) / (2 * sigma**2))
    return image


# Continuous pair: channel B follows channel A with 20 % crosstalk-free scaling.
structure = blobs([(50, 50), (110, 60), (70, 120)])
background = 8.0
continuous_a = structure + background + RNG.normal(0.0, 3.0, SHAPE)
continuous_b = 0.8 * structure + background + RNG.normal(0.0, 3.0, SHAPE)

# Punctate pair: 30 spots in A, of which 20 have a partner 1 px away in B,
# plus 5 spots in B that belong to nobody.
punctate_centres = [tuple(p) for p in RNG.integers(12, 148, size=(30, 2))]
partners = [(cy + 1, cx) for cy, cx in punctate_centres[:20]]
strangers = [tuple(p) for p in RNG.integers(12, 148, size=(5, 2))]
punctate_a = blobs(punctate_centres, sigma=2.2) + RNG.normal(0.0, 2.0, SHAPE)
punctate_b = blobs(partners + strangers, sigma=2.2) + RNG.normal(0.0, 2.0, SHAPE)

# ── 1. pixel-wise coefficients ────────────────────────────────────────────────
# Background first: it biases Manders' overlap badly and Pearson mildly.
result = colocalization_metrics(
    continuous_a,
    continuous_b,
    background_a=background,
    background_b=background,
    auto_threshold=True,  # Costes' thresholds instead of hand-picked ones
    costes_test=True,  # is it more than two dense stainings can give by chance?
    costes_randomizations=100,
    costes_seed=0,
    ccf_max_shift=12,
    ccf_2d=True,
    profiles=True,
)
metrics = result.metrics

print("── continuous pair (intensity coefficients) ──")
print(f"Pearson PCC          : {metrics['pearson']:.3f}")
print(f"Manders MOC          : {metrics['manders_overlap']:.3f}")
print(f"Manders M1 / M2      : {metrics['manders_m1']:.3f} / {metrics['manders_m2']:.3f}")
print(f"Li ICQ               : {metrics['li_icq']:.3f}")
print(f"Costes thresholds    : {metrics['threshold_a']:.2f} / {metrics['threshold_b']:.2f}")
print(f"Costes p-value       : {metrics['costes_p_value']:.3f}  (significant at > 0.95)")
print(f"CCF peak shift (1-D) : {metrics['ccf_peak_shift']} px")
print(f"CCF peak (2-D)       : dx={metrics['ccf2d_peak_dx']}, dy={metrics['ccf2d_peak_dy']} px")

# A registration offset is what the shift profile is for: displace B and look.
shifted = np.roll(continuous_b, (4, -3), axis=(0, 1))
offset = cross_correlation_2d(continuous_a, shifted, max_shift=12)
print(f"misaligned copy      : dx={offset['peak_dx']}, dy={offset['peak_dy']} px (expected -3, 4)")

# ── 2. object-based colocalization ────────────────────────────────────────────
# For puncta the coefficients above are dominated by the empty background
# between the spots; count objects instead.
objects = object_colocalization(punctate_a, punctate_b, distance=3.0, min_size=4)
object_metrics = objects["metrics"]

print()
print("── punctate pair (object statistics) ──")
print(f"Pearson PCC          : {pearson(punctate_a, punctate_b):.3f}  ← the wrong question")
print(f"objects A / B        : {object_metrics['n_objects_a']} / {object_metrics['n_objects_b']}")
print(f"fraction A with B    : {object_metrics['object_fraction_a_near_b']:.2f}")
print(f"fraction B with A    : {object_metrics['object_fraction_b_near_a']:.2f}")
print(f"median distance A→B  : {object_metrics['object_median_distance_a']:.2f} px")

single = segment_objects(punctate_a, min_size=4)
print(f"mean object area     : {single.areas.mean():.1f} px")

# ── 3. write the results ──────────────────────────────────────────────────────
output = pathlib.Path(__file__).with_name("colocalization_results.txt")
with output.open("w") as fp:
    fp.write("# Colocalization coefficients from examples/scripts/colocalization.py\n")
    fp.write("# continuous pair\n")
    for key in (
        "pearson",
        "manders_overlap",
        "manders_m1",
        "manders_m2",
        "li_icq",
        "spearman",
        "threshold_a",
        "threshold_b",
        "costes_p_value",
        "ccf_peak_shift",
        "ccf2d_peak_dx",
        "ccf2d_peak_dy",
    ):
        fp.write(f"{key}\t{metrics[key]}\n")
    fp.write("# punctate pair\n")
    for key, value in object_metrics.items():
        fp.write(f"{key}\t{value}\n")
print(f"\nwrote {output.name}")

# ── assertions: the answers are known by construction ─────────────────────────
assert metrics["pearson"] > 0.9, "proportional channels must correlate"
assert metrics["costes_p_value"] > 0.95, "real colocalization must be significant"
assert metrics["ccf_peak_shift"] == 0, "the pair is registered"
assert (offset["peak_dx"], offset["peak_dy"]) == (-3, 4), "the shift must be recovered"
assert object_metrics["n_objects_a"] >= 25, "most puncta must be segmented"
assert object_metrics["object_fraction_a_near_b"] > 0.5, "two thirds of A have a partner"
assert object_metrics["object_median_distance_a"] < 3.0, "partners are ~1 px apart"
print("all assertions passed")
