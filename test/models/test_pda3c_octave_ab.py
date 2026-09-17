"""Compare ChiSurf to the incumbent's compiled PDA3c kernel, via a recorded fixture.

The sibling ``test_pda3c_pam_ab.py`` transcribes the incumbent's *expressions*;
this one checks against its actual **C code**. The kernel is a self-contained MEX
function with a plain numeric signature, so unlike the surrounding MATLAB it can
be compiled with Octave's ``mkoctfile`` and driven directly. That closes the gap a
transcription leaves open: a mistake shared between the source and its
transcription would survive the other test, and would not survive this one.

The kernel's output is frozen in
``test/data/pda3c/pam_eval_prob_3c_bg_lib_reference.npz`` (inputs included), so
the check runs everywhere without Octave or the reference checkout. The upstream
revision, the exact source files and the Octave driver are in
``test/data/pda3c/gen_pam_pda3c_reference.py``, which regenerates it.
"""

from __future__ import annotations

import pathlib

import numpy as np

REFERENCE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "data"
    / "pda3c"
    / "pam_eval_prob_3c_bg_lib_reference.npz"
)


def test_chisurf_matches_the_compiled_reference_kernel():
    """ChiSurf's factorised likelihood equals the reference's nested-sum C code.

    The two compute the same quantity by different algorithms — the reference
    sums over every channel's background count, ChiSurf collapses that into two
    matrix products — so agreement to machine precision is a real check on the
    factorisation rather than a restatement of it.
    """
    from chisurf.core.fluorescence.pda3c import burst_log_likelihood

    z = np.load(REFERENCE)
    reference = z["P"]  # (bursts, points)

    p_blue = np.stack([z["p_bb"], z["p_bg"], 1.0 - z["p_bb"] - z["p_bg"]], axis=1)
    counts_blue = np.stack([z["fbb"], z["fbg"], z["fbr"]], axis=1)
    counts_green = np.stack([z["fgg"], z["fgr"]], axis=1)
    p_green = np.stack([1.0 - z["p_gr"], z["p_gr"]], axis=1)

    ours = np.exp(
        burst_log_likelihood(counts_blue, p_blue, z["bg_blue"])
        + burst_log_likelihood(counts_green, p_green, z["bg_green"])
    ).T

    assert ours.shape == reference.shape
    assert np.all(reference > 0.0)
    relative = np.abs(ours - reference) / np.maximum(np.abs(reference), 1e-300)
    assert relative.max() < 1e-10, f"max relative difference {relative.max():.3e}"
