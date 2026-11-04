"""The IRF of a lifetime fit comes from a scatter, else a reference dye, else the photons outside
the bursts -- extracted by the IRF Estimation tool, the one implementation every consumer calls.

A reference dye's decay is the IRF convolved with the dye's polarised exponential, so the IRF is
recovered by deconvolving that known kernel (Richardson-Lucy, the dye's lifetime from its tail and
its rotation from its two polarisations); a scatter is the IRF itself, on a background. Both are
tested against a known IRF; the dye recognised by its name (``reference_dyes.yaml``).
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fio.reference_files import find_reference_measurements, reference_dye
from chisurf.plugins.fluorescence_decay.irf_estimator.core.extraction import (
    best_irf,
    irf_from_reference,
    irf_from_scatter,
    polarised_kernels,
    reference_irf,
    reference_rotation,
    reference_tail_lifetime,
    scatter_irf,
)

N, DT = 625, 0.064  # bins, ns: a 40 ns period, the reference decays die before the next pulse
OS = 16  # sub-bins of the simulation: photons arrive anywhere in a bin


def _fine_irf(n: int = N, dt: float = DT) -> np.ndarray:
    t = (np.arange(n * OS) + 0.5) * dt / OS
    irf = np.exp(-0.5 * ((t - 2.0) / 0.12) ** 2) + 0.05 * np.exp(-((t - 2.0).clip(0)) / 0.3) * (t > 2.0)
    return irf / irf.sum()


def _irf(n: int = N, dt: float = DT) -> np.ndarray:
    return _fine_irf(n, dt).reshape(n, OS).sum(1)


def _decay_of(tau: float, rho: float | None = None, n: int = N, dt: float = DT, r0: float = 0.38):
    """VV and VH of a dye (lifetime *tau*, rotation *rho*) excited by the IRF, binned like photons."""
    t = (np.arange(n * OS) + 0.5) * dt / OS
    fine = _fine_irf(n, dt)
    r = r0 * np.exp(-t / rho) if rho else np.zeros_like(t)
    out = []
    for pol in (1 + 2 * r, 1 - r):
        out.append(np.real(np.fft.ifft(np.fft.fft(fine) * np.fft.fft(pol * np.exp(-t / tau)))).reshape(n, OS).sum(1))
    return out


def _tv(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.clip(a, 0, None), np.clip(b, 0, None)
    return 0.5 * float(np.abs(a / a.sum() - b / b.sum()).sum())


def test_the_irf_is_recovered_from_a_reference_dye_of_known_lifetime():
    rng = np.random.default_rng(1)
    irf = _irf()
    vv, _ = _decay_of(4.0)
    counts = rng.poisson(vv / vv.max() * 2e5 + 50.0).astype(float)  # + a flat floor
    got = reference_irf(counts, polarised_kernels(N, DT, 4.0, None)[0])
    got /= got.sum()
    assert abs(int(np.argmax(got)) - int(np.argmax(irf))) <= 1
    width = lambda y: int((y > y.max() / 2).sum())  # noqa: E731
    assert abs(width(got) - width(irf)) <= 1
    assert _tv(got, irf) < 0.05


def test_the_wrong_lifetime_is_not_the_irf():
    """The recovery is only as good as the reference lifetime: a decay deconvolved with the
    wrong one keeps a tail (what the photons outside the bursts look like)."""
    irf = _irf()
    vv, _ = _decay_of(4.0)
    counts = vv * 1e6 + 50.0
    right = reference_irf(counts, polarised_kernels(N, DT, 4.0, None)[0])
    wrong = reference_irf(counts, polarised_kernels(N, DT, 1.0, None)[0])
    late = slice(int(np.argmax(irf)) + 20, None)
    assert wrong[late].sum() / wrong.sum() > 10 * right[late].sum() / right.sum()


def test_the_rotation_of_the_dye_is_not_taken_for_the_irf():
    """Each polarisation of a rotating dye is not one exponential. The exact difference used
    before took the rotation for part of the IRF (TV 0.16 on VV, the centre 0.12 ns early, a
    2.5 ns sample fitted at 2.63 ns, on the simulation of the IRF tool's guide); with the
    polarised kernels and the rotation read from the data both halves are the IRF."""
    rng = np.random.default_rng(7)
    irf = _irf()
    vv, vh = _decay_of(4.0, rho=0.2)
    total = vv.sum() + vh.sum()
    vv = rng.poisson(vv / total * 1.2e6 + 300.0).astype(float)
    vh = rng.poisson(vh / total * 1.2e6 + 300.0).astype(float)
    tau = reference_tail_lifetime(vv + 2 * vh, DT)
    assert tau == pytest.approx(4.0, rel=0.04)
    assert reference_rotation(vv, vh, DT, tau) == pytest.approx(0.2, abs=0.06)
    got = irf_from_reference(vv, vh, DT, listed_tau_ns=4.0, name="Rh110.ptu", dye="Rh110")
    assert got.source == "reference" and "Rh110" in got.text and "rotation" in got.text
    for half in got.halves:
        assert _tv(half, irf) < 0.06
        t = np.arange(N) * DT
        assert abs(float((half * t).sum() - (irf * t).sum())) < 0.03  # centre within 30 ps


def test_one_channel_for_both_halves_takes_the_plain_exponential():
    vv, _ = _decay_of(4.0)
    counts = vv * 1e6 + 50.0
    got = irf_from_reference(counts, counts, DT, tau_ns=4.0)
    assert got.info["rho_ns"] is None
    np.testing.assert_allclose(got.halves[0], got.halves[1])


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


def test_a_scatter_wins_over_a_dye_and_too_few_photons_is_none():
    irf = _irf()
    vv, vh = _decay_of(4.0)
    scatter = irf_from_scatter([irf * 1e4 + 5.0, irf * 1e4 + 5.0])
    dye = irf_from_reference(vv * 1e6 + 50.0, vh * 1e6 + 50.0, DT, tau_ns=4.0, rho_ns=0.2)
    assert best_irf([dye, scatter], min_counts=500).source == "scatter"
    assert best_irf([dye, None], min_counts=500) is dye
    assert best_irf([irf_from_scatter([irf * 10.0, irf * 10.0])], min_counts=500) is None


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


def test_a_gate_without_a_decay_gives_no_irf():
    """A reference dye that a detector does not see (Rh110 in the red detectors after the red
    pulse) leaves only the floor there: no IRF, so the detector falls back to the next source."""
    rng = np.random.default_rng(11)
    floor = rng.poisson(np.full(N, 300.0)).astype(float)
    got = irf_from_reference(floor, floor.copy() + 1.0, DT, tau_ns=4.0, rho_ns=0.2)
    assert got.counts == (0.0, 0.0)
    assert best_irf([got], min_counts=500) is None
