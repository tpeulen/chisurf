"""Native drop grouping, lossless conversion, errors, state and translated UI."""

import json
from pathlib import Path

import pytest
from emtk import i18n
from emtk.testing import RecordingPainter

from chisurf.core.fio.pto import Measurement
from chisurf.plugins.core.tttr_to_pto.gui.app import _CATALOG, TttrToPtoApp, tr

DATA = Path(__file__).resolve().parents[4] / "plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"


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
        state = json.loads(json.dumps(app.export_state()))
        app.restore_state(state)
        assert app.export_state() == state
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
        app.restore_state({"history": [{"paths": [str(tmp_path / "old.ptu")], "action": "pack", "status": "queued", "outputs": [], "error": ""}]})
        app.poll()
        assert not app.job.running and not app.pending
        assert app.rows[0]["status"] == "interrupted"
    finally:
        app.close()


def test_every_native_string_has_six_translations_and_ui_renders():
    old_locale = i18n.get_locale()
    app = TttrToPtoApp()
    try:
        sources = set(_CATALOG["en"])
        for locale in ("en", "de", "fr", "es", "pt", "ru"):
            assert set(_CATALOG[locale]) == sources
            assert all(_CATALOG[locale].values())
            i18n.set_locale(locale)
            assert tr("Originals stay untouched") == _CATALOG[locale]["Originals stay untouched"]
            for width, height in ((1200, 800), (800, 600)):
                painter = RecordingPainter()
                app.draw(painter, 0, 0, width, height)
                assert painter.strings
            assert app.help_locale == locale
            assert len(app.tour.steps) == 4
    finally:
        i18n.set_locale(old_locale)
        app.close()


@pytest.mark.skipif(not (DATA / "m000.spc").exists(), reason="BH SPC fixture absent")
def test_content_detected_container_and_verification_failure_preserve_sources(tmp_path, monkeypatch):
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


def test_native_interactive_controls_and_drop_area_have_translated_tooltips(monkeypatch):
    from chisurf.plugins.core.tttr_to_pto.gui import app as module

    tips = []
    monkeypatch.setattr(module.im, "set_item_tooltip", tips.append)
    app = TttrToPtoApp()
    try:
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 800, 600)
        expected = [
            "Walk through packing, unpacking and sidecar handling.",
            "Read the conversion rules and verification guarantees.",
            "Remove completed status rows; files on disk stay untouched.",
            "Drop multiple vendor files together to pack one measurement. Matching SET sidecars are included automatically.",
        ]
        assert all(tr(tip) in tips for tip in expected)
    finally:
        app.close()
