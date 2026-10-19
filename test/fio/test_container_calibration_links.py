"""A measurement container names the calibrations it uses; each is stored once.

Two measurements of one day share its IRF and buffers. Before, a container could
only point at raws beside it, so a calibration was either copied next to every
measurement or not linked at all -- which calibration belonged to which
measurement was only written in prose.
"""

from __future__ import annotations

import hashlib

import pytest

from chisurf.core.fio.pto import Measurement, PtoMfdbError


@pytest.fixture()
def record(tmp_path):
    rec = tmp_path / "rec"
    irf = rec / "calibrations" / "2014-08-12_pq-hydraharp" / "h2o-scatter-irf"
    irf.mkdir(parents=True)
    (irf / "irf-0000.ht3").write_bytes(b"irf photons")
    (irf / "irf-0001.ht3").write_bytes(b"more irf photons")
    for m in ("0M-urea", "7.5M-urea"):
        (rec / "measurements" / m).mkdir(parents=True)
    return rec, irf


def _container(path):
    m = Measurement.create_empty(path, title=path.stem)
    m.commit()
    m.close()
    return path


def test_two_measurements_link_one_calibration_by_relative_path(record):
    rec, irf = record
    for name in ("0M-urea", "7.5M-urea"):
        pto = _container(rec / "measurements" / name / f"{name}.mmfdb.pto")
        with Measurement.open(pto, writable=True) as m:
            assert m.link_calibration(irf, rec, content="clean H2O: scatter and IRF") == 0
        with Measurement.open(pto) as m:
            (cal,) = m.calibrations()
        assert cal["path"] == "../../calibrations/2014-08-12_pq-hydraharp/h2o-scatter-irf"
        assert cal["resolved"] == irf.resolve() and cal["files"] == 2
        assert cal["content"] == "clean H2O: scatter and IRF"
        f = cal["file_list"][0]
        assert f["resolved"].read_bytes() == b"irf photons"
        assert f["checksum"] == hashlib.sha256(b"irf photons").hexdigest()
        assert b"/private/" not in pto.read_bytes() and str(rec).encode() not in pto.read_bytes()
    assert len(list(irf.iterdir())) == 2  # nothing copied beside the measurements


def test_a_second_calibration_keeps_its_own_files(record):
    rec, irf = record
    buf = irf.parent / "buffer-0M-urea"
    buf.mkdir()
    (buf / "buffer-0000.ht3").write_bytes(b"buffer")
    pto = _container(rec / "measurements" / "0M-urea" / "0M-urea.mmfdb.pto")
    with Measurement.open(pto, writable=True) as m:
        m.link_calibration(irf, rec)
        assert m.link_calibration(buf, rec) == 1
    with Measurement.open(pto) as m:
        cals = m.calibrations()
    assert [c["name"] for c in cals] == ["h2o-scatter-irf", "buffer-0M-urea"]
    assert [f["name"] for f in cals[1]["file_list"]] == ["buffer-0000.ht3"]
    assert len(cals[0]["file_list"]) == 2


def test_a_calibration_outside_the_record_is_refused(record, tmp_path):
    rec, _irf = record
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "x.ht3").write_bytes(b"x")
    pto = _container(rec / "measurements" / "0M-urea" / "0M-urea.mmfdb.pto")
    with Measurement.open(pto, writable=True) as m, pytest.raises(PtoMfdbError):
        m.link_calibration(elsewhere, rec)
