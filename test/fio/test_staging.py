"""Tests for the Qt-free slow-storage staging helper.

Covers :mod:`chisurf.core.fio.staging`: the slow/fast decision, progress
reporting, cancellation, ephemeral cleanup, and that a staged load produces
data identical to a direct ``tttrlib`` read.
"""

import pathlib

import pytest

from chisurf.core.fio import staging

HERE = pathlib.Path(__file__).resolve().parents[1]  # test/
PTU = HERE / "data" / "clsm" / "Leica_SP8.ptu"
SPC = HERE / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"


@pytest.fixture(autouse=True)
def _clear_lut_context():
    """Reset the process-global active-setup LUT context around each test."""
    from chisurf.core.fio.lut_context import clear_active_setup_lut

    clear_active_setup_lut()
    yield
    clear_active_setup_lut()


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Point the staging cache at a tmp dir so leftovers are easy to assert."""
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(staging, "_cache_dir", lambda: cache)
    return cache


def _make_file(path: pathlib.Path, size: int) -> pathlib.Path:
    path.write_bytes(bytes((i * 37) % 256 for i in range(size)))
    return path


def test_fast_source_not_staged(tmp_path, isolated_cache):
    src = _make_file(tmp_path / "fast.dat", 4 * 1024 * 1024)
    # Local disk easily beats a 0 MB/s threshold -> never staged.
    local, was_staged = staging.stage_path_if_slow(src, threshold_mbps=0.0, min_size=0)
    assert was_staged is False
    assert local == src
    assert not any(isolated_cache.iterdir())  # no temp created


def test_min_size_gate(tmp_path, isolated_cache):
    src = _make_file(tmp_path / "small.dat", 1024 * 1024)
    # Even a force-slow threshold is skipped when below the min-size gate.
    local, was_staged = staging.stage_path_if_slow(
        src, threshold_mbps=1e9, min_size=8 * 1024 * 1024
    )
    assert was_staged is False
    assert local == src
    assert not any(isolated_cache.iterdir())


def test_slow_source_staged_with_progress(tmp_path, isolated_cache):
    size = 5 * 1024 * 1024
    src = _make_file(tmp_path / "slow.dat", size)

    events = []
    local, was_staged = staging.stage_path_if_slow(
        src,
        threshold_mbps=1e9,  # everything looks slow
        min_size=0,
        probe_bytes=512 * 1024,
        chunk_bytes=256 * 1024,
        progress_cb=lambda *a: events.append(a),
    )

    assert was_staged is True
    assert local.exists()
    assert local.name == src.name  # name preserved for tttrlib
    assert local.read_bytes() == src.read_bytes()  # byte-exact copy
    assert local.parent.parent == isolated_cache  # staged under cache dir

    # progress: monotonic bytes, ends at total, positive speed throughout
    assert len(events) >= 2
    done = [e[0] for e in events]
    assert done == sorted(done)
    assert done[-1] == size
    assert all(e[1] == size for e in events)  # total reported
    assert all(e[2] > 0 for e in events)  # mbps > 0


def test_cancel_mid_copy(tmp_path, isolated_cache):
    src = _make_file(tmp_path / "cancel.dat", 5 * 1024 * 1024)

    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 2  # allow the probe, abort during the copy

    with pytest.raises(staging.StagingCancelled):
        staging.stage_path_if_slow(
            src,
            threshold_mbps=1e9,
            min_size=0,
            probe_bytes=256 * 1024,
            chunk_bytes=256 * 1024,
            cancel_cb=cancel,
        )

    # the partial copy must have been removed
    assert not any(isolated_cache.iterdir())


def test_staged_source_cleans_up_even_on_error(tmp_path, isolated_cache):
    src = _make_file(tmp_path / "ctx.dat", 5 * 1024 * 1024)

    captured = {}
    with pytest.raises(ValueError):
        with staging.staged_source(
            src, threshold_mbps=1e9, min_size=0, probe_bytes=256 * 1024
        ) as local:
            captured["local"] = local
            assert local.exists()
            raise ValueError("boom")

    assert not captured["local"].exists()
    assert not any(isolated_cache.iterdir())


def test_disabled_via_settings(tmp_path, isolated_cache, monkeypatch):
    import chisurf.settings as settings

    monkeypatch.setitem(settings.cs_settings, "data_loading", {"enabled": False})
    src = _make_file(tmp_path / "disabled.dat", 5 * 1024 * 1024)
    local, was_staged = staging.stage_path_if_slow(src, threshold_mbps=1e9, min_size=0)
    assert was_staged is False
    assert local == src


@pytest.mark.skipif(not PTU.is_file(), reason="sample PTU not available")
def test_open_tttr_staged_matches_direct():
    tttrlib = pytest.importorskip("tttrlib")
    direct = tttrlib.TTTR(str(PTU)).get_n_valid_events()
    staged = staging.open_tttr(str(PTU), threshold_mbps=1e9, min_size=0)
    assert staged.get_n_valid_events() == direct


@pytest.mark.skipif(not PTU.is_file(), reason="sample PTU not available")
def test_open_tttr_fast_path_no_leftover(isolated_cache):
    pytest.importorskip("tttrlib")
    # Local sample is fast -> not staged, nothing left in the cache.
    staging.open_tttr(str(PTU))
    assert not any(isolated_cache.iterdir())


# --- LUT / photon-shift aware reading -------------------------------------
#
# open_tttr is the single seam that applies per-routing-channel TAC
# linearization LUTs and photon-level micro-time shifts when a setup is
# associated with the read. These tests pin the contract: default reads are
# byte-identical to a plain tttrlib open; applied LUTs are reproducible.

import numpy as np  # noqa: E402


def _spc_lut_for_first_channel():
    """Build a real Felekyan LUT for the first routing channel of the SPC fixture."""
    tttrlib = pytest.importorskip("tttrlib")
    from chisurf.plugins.tttr.tttr_lut_tools.core import tac_lut

    t = tttrlib.TTTR(str(SPC))
    ch = sorted(int(c) for c in set(int(x) for x in t.get_used_routing_channels()))[0]
    n_mt = int(t.header.get_effective_number_of_micro_time_channels())
    counts = np.bincount(
        np.asarray(t.get_tttr_by_channel([ch]).micro_times), minlength=n_mt
    ).astype(float)
    tbl = tac_lut.build_linearization_table(counts, 0, len(counts), n_mt, 0)
    return ch, np.asarray(tbl["NTAC_fract"], dtype=np.float64)


@pytest.mark.skipif(not SPC.is_file(), reason="sample SPC not available")
def test_open_tttr_no_lut_is_raw():
    """No LUT / apply_lut=False -> identical micro-times to a plain open."""
    tttrlib = pytest.importorskip("tttrlib")
    raw = np.asarray(tttrlib.TTTR(str(SPC)).micro_times)
    ch, ntac = _spc_lut_for_first_channel()

    seam = np.asarray(staging.open_tttr(str(SPC)).micro_times)
    assert np.array_equal(raw, seam)

    # LUT supplied but gate off -> still raw.
    off = np.asarray(
        staging.open_tttr(str(SPC), channel_luts={ch: ntac}, apply_lut=False).micro_times
    )
    assert np.array_equal(raw, off)


@pytest.mark.skipif(not SPC.is_file(), reason="sample SPC not available")
def test_open_tttr_lut_applied_and_reproducible():
    """apply_lut=True changes the data and, with the fixed seed, is reproducible."""
    tttrlib = pytest.importorskip("tttrlib")
    raw = np.asarray(tttrlib.TTTR(str(SPC)).micro_times)
    ch, ntac = _spc_lut_for_first_channel()

    a = np.asarray(staging.open_tttr(str(SPC), channel_luts={ch: ntac}, apply_lut=True).micro_times)
    b = np.asarray(staging.open_tttr(str(SPC), channel_luts={ch: ntac}, apply_lut=True).micro_times)

    assert not np.array_equal(raw, a)  # correction did something
    assert np.array_equal(a, b)  # fixed-seed dithering -> reproducible


@pytest.mark.skipif(not SPC.is_file(), reason="sample SPC not available")
def test_open_tttr_channel_shift_wraps():
    """A photon-level channel shift mutates the data independent of apply_lut."""
    tttrlib = pytest.importorskip("tttrlib")
    raw = np.asarray(tttrlib.TTTR(str(SPC)).micro_times)
    ch, _ = _spc_lut_for_first_channel()
    shifted = np.asarray(staging.open_tttr(str(SPC), channel_shifts={ch: 5}).micro_times)
    assert not np.array_equal(raw, shifted)


@pytest.mark.skipif(not SPC.is_file(), reason="sample SPC not available")
def test_open_tttr_uses_active_setup_context():
    """When the caller passes no correction, open_tttr consults the global context.

    This is the general 'route all TTTR through a routine that accounts for setup
    specifics' mechanism: publish once, every seam read is LUT-aware.
    """
    tttrlib = pytest.importorskip("tttrlib")
    from chisurf.core.fio import lut_context

    ch, ntac = _spc_lut_for_first_channel()
    raw = np.asarray(tttrlib.TTTR(str(SPC)).micro_times)

    # no context -> raw
    assert np.array_equal(raw, np.asarray(staging.open_tttr(str(SPC)).micro_times))

    # publish an active setup -> a plain open applies it
    lut_context.set_active_setup_lut({ch: ntac}, {}, apply_lut=True)
    assert not np.array_equal(raw, np.asarray(staging.open_tttr(str(SPC)).micro_times))

    # explicit apply_lut=False forces raw despite the context (inspection opt-out)
    assert np.array_equal(raw, np.asarray(staging.open_tttr(str(SPC), apply_lut=False).micro_times))

    # clearing returns to raw
    lut_context.clear_active_setup_lut()
    assert np.array_equal(raw, np.asarray(staging.open_tttr(str(SPC)).micro_times))


@pytest.mark.skipif(not SPC.is_file(), reason="sample SPC not available")
def test_apply_setup_lut_in_place():
    """apply_setup_lut is the shared in-place LUT correction for a raw TTTR.

    Any decay-preview / analysis path that opens a raw ``tttrlib.TTTR`` should
    call this before histogramming so the result is not silently uncorrected.
    """
    tttrlib = pytest.importorskip("tttrlib")
    ch, ntac = _spc_lut_for_first_channel()

    # gate off / no LUT -> no-op, returns False
    t0 = tttrlib.TTTR(str(SPC))
    raw = np.asarray(t0.micro_times).copy()
    assert staging.apply_setup_lut(t0, {ch: ntac}, apply_lut=False) is False
    assert np.array_equal(raw, np.asarray(t0.micro_times))

    # gate on -> mutates in place, returns True, matches open_tttr's correction
    t1 = tttrlib.TTTR(str(SPC))
    assert staging.apply_setup_lut(t1, {ch: ntac}, apply_lut=True) is True
    ref = staging.open_tttr(str(SPC), channel_luts={ch: ntac}, apply_lut=True)
    assert np.array_equal(np.asarray(t1.micro_times), np.asarray(ref.micro_times))
