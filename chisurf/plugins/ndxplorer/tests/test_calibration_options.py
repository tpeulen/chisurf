"""Which factors a calibration may write, and that holding one really holds it.

Applying everything is right exactly once — the first time, on a measurement
carrying its own donor-only and acceptor-only populations. After that it is
usually wrong in one way: γ from a measurement's own populations is only as good
as those populations, and someone who determined γ on a reference sample wants
α and δ fitted *around* it rather than replaced.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.ndxplorer.calibration_bridge import optimize_calibration_from_ndx
from chisurf.plugins.ndxplorer.calibration_options import CalibrationOptions


def _window(**constants):
    """An ndX stand-in holding three-species burst data."""
    rng = np.random.default_rng(0)
    n = 3000
    kind = rng.choice([0, 1, 2], n, p=[0.25, 0.15, 0.60])
    E = np.where(kind == 2, rng.normal(0.55, 0.08, n), np.where(kind == 0, 0.02, 0.0))
    S = np.where(kind == 0, 0.95, np.where(kind == 1, 0.08, 0.55))
    size = rng.gamma(4.0, 60.0, n)

    class _DataSource:
        def __init__(self):
            self.data = {
                "Number of Photons (green)": np.clip(size * (1 - E) * S, 1, None),
                "Number of Photons (red)": np.clip(size * E * S, 1, None),
                "Number of Photons (yellow)": np.clip(size * (1 - S), 1, None),
            }

    class _Ndx:
        def __init__(self):
            self.data_source = _DataSource()
            self.constants = {
                "gG/gR": 1.0, "alpha": 0.0, "beta": 0.0, "r": 1.0,
                "Bg": 0.0, "Br": 0.0, "By": 0.0, "PhiA": 1.0, "PhiD": 1.0,
                "forster_radius": 52.0, "tauD0": 4.0, **constants,
            }

    return _Ndx()


def _run(ndx, **kwargs):
    return optimize_calibration_from_ndx(
        ndx, n_bootstrap=0, inject_columns=False, recompute=False, **kwargs)


def test_by_default_every_factor_is_written():
    result = _run(_window())
    assert result["ok"]
    assert set(result["applied_factors"]) == {"alpha", "beta", "gamma", "delta", "r0"}
    assert result["held"] == {}


def test_a_held_factor_keeps_the_window_value():
    """The point of the option, and the thing that is easy to get wrong.

    ``auto_calibrate`` refines the calibration *in place*, so a factor to be kept
    has to be remembered before the call — reading it back afterwards returns the
    refined value, and 'held fixed' would silently mean 'applied'.
    """
    ndx = _window(forster_radius=61.0)
    result = _run(ndx, factors=["alpha", "delta"])
    assert set(result["applied_factors"]) == {"alpha", "delta"}
    assert set(result["held"]) == {"beta", "gamma", "r0"}
    assert result["held"]["r0"] == pytest.approx(61.0), "the window's R0 was overwritten"


def test_what_a_held_factor_would_have_been_is_still_reported():
    """Holding one is a decision; the number it was held against justifies it."""
    result = _run(_window(), factors=["alpha"])
    assert "gamma" in result["determined"]
    assert np.isfinite(result["determined"]["gamma"])


def test_holding_everything_changes_nothing():
    ndx = _window()
    before = dict(ndx.constants)
    result = _run(ndx, factors=[])
    assert result["ok"]
    assert result["applied_factors"] == []
    for key, value in before.items():
        assert ndx.constants[key] == pytest.approx(value), key


def test_the_options_map_onto_the_bridge():
    options = CalibrationOptions(donor_lifetime=3.2)
    options.fit_gamma = False
    options.fit_r0 = True
    kwargs = options.as_kwargs()
    assert kwargs["factors"] == ["alpha", "delta", "beta", "r0"]
    assert kwargs["donor_lifetime"] == pytest.approx(3.2)
    # Every key must be one the bridge accepts.
    import inspect

    accepted = set(inspect.signature(optimize_calibration_from_ndx).parameters)
    assert set(kwargs) <= accepted, set(kwargs) - accepted


# ── backgrounds: an input, not a factor ──────────────────────────────────────

def test_a_missing_stored_background_falls_back_to_the_constants():
    """Asking for the measured background must not throw the typed one away.

    A container that never had a background step has nothing to subtract. Zeroing
    the window's own numbers *and* subtracting nothing in their place is strictly
    worse than the setting it replaced.
    """
    ndx = _window(Bg=2.0, Br=3.0, By=4.0)
    result = _run(ndx, background="measurement")
    assert result["ok"]
    assert result["background_per_burst"] == [], "this fixture has no container"
    # The typed values survived into the calibration.
    assert ndx.constants["Bg"] == pytest.approx(2.0)


def test_none_really_means_zero():
    ndx = _window(Bg=2.0, Br=3.0, By=4.0)
    result = _run(ndx, background="none")
    assert result["ok"]
    assert result["background"] == "none"


def test_a_rate_becomes_counts_through_the_burst_duration(tmp_path, monkeypatch):
    """kHz x ms = counts, and the scaling is per burst.

    A 4 ms burst carries four times the background of a 1 ms one; subtracting
    one number from both is wrong in opposite directions.
    """
    from chisurf.plugins.ndxplorer import calibration_bridge as bridge

    durations = np.array([1.0, 2.0, 4.0])
    table = {"Duration (ms)": durations}

    class _Column:
        def __init__(self, name, values=None, strings=None):
            self._name, self._values, self._strings = name, values, strings

        def name(self):
            return self._name

        def numpy(self):
            return np.asarray(self._values, dtype=float)

        def string_at(self, row):
            return self._strings[row]

    class _Store:
        def __init__(self):
            self._cols = [
                _Column("Detector", strings=["green", "red", "yellow"]),
                _Column("Rate", values=[0.5, 1.0, 2.0]),
            ]

        def n_columns(self):
            return len(self._cols)

        def n_rows(self):
            return 3

        def column(self, i):
            return self._cols[i]

    class _Obj:
        name = "background"
        uid = 1

    class _Measurement:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def artifacts(self):
            return [_Obj()]

        def get_store(self, _uid):
            return _Store()

    import chisurf.core.fio.pto as pto

    monkeypatch.setattr(pto.Measurement, "open",
                        staticmethod(lambda *_a, **_k: _Measurement()))

    class _DS:
        provenance = {"container_path": str(tmp_path / "m.pto")}

    class _Ndx:
        data_source = _DS()

    out = bridge.measured_background(_Ndx(), table)
    np.testing.assert_allclose(out["i_dd"], 0.5 * durations)   # green
    np.testing.assert_allclose(out["i_da"], 1.0 * durations)   # red
    np.testing.assert_allclose(out["i_aa"], 2.0 * durations)   # yellow


# ── fitting the background, for when nobody knows it ─────────────────────────

def _physical_window(bg_dd=5.0, bg_da=3.0, bg_aa=7.0, alpha=0.06, n=8000, seed=1):
    """Bursts where the reference populations really lack a fluorophore.

    An acceptor-only burst has NO donor: what is in the donor channel is
    background and nothing else. That is what makes the background readable at
    all, and a simulation that leaves a residual donor signal there is testing
    something else.
    """
    rng = np.random.default_rng(seed)
    kind = rng.choice([0, 1, 2], n, p=[0.30, 0.20, 0.50])
    size = rng.gamma(4.0, 60.0, n)
    E = np.where(kind == 2, rng.normal(0.55, 0.08, n), 0.0)
    dd, da, aa = np.zeros(n), np.zeros(n), np.zeros(n)
    m = kind == 0                      # donor-only: donor emits, acceptor leaks
    dd[m], da[m], aa[m] = size[m], alpha * size[m], 0.0
    m = kind == 1                      # acceptor-only: no donor at all
    dd[m], da[m], aa[m] = 0.0, 0.0, size[m]
    m = kind == 2                      # FRET
    dd[m] = size[m] * (1 - E[m])
    da[m] = size[m] * E[m] + alpha * size[m] * (1 - E[m])
    aa[m] = size[m] * 0.8
    dd += rng.poisson(bg_dd, n)
    da += rng.poisson(bg_da, n)
    aa += rng.poisson(bg_aa, n)

    class _DataSource:
        def __init__(self):
            self.data = {"Number of Photons (green)": dd,
                         "Number of Photons (red)": da,
                         "Number of Photons (yellow)": aa}

    class _Ndx:
        def __init__(self):
            self.data_source = _DataSource()
            self.constants = {"gG/gR": 1.0, "alpha": 0.0, "beta": 0.0, "r": 1.0,
                              "Bg": 0.0, "Br": 0.0, "By": 0.0, "PhiA": 1.0,
                              "PhiD": 1.0, "forster_radius": 52.0, "tauD0": 4.0}

    return _Ndx()


def test_the_background_is_recovered_from_the_populations():
    """Each reference population has one channel measuring background alone."""
    result = _run(_physical_window(), background="fit")
    assert result["ok"]
    fitted = result["background_fitted"]
    assert fitted["bg_dd"] == pytest.approx(5.0, abs=1.0)
    assert fitted["bg_aa"] == pytest.approx(7.0, abs=1.0)
    # The intercept of I_DA = alpha*I_DD + bg_da, which is what separates
    # leakage from background; a ratio of means folds one into the other.
    assert fitted["bg_da"] == pytest.approx(3.0, abs=1.5)


def test_leakage_survives_the_background_fit():
    """alpha must come out of the slope, not be inflated by the intercept."""
    result = _run(_physical_window(alpha=0.06), background="fit")
    assert result["determined"]["alpha"] == pytest.approx(0.06, abs=0.02)


def test_too_few_reference_bursts_are_not_guessed_from():
    """An absent estimate means 'not determined', not 'zero'."""
    result = _run(_physical_window(n=8000), background="fit", min_population=100000)
    assert result["background_fitted"] == {}


# ── a calibration belongs to its measurement ─────────────────────────────────

def _container_with_calibration(tmp_path, **factors):
    """A container carrying the artifact the Accurate FRET step writes."""
    import shutil

    from chisurf.core.datastore import store_from_arrays
    from chisurf.core.fio.fluorescence.burst_container import write_burst_artifact
    from chisurf.plugins.ndxplorer.calibration_bridge import CALIBRATION_ARTIFACT

    source = pathlib.Path.home() / (
        "dev/tttr-data/sm/cal1/001_60g_25r_cal1_cy3b_8_18_33bp_atto647n_alex.pto")
    if not source.exists():
        pytest.skip("the ALEX calibration container is not on this machine")
    target = tmp_path / source.name
    shutil.copy2(source, target)

    n = 3
    rows = {"label": np.arange(n, dtype=float), "E": np.array([0.02, 0.55, 0.81])}
    # Constant over the populations, which is what makes any row the whole
    # calibration — that is deliberate in the writer, and relied on here.
    for name, value in factors.items():
        rows[name] = np.full(n, float(value))
    write_burst_artifact(
        target, store_from_arrays(rows), name=CALIBRATION_ARTIFACT,
        artifact_kind="parameter_table", operation_type="calibration",
        row_grain="species", derived_from="bursts")
    return target


PLANTED = {"alpha": 0.0731, "beta": 1.234, "gamma": 0.8642,
           "delta": 0.0519, "r0": 54.3}


def test_a_stored_calibration_is_read_back(tmp_path):
    from chisurf.plugins.ndxplorer.calibration_bridge import calibration_from_container

    container = _container_with_calibration(tmp_path, **PLANTED)
    read = calibration_from_container(container)
    for name, value in PLANTED.items():
        assert read[name] == pytest.approx(value), name


def test_a_run_path_resolves_to_its_container(tmp_path):
    """Every burst reader addresses a run; the calibration is on the file."""
    from chisurf.plugins.ndxplorer.calibration_bridge import calibration_from_container

    container = _container_with_calibration(tmp_path, **PLANTED)
    run = container / "sliding_window_All 0.1500#60"
    assert calibration_from_container(run) == calibration_from_container(container)


def test_a_measurement_without_one_changes_nothing(tmp_path):
    """Absent is not zero: the window keeps the constants it had."""
    from chisurf.plugins.ndxplorer.calibration_bridge import (
        restore_calibration_from_container,
    )

    ndx = _window(alpha=0.11)
    before = dict(ndx.constants)
    assert restore_calibration_from_container(ndx, "/nowhere/none.pto") == {}
    assert ndx.constants == before


def test_restoring_keeps_what_the_measurement_does_not_carry(tmp_path):
    """Quantum yields are the window's; backgrounds are the measurement's.

    The container stores per-detector background rates, and ndX's Bg/Br/By are
    exactly those rates, so those *are* restored. What has no counterpart in the
    measurement — PhiA, PhiD — is left alone.
    """
    from chisurf.plugins.ndxplorer.calibration_bridge import (
        restore_calibration_from_container,
    )

    container = _container_with_calibration(tmp_path, **PLANTED)
    ndx = _window(Bg=2.5, Br=3.5, By=4.5, PhiA=0.8, PhiD=0.4)
    restore_calibration_from_container(ndx, container)
    assert ndx.constants["alpha"] == pytest.approx(PLANTED["alpha"])
    assert ndx.constants["beta"] == pytest.approx(PLANTED["delta"])   # ndX's name for delta
    assert ndx.constants["forster_radius"] == pytest.approx(PLANTED["r0"])
    for kept, value in (("PhiA", 0.8), ("PhiD", 0.4)):
        assert ndx.constants[kept] == pytest.approx(value), kept


def test_the_schema_is_flrcif_s_not_chisurf_s():
    """The factors are standard, and are stored under the standard names.

    ``_flr_fret_calibration_parameters`` has carried alpha, beta, gamma, delta,
    gG_gR_ratio and phi_acceptor all along, and the Forster radius has its own
    category. Writing a calibration under ad-hoc headers made the one artifact
    that most needs to be readable by something other than chisurf readable only
    by chisurf.
    """
    from chisurf.plugins.burst.accurate_fret.calibration_columns import (
        calibration_columns,
    )

    declared = {spec["column"]: spec["term"] for spec in calibration_columns()}
    assert declared["alpha"] == "_flr_fret_calibration_parameters.alpha"
    assert declared["gamma"] == "_flr_fret_calibration_parameters.gamma"
    assert declared["delta"] == "_flr_fret_calibration_parameters.delta"
    assert declared["forster_radius"] == "_flr_fret_forster_radius.forster_radius"


def test_a_container_written_before_the_schema_still_restores(tmp_path):
    """A file on disk cannot be asked to follow a newer schema."""
    from chisurf.plugins.ndxplorer.calibration_bridge import calibration_from_container

    # 'r0' is what earlier versions wrote for the Forster radius.
    container = _container_with_calibration(tmp_path, r0=57.1, gamma=0.77)
    read = calibration_from_container(container)
    assert read["r0"] == pytest.approx(57.1)
    assert read["gamma"] == pytest.approx(0.77)


def test_the_writer_and_the_reader_share_one_declaration():
    """Two directions, one file — that is what stops them drifting."""
    from chisurf.plugins.burst.accurate_fret.calibration_columns import (
        calibration_columns, column_for_factor, factor_for_column,
    )

    for spec in calibration_columns():
        assert column_for_factor(spec["factor"]) == spec["column"]
        assert factor_for_column(spec["column"]) == spec["factor"]


# ── the background is a stored parameter too ─────────────────────────────────

def test_the_stored_background_rates_are_read(tmp_path):
    """ndX's Bg/Br/By are rates, so a stored rate goes in as it stands.

    ``Fg(PIE) = Sg(PIE) - Bg`` and ``Sg(PIE)`` is ``S prompt green (kHz)``, so
    the constant is in kHz — the same unit the background step writes. No
    duration, no conversion.
    """
    from chisurf.plugins.ndxplorer.calibration_bridge import background_from_container

    source = pathlib.Path.home() / (
        "dev/tttr-data/sm/cal1/001_60g_25r_cal1_cy3b_8_18_33bp_atto647n_alex.pto")
    if not source.exists():
        pytest.skip("the ALEX calibration container is not on this machine")
    rates = background_from_container(source)
    assert set(rates) <= {"Bg", "Br", "By"}
    assert rates, "this container carries a background artifact"
    for value in rates.values():
        assert np.isfinite(value) and value >= 0.0


def test_a_measurement_with_only_a_background_still_restores(tmp_path):
    """The ordinary state: background measured, factors not yet determined.

    Requiring a calibration before anything is restored would throw away the
    part the equations use most directly.
    """
    import shutil

    from chisurf.core.datastore import store_from_arrays
    from chisurf.core.fio.fluorescence.burst_container import write_burst_artifact
    from chisurf.plugins.ndxplorer.calibration_bridge import (
        calibration_from_container, restore_calibration_from_container,
    )

    source = pathlib.Path.home() / (
        "dev/tttr-data/sm/cal1/001_60g_25r_cal1_cy3b_8_18_33bp_atto647n_alex.pto")
    if not source.exists():
        pytest.skip("the ALEX calibration container is not on this machine")
    target = tmp_path / source.name
    shutil.copy2(source, target)
    write_burst_artifact(
        target,
        store_from_arrays({
            "Detector": np.array(["green", "red", "yellow"], dtype=object),
            "Rate": np.array([1.25, 2.5, 3.75]),
        }),
        name="background", artifact_kind="background_data",
        operation_type="background_correction", row_grain="channel",
        derived_from="bursts")

    assert calibration_from_container(target) == {}, "no factors in this fixture"
    ndx = _window(Bg=99.0, Br=99.0, By=99.0)
    applied = restore_calibration_from_container(ndx, target)
    assert applied, "a background alone must still restore"
    assert ndx.constants["Bg"] == pytest.approx(1.25)
    assert ndx.constants["Br"] == pytest.approx(2.5)
    assert ndx.constants["By"] == pytest.approx(3.75)


# ── and it repopulates when the measurement changes ──────────────────────────

def _window_on(container):
    class _DataSource:
        provenance = {"container_path": str(container)}

    class _Ndx:
        def __init__(self):
            self.data_source = _DataSource()
            self.constants = {
                "gG/gR": 1.0, "alpha": 0.0, "beta": 0.0, "r": 1.0,
                "Bg": 9.0, "Br": 9.0, "By": 9.0, "PhiA": 1.0, "PhiD": 1.0,
                "forster_radius": 52.0, "tauD0": 4.0,
            }

    return _Ndx()


def _write_background(container, green, red, yellow):
    from chisurf.core.datastore import store_from_arrays
    from chisurf.core.fio.fluorescence.burst_container import write_burst_artifact

    write_burst_artifact(
        container,
        store_from_arrays({
            "Detector": np.array(["green", "red", "yellow"], dtype=object),
            "Rate": np.array([green, red, yellow], dtype=float),
        }),
        name="background", artifact_kind="background_data",
        operation_type="background_correction", row_grain="channel",
        derived_from="bursts")


@pytest.fixture
def container(tmp_path):
    import shutil

    source = pathlib.Path.home() / (
        "dev/tttr-data/sm/cal1/001_60g_25r_cal1_cy3b_8_18_33bp_atto647n_alex.pto")
    if not source.exists():
        pytest.skip("the ALEX calibration container is not on this machine")
    target = tmp_path / source.name
    shutil.copy2(source, target)
    return target


def test_a_revisit_with_nothing_changed_is_a_no_op(container):
    from chisurf.plugins.ndxplorer.calibration_bridge import refresh_stored_parameters

    ndx = _window_on(container)
    assert refresh_stored_parameters(ndx), "the first visit must populate"
    assert refresh_stored_parameters(ndx) == {}, "a revisit re-applied it"


def test_a_value_the_user_tuned_survives_a_revisit(container):
    """The window is theirs between updates; only a *changed* estimate wins."""
    from chisurf.plugins.ndxplorer.calibration_bridge import refresh_stored_parameters

    ndx = _window_on(container)
    refresh_stored_parameters(ndx)
    ndx.constants["Bg"] = 42.0
    assert refresh_stored_parameters(ndx) == {}
    assert ndx.constants["Bg"] == pytest.approx(42.0)


def test_re_running_the_background_step_repopulates(container):
    """The container is the shared surface: a new estimate reaches the window."""
    from chisurf.plugins.ndxplorer.calibration_bridge import refresh_stored_parameters

    ndx = _window_on(container)
    refresh_stored_parameters(ndx)
    _write_background(container, 2.24, 3.17, 1.05)
    assert refresh_stored_parameters(ndx), "a re-run must reach the window"
    assert ndx.constants["Bg"] == pytest.approx(2.24)
    assert ndx.constants["Br"] == pytest.approx(3.17)
    assert ndx.constants["By"] == pytest.approx(1.05)


# ── the quantum yields, and what is derived from them ────────────────────────

FULL = {"alpha": 0.07, "beta": 1.2, "gamma": 0.86, "delta": 0.05,
        "forster_radius": 54.3, "phi_acceptor": 0.32, "phi_donor": 0.45}


def _write_full_calibration(container):
    from chisurf.core.datastore import store_from_arrays
    from chisurf.core.fio.fluorescence.burst_container import write_burst_artifact
    from chisurf.plugins.ndxplorer.calibration_bridge import CALIBRATION_ARTIFACT

    rows = {"label": np.arange(3, dtype=float)}
    for name, value in FULL.items():
        rows[name] = np.full(3, float(value))
    rows["gG_gR_ratio"] = np.full(
        3, (FULL["phi_acceptor"] / FULL["phi_donor"]) / FULL["gamma"])
    write_burst_artifact(
        container, store_from_arrays(rows), name=CALIBRATION_ARTIFACT,
        artifact_kind="parameter_table", operation_type="calibration",
        row_grain="species", derived_from="bursts")


def test_the_quantum_yields_are_restored(container):
    """gamma without the yields it was measured against cannot be reapplied.

    They are inputs the calibration was determined *with*, not outputs of it, so
    ``result.factors`` never held them — which is why they were neither written
    nor restored.
    """
    from chisurf.plugins.ndxplorer.calibration_bridge import (
        restore_calibration_from_container,
    )

    _write_full_calibration(container)
    ndx = _window(PhiA=1.0, PhiD=1.0)
    restore_calibration_from_container(ndx, container)
    assert ndx.constants["PhiA"] == pytest.approx(FULL["phi_acceptor"])
    assert ndx.constants["PhiD"] == pytest.approx(FULL["phi_donor"])


def test_gg_gr_follows_from_what_was_restored(container):
    """Recomputed, not copied — so it cannot disagree with its own inputs."""
    from chisurf.plugins.ndxplorer.calibration_bridge import (
        restore_calibration_from_container,
    )

    _write_full_calibration(container)
    ndx = _window()
    restore_calibration_from_container(ndx, container)
    expected = (FULL["phi_acceptor"] / FULL["phi_donor"]) / FULL["gamma"]
    assert ndx.constants["gG/gR"] == pytest.approx(expected)


def test_a_derived_column_is_never_applied_back(container):
    """Reading it as a factor would let it drift from gamma and the yields."""
    from chisurf.plugins.burst.accurate_fret.calibration_columns import is_derived
    from chisurf.plugins.ndxplorer.calibration_bridge import calibration_from_container

    _write_full_calibration(container)
    assert is_derived("gG_gR_ratio")
    assert "gG_gR_ratio" not in calibration_from_container(container)


def test_the_donor_yield_has_a_dictionary_term():
    """IHM-FLR defines only the acceptor's; the donor's was added centrally.

    The rule is that a missing term is created in mmfdb's extension dictionary,
    never invented in a plugin — so this asserts the term resolves, not that a
    string matches.
    """
    mmfdb = pytest.importorskip("mmfdb.schema.pdbx_metadata")
    dictionary = mmfdb.MmcifDictionary.load_bundled()
    assert dictionary.get_item(
        "_flr_fret_calibration_parameters.phi_donor") is not None


def test_gamma_is_the_detection_ratio_and_the_yields_together():
    """gG/gR is an instrument property; the yields belong to the dyes.

    gamma = (gR*phi_A)/(gG*phi_D) is one number standing for both, which is why
    a stored gamma alone cannot be moved to another instrument or another dye
    pair. Four quantities, one relation: store three, derive the fourth. This
    pins the relation the declaration's descriptions claim.
    """
    gg_gr, phi_a, phi_d = 1.35, 0.32, 0.45
    gamma = (1.0 / gg_gr) * (phi_a / phi_d)
    # The container stores gamma and the yields, and derives the detection ratio.
    assert (phi_a / phi_d) / gamma == pytest.approx(gg_gr)
    # ndX stores the detection ratio and the yields, and implies gamma; its
    # efficiency equation uses (1/(gG/gR)) * (PhiA/PhiD), which is that gamma.
    assert (1.0 / gg_gr) * (phi_a / phi_d) == pytest.approx(gamma)
