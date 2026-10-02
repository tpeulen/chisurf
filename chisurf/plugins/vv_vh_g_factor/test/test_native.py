"""Native G calibration uses canonical formulas and complete batch export."""

import json

import numpy as np
import pytest

from chisurf.plugins.vv_vh_g_factor.core.calculations import calculate_g_factor_core
from chisurf.plugins.vv_vh_g_factor.gui.model import GFactorModel


def decay(tmp_path, name="fast.dat"):
    time = np.arange(100)
    vh = 1000 * np.exp(-time / 20) + 5
    vv = 2 * vh
    path = tmp_path / name
    np.savetxt(path, np.concatenate([vv, vh]))
    return path, vv, vh


def test_native_matches_current_core_g_not_historical_defaults(tmp_path):
    path, vv, vh = decay(tmp_path)
    model = GFactorModel()
    model.load(path)
    expected = calculate_g_factor_core(
        vv,
        vh,
        model.region,
        decay_shift=0,
        use_bg=False,
        bg_region_bounds=model.background_region,
        flip=False,
    )
    assert model.result == expected
    assert model.g_factor == pytest.approx(expected["g_factor"])
    model.manual_g = True
    model.g_override = 1.25
    model.compute()
    assert model.g_factor == 1.25


def test_native_slow_reference_manual_mixing_and_batch_export(tmp_path):
    path, _, _ = decay(tmp_path)
    slow, _, _ = decay(tmp_path, "slow.dat")
    model = GFactorModel()
    model.load(slow, slow=True)
    assert model.slow is not None and model.fast is None
    model.load(path)
    model.manual_l = True
    model.l_override = 0.1
    model.compute()
    assert model.fp_result["l1"] == 0.1 and model.fp_result["l2"] == 0.1
    model.batch_files = [str(path)]
    model.compute_batch()
    assert len(model.batch_results) == 1 and model.batch_results[0]["error"] == ""
    output = tmp_path / "batch.tsv"
    model.export_batch(output)
    assert "r_inf" in output.read_text()
    metadata = tmp_path / "calibration.json"
    model.save_results(metadata)
    assert json.loads(metadata.read_text())["settings"]["manual_l"] is True


def test_native_archive_uses_current_scientific_snapshot(tmp_path):
    from chisurf.plugins.vv_vh_g_factor.gui.app import create_app

    path, _, _ = decay(tmp_path)
    seen = {}

    class Client:
        def archive_g_factor(self, path, parameters):
            seen.update(parameters)
            return {"ok": True, "calibration_id": "test-calibration"}

    app = create_app(client=Client())
    app.model.load(path)
    assert app.archive()
    app.job.future.result(timeout=5)
    app.job.poll()
    assert seen["g_factor"] == app.model.g_factor
    assert seen["region_min"] == min(app.model.region)
    assert "test-calibration" in app.model.message
    app.close()


def test_native_no_data_reference_does_not_fabricate_anisotropy(tmp_path):
    slow, _, _ = decay(tmp_path, "slow_only.dat")
    model = GFactorModel()
    model.load(slow, slow=True)
    assert model.g_factor is None
    assert np.all(np.isnan(model.decay_series(slow=True)["r_corrected"]))


def test_native_all_controls_and_populated_plots_have_tooltips(tmp_path, monkeypatch):
    from emtk import im
    from emtk.pil_painter import PilPainter

    from chisurf.plugins.vv_vh_g_factor.gui.app import create_app

    path, _, _ = decay(tmp_path)
    app = create_app()
    app.model.load(path)
    app.model.manual_g = True
    app.model.manual_tau = True
    app.model.manual_rs = True
    app.model.manual_l = True
    tips = []
    monkeypatch.setattr(im, "set_item_tooltip", lambda text: tips.append(text))
    app.draw(PilPainter(1200, 800), 0, 0, 1200, 800)
    # the form fields take their tooltips from the spec descriptions (audited by test_emtk_vv_vh_g_factor_parity)
    assert len(tips) > 10 and all(tips)
    app.close()
