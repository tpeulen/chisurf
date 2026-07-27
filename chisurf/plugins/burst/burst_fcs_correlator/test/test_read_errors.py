"""An unreadable burst-FCS input must not be reported as a successful run.

Regression tests for RF-472: ``correlate_burst_file`` used to return an empty
curve list both when the TTTR file could not be opened and when the file was
read but produced no curve, so ``burst_fcs.correlate_file`` answered
``{"ok": True, "curves": []}`` for an analysis in which not a single photon was
read.
"""

import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
TTTR_FILE = REPO_ROOT / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"


def _correlate(tttr_path, ranges=()):
    """Call the RPC handler for one file with no channel pairs configured."""
    from chisurf.plugins.burst.burst_fcs_correlator.backend.services import (
        correlate_file_handler,
    )

    return correlate_file_handler(str(tttr_path), [list(r) for r in ranges], [])


def test_core_raises_when_the_file_does_not_exist(tmp_path):
    from chisurf.plugins.burst.burst_fcs_correlator.core import (
        BurstFcsSettings,
        correlate_burst_file,
    )

    missing = tmp_path / "not_there.spc"
    with pytest.raises(FileNotFoundError):
        correlate_burst_file(missing, [(0, 10)], [], BurstFcsSettings())


def test_core_raises_when_the_file_cannot_be_read(tmp_path, monkeypatch):
    from chisurf.plugins.burst.burst_fcs_correlator.core import algorithms

    unreadable = tmp_path / "garbage.spc"
    unreadable.write_bytes(b"not a photon stream")
    monkeypatch.setattr(algorithms, "open_tttr", lambda *a, **k: None)

    with pytest.raises(OSError) as excinfo:
        algorithms.correlate_burst_file(unreadable, [(0, 10)], [], algorithms.BurstFcsSettings())
    assert not isinstance(excinfo.value, FileNotFoundError)


def test_handler_reports_a_missing_file_as_not_found(tmp_path):
    r = _correlate(tmp_path / "not_there.spc", ranges=[(0, 10)])
    assert r["ok"] is False
    assert r["error_code"] == "NOT_FOUND"
    assert "not_there.spc" in r["error"]


def test_handler_reports_an_unreadable_file_as_operation_failed(tmp_path, monkeypatch):
    from chisurf.plugins.burst.burst_fcs_correlator.core import algorithms

    unreadable = tmp_path / "garbage.spc"
    unreadable.write_bytes(b"not a photon stream")
    monkeypatch.setattr(algorithms, "open_tttr", lambda *a, **k: None)

    r = _correlate(unreadable, ranges=[(0, 10)])
    assert r["ok"] is False
    assert r["error_code"] == "OPERATION_FAILED"


@pytest.mark.skipif(not TTTR_FILE.exists(), reason="TTTR test file not available")
def test_a_readable_file_with_no_bursts_still_succeeds():
    r = _correlate(TTTR_FILE)
    assert r["ok"] is True
    assert r["result"]["curves"] == []
