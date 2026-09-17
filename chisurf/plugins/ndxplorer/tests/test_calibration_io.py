"""Saving and loading a FRET calibration.

The container route is the default and the one with a trap in it: the container
lists its objects newest-first, so "the latest calibration" was for a while the
oldest one. That is what `test_newest_wins` pins.
"""

import json

import pytest


@pytest.fixture()
def container(tmp_path):
    """An empty `.pto` measurement."""
    pto = pytest.importorskip("chisurf.core.fio.pto")
    path = tmp_path / "measurement.pto"
    with pto.Measurement.create_empty(path, title="test"):
        pass
    return path


@pytest.fixture()
def ndx(container):
    """A window stub carrying the provenance the bridge reads."""

    class _Source:
        provenance = {"container_path": str(container)}

    class _Window:
        data_source = _Source()
        constants: dict = {}

    return _Window()


def test_file_round_trip(tmp_path):
    from chisurf.plugins.ndxplorer import calibration_io as cio

    constants = {"gG/gR": 0.8, "alpha": 0.02, "forster_radius": 52.0}
    target = tmp_path / ("c" + cio.SUFFIX)
    out = cio.save_calibration(
        constants,
        path=str(target),
        note="dsDNA ruler",
        result={"report": "REPORT", "uncertainties": {"gamma": 0.05}},
    )
    assert out["ok"] and out["where"] == "file"

    back = cio.load_calibration(path=str(target))
    assert back["ok"]
    assert back["constants"] == constants
    assert back["note"] == "dsDNA ruler"
    assert back["report"] == "REPORT"
    # The payload is plain JSON on purpose: readable without this program.
    assert json.loads(target.read_text())["format"] == "chisurf.fret_calibration"


def test_foreign_file_is_refused(tmp_path):
    from chisurf.plugins.ndxplorer import calibration_io as cio

    other = tmp_path / "other.json"
    other.write_text('{"format": "something else"}')
    assert cio.load_calibration(path=str(other))["ok"] is False


def test_container_round_trip(ndx, container):
    from chisurf.plugins.ndxplorer import calibration_io as cio

    assert cio.container_of(ndx) == str(container)
    constants = {"gG/gR": 0.81, "alpha": 0.019}
    out = cio.save_calibration(constants, ndx=ndx, note="run A")
    assert out["ok"] and out["where"] == "container"

    back = cio.load_calibration(ndx=ndx)
    assert back["ok"] and back["where"] == "container"
    assert back["constants"] == constants


def test_newest_wins_and_earlier_is_kept(ndx):
    """A second save does not overwrite the first, and 'load' takes the later.

    Both halves matter: keeping every calibration is the reason to put them in
    the measurement at all, and the one loaded by default must still be the
    most recent. No sleep between the saves: `saved_utc` is recorded to the
    microsecond precisely so that back-to-back saves still order.
    """
    from chisurf.plugins.ndxplorer import calibration_io as cio

    first, second = {"gG/gR": 0.80}, {"gG/gR": 0.85}
    cio.save_calibration(first, ndx=ndx, note="run A")
    cio.save_calibration(second, ndx=ndx, note="run B")

    stored = cio.stored_calibrations(ndx)
    assert [d["note"] for d in stored] == ["run A", "run B"]
    assert cio.load_calibration(ndx=ndx)["constants"] == second
    assert cio.load_calibration(ndx=ndx, uid=stored[0]["uid"])["constants"] == first


def test_no_container_and_no_path_is_an_error():
    from chisurf.plugins.ndxplorer import calibration_io as cio

    out = cio.save_calibration({"gG/gR": 0.8}, ndx=None, embed=True)
    assert out["ok"] is False and "no container" in out["error"]


def test_history_is_bounded_and_drops_the_oldest(ndx):
    """More saves than the limit keeps the last few, and keeps the *right* few.

    The trap is in the second half. Removing an object frees its slot and the
    next save reuses it, so once anything has been pruned the container no
    longer lists calibrations in write order -- a FIFO that trusts that order
    silently starts discarding the newest save and returning a stale one. Both
    the prune and the readers therefore sort on the payload's own timestamp,
    and this pins it by saving well past the limit and asking for the latest.
    """
    from chisurf.plugins.ndxplorer import calibration_io as cio

    keep = cio.CALIBRATION_HISTORY
    n = keep + 4
    for i in range(n):
        cio.save_calibration({"gG/gR": 0.1 * (i + 1)}, ndx=ndx, note=f"run {i}")

    stored = cio.stored_calibrations(ndx)
    assert len(stored) == keep
    # The survivors are the last `keep` written, oldest first.
    assert [d["note"] for d in stored] == [f"run {i}" for i in range(n - keep, n)]
    latest = cio.load_calibration(ndx=ndx)
    assert latest["ok"]
    assert latest["constants"]["gG/gR"] == pytest.approx(0.1 * n)


def test_history_bound_survives_repeated_pruning(ndx):
    """Saving in two bursts stays bounded -- the second burst prunes again.

    A prune that only ran while the history was growing for the first time
    would leave the bound holding once and never again; the burst boundary is
    also where slot reuse first makes position lie.
    """
    from chisurf.plugins.ndxplorer import calibration_io as cio

    keep = cio.CALIBRATION_HISTORY
    for i in range(keep + 2):
        cio.save_calibration({"gG/gR": 0.01 * i}, ndx=ndx, note=f"a{i}")
    assert len(cio.stored_calibrations(ndx)) == keep

    for i in range(keep + 2):
        cio.save_calibration({"gG/gR": 0.5 + 0.01 * i}, ndx=ndx, note=f"b{i}")
    stored = cio.stored_calibrations(ndx)
    assert len(stored) == keep
    assert [d["note"] for d in stored] == [f"b{i}" for i in range(2, keep + 2)]


def test_the_newest_calibration_is_what_the_bridge_restores(ndx, container):
    """What ndX puts in its parameters after pruning is the newest save.

    The bridge reads the container by itself rather than through
    `load_calibration`, so the ordering fix has to hold on that path too -- it
    is the one the user actually sees when a `.pto` is opened.
    """
    from chisurf.plugins.ndxplorer import calibration_io as cio

    bridge = pytest.importorskip("chisurf.plugins.ndxplorer.calibration_bridge")

    n = cio.CALIBRATION_HISTORY + 4
    for i in range(n):
        cio.save_calibration({"gG/gR": 0.1 * (i + 1)}, ndx=ndx, note=f"run {i}")

    constants = bridge.saved_constants_from_container(str(container))
    assert constants["gG/gR"] == pytest.approx(0.1 * n)
