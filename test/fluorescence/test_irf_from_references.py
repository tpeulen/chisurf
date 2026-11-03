"""The IRF of a lifetime fit comes from a scatter, else a reference dye, else the photons outside
the bursts.

A reference dye's decay is the IRF convolved with one exponential of known lifetime, so the IRF is
recovered exactly by D[i] - exp(-dt/tau) D[i-1]; a scatter is the IRF itself, on a background. Both
are tested against a known IRF; the dye recognised by its name (``reference_dyes.yaml``).
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fio.reference_files import find_reference_measurements, reference_dye
from chisurf.core.fluorescence.tcspc.irf import (
    irf_from_reference_decay,
    reference_tail_lifetime,
    scatter_irf,
)

N, DT = 256, 0.064  # bins, ns


def _irf() -> np.ndarray:
    t = np.arange(N) * DT
    irf = np.exp(-0.5 * ((t - 2.0) / 0.12) ** 2) + 0.05 * np.exp(-((t - 2.0).clip(0)) / 0.3) * (t > 2.0)
    return irf / irf.sum()


def _decay_of(irf: np.ndarray, tau: float) -> np.ndarray:
    kernel = np.exp(-np.arange(N) * DT / tau)
    return np.real(np.fft.ifft(np.fft.fft(irf) * np.fft.fft(kernel)))


def test_the_irf_is_recovered_from_a_reference_dye_of_known_lifetime():
    rng = np.random.default_rng(1)
    irf = _irf()
    decay = _decay_of(irf, 4.0)
    counts = rng.poisson(decay / decay.max() * 2e5 + 50.0).astype(float)  # + a flat floor
    got = irf_from_reference_decay(counts, 4.0, DT)
    got /= got.sum()
    assert abs(int(np.argmax(got)) - int(np.argmax(irf))) <= 1
    width = lambda y: int((y > y.max() / 2).sum())  # noqa: E731
    assert abs(width(got) - width(irf)) <= 1
    assert np.abs(got - irf).sum() < 0.1  # 10 % of the area misplaced at most


def test_the_wrong_lifetime_is_not_the_irf():
    """The recovery is only as good as the reference lifetime: a decay deconvolved with the
    wrong one keeps a tail (what the photons outside the bursts look like)."""
    irf = _irf()
    counts = _decay_of(irf, 4.0) * 1e6 + 50.0
    right = irf_from_reference_decay(counts, 4.0, DT)
    wrong = irf_from_reference_decay(counts, 1.0, DT)
    late = slice(int(np.argmax(irf)) + 20, None)
    assert wrong[late].sum() / wrong.sum() > 10 * right[late].sum() / right.sum()


@pytest.mark.parametrize("tau", [1.15, 4.0])
def test_the_reference_lifetime_is_read_from_its_tail(tau):
    """A listed lifetime is a solvent and a temperature away from the one measured (Alexa647:
    1.0 ns listed, 1.15 ns in a real reference); the tail says which."""
    rng = np.random.default_rng(3)
    n = 625  # a 40 ns period: the decay has died before the next pulse
    t = np.arange(n) * DT
    irf = np.exp(-0.5 * ((t - 2.0) / 0.12) ** 2)
    decay = np.real(np.fft.ifft(np.fft.fft(irf) * np.fft.fft(np.exp(-t / tau))))
    counts = rng.poisson(decay / decay.max() * 2e4 + 30.0).astype(float)
    assert reference_tail_lifetime(counts, DT) == pytest.approx(tau, rel=0.03)


def test_a_flat_decay_has_no_tail_lifetime():
    assert reference_tail_lifetime(np.full(N, 50.0), DT) is None


def test_a_scatter_is_corrected_with_its_buffer_and_floor():
    irf = _irf()
    raman = np.zeros(N)
    raman[int(np.argmax(irf)) + 40] = 3000.0  # a line the buffer carries, not the response
    counts = irf * 1e6 + raman + 80.0
    got = scatter_irf(counts, buffer=raman)
    got /= got.sum()
    assert np.abs(got - irf).sum() < 0.05
    without = scatter_irf(counts)
    assert without[int(np.argmax(irf)) + 40] == 0.0  # off the IRF's peak either way


def test_the_gate_picks_the_pulse():
    """In a PIE period the detector's gate says which pulse the IRF is of."""
    irf = _irf()
    second = np.roll(irf, 120) * 3.0  # a stronger second pulse
    counts = (irf + second) * 1e6 + 10.0
    got = scatter_irf(counts, window=(0, 100))
    assert int(np.argmax(got)) == int(np.argmax(irf))


@pytest.mark.parametrize(
    "name, dye",
    [
        ("Rh110_thick_1", "Rh110"),
        ("rhodamine110", "Rh110"),
        ("Alexa647_thick_1", "Alexa647"),
        ("A488_ref", "Alexa488"),
        ("cy5_2", "Cy5"),
        ("Cy5.5", None),
        ("DNA13bp_3", None),
        ("H2O_1", None),
    ],
)
def test_reference_dyes_are_recognised_by_name(name, dye):
    found = reference_dye(f"{name}.ptu")
    assert (found or {}).get("name") == dye


def test_references_beside_the_data_are_found(tmp_path):
    for name in ("DNA13bp_3.ptu", "Rh110_thick_1.ptu", "Alexa647_thick_1.ptu", "H2O.ptu", "buffer.ptu"):
        (tmp_path / name).write_bytes(b"")
    found = find_reference_measurements([tmp_path / "DNA13bp_3.ptu"])
    assert [p.name for p in found["irf"]] == ["H2O.ptu"]
    assert [p.name for p in found["dye"]] == ["Alexa647_thick_1.ptu", "Rh110_thick_1.ptu"]
    assert [p.name for p in found["bg"]] == ["buffer.ptu"]
