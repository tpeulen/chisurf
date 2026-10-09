"""Native drop grouping, lossless conversion, errors and state."""

import json
from pathlib import Path

import pytest

from chisurf.core.fio.pto import Measurement
from chisurf.plugins.core.tttr_to_pto.gui.app import TttrToPtoApp

DATA = (
    Path(__file__).resolve().parents[4]
    / "plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"
)


def finish(app):
    while app.job.running or app.pending:
        app.job.future.result(timeout=30)
        app.poll()


@pytest.mark.skipif(not (DATA / "m000.spc").exists(), reason="BH SPC fixture absent")
def test_drop_packs_sorted_group_sidecar_then_recovers_every_byte(tmp_path):
    app = TttrToPtoApp()
    try:
        sources = []
        originals = {}
        for name in ("m000.spc", "m001.spc"):
            source = tmp_path / name
            source.write_bytes((DATA / name).read_bytes())
            sources.append(source)
            originals[name] = source.read_bytes()
        sidecar = tmp_path / "m000.set"
        sidecar.write_bytes(b"BH settings kept byte for byte\r\n")
        originals[sidecar.name] = sidecar.read_bytes()
        assert app.add_paths([sources[1], sidecar, sources[0]])
        finish(app)
        pack = app.rows[-1]
        assert pack["action"] == "pack" and pack["status"] == "verified"
        assert [Path(p).name for p in pack["paths"]] == ["m000.spc", "m001.spc"]
        target = tmp_path / "m000.pto"
        assert pack["outputs"] == [str(target)]
        for name, payload in originals.items():
            assert (tmp_path / name).read_bytes() == payload
        with Measurement.open(target, writable=False) as measurement:
            assert measurement.verify() == []
        container_bytes = target.read_bytes()
        # Rename sources before unpacking, testing recovery as well as preservation.
        for name in originals:
            (tmp_path / name).rename(tmp_path / (name + ".saved"))
        assert app.add_paths([target])
        finish(app)
        assert app.rows[-1]["status"] == "verified"
        assert target.read_bytes() == container_bytes
        for name, payload in originals.items():
            assert (tmp_path / name).read_bytes() == payload
        # Repeating an unpack with existing identical files is also supported.
        assert app.add_paths([target])
        finish(app)
        assert app.rows[-1]["status"] == "verified"
        state = json.loads(json.dumps(app.export_settings()))
        app.restore_settings(state)
        assert app.export_settings() == state
        assert not app.pending and not app.job.running
    finally:
        app.close()


def test_rejects_sidecar_missing_file_and_reports_async_errors(tmp_path):
    sidecar = tmp_path / "alone.set"
    sidecar.write_bytes(b"sidecar")
    app = TttrToPtoApp(extractor=lambda path: (_ for _ in ()).throw(ValueError("bad checksum")))
    try:
        assert not app.add_paths([sidecar, tmp_path / "missing.ptu"])
        assert all(row["status"] == "rejected" for row in app.rows)
        bad = tmp_path / "bad.pto"
        bad.write_bytes(b"not a PTO")
        assert app.add_paths([bad])
        with pytest.raises(ValueError, match="bad checksum"):
            app.job.future.result(timeout=5)
        app.poll()
        assert app.rows[-1]["status"] == "error"
        assert app.rows[-1]["error"] == "bad checksum"
        assert bad.read_bytes() == b"not a PTO"
        app.clear_history()
        assert not app.rows
    finally:
        app.close()


def test_restored_pending_operations_never_reexecute(tmp_path):
    app = TttrToPtoApp()
    try:
        app.restore_settings(
            {
                "history": [
                    {
                        "paths": [str(tmp_path / "old.ptu")],
                        "action": "pack",
                        "status": "queued",
                        "outputs": [],
                        "error": "",
                    }
                ]
            }
        )
        app.poll()
        assert not app.job.running and not app.pending
        assert app.rows[0]["status"] == "interrupted"
    finally:
        app.close()


@pytest.mark.skipif(not (DATA / "m000.spc").exists(), reason="BH SPC fixture absent")
def test_content_detected_container_and_verification_failure_preserve_sources(
    tmp_path, monkeypatch
):
    source = tmp_path / "m000.spc"
    source.write_bytes((DATA / source.name).read_bytes())
    original = source.read_bytes()
    app = TttrToPtoApp()
    try:
        assert app.add_paths([source])
        finish(app)
        target = tmp_path / "m000.pto"
        renamed = tmp_path / "measurement.recording"
        renamed.write_bytes(target.read_bytes())
        assert app.accepts(renamed)
        assert app.add_paths([renamed])
        finish(app)
        assert app.rows[-1]["action"] == "unpack"
        assert app.rows[-1]["status"] == "verified"
        monkeypatch.setattr(Measurement, "verify", lambda self: ["checksum mismatch"])
        assert app.add_paths([source])
        with pytest.raises(ValueError, match="checksum mismatch"):
            app.job.future.result(timeout=30)
        app.poll()
        assert app.rows[-1]["status"] == "error"
        assert source.read_bytes() == original
    finally:
        app.close()
