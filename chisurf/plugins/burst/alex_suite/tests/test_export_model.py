"""The Qt-free ALEX-Suite CSV export model (card AS3) and the native export step's Write button, on a real table."""

from __future__ import annotations

import numpy as np

from chisurf.plugins.burst.alex_suite.gui.export_model import LegacyExportModel, _export_stem
from chisurf.plugins.emtk_test_input import Driver


def _table(path, n=120, e_true=0.45, seed=7):
    rng = np.random.default_rng(seed)
    total = rng.poisson(200, n).astype(float) + 20.0
    green = total * 0.5
    i_da = rng.binomial(green.astype(int), e_true).astype(float)
    cols = {
        "Number of Photons (green)": green - i_da,
        "Number of Photons (red)": i_da,
        "Number of Photons (yellow)": total - green,
        "Duration (ms)": np.full(n, 1.0),
    }
    lines = ["\t".join(cols)] + ["\t".join(f"{v:.10g}" for v in row) for row in np.column_stack(list(cols.values()))]
    path.write_text("\n".join(lines) + "\n")
    return path


PARTS = {"metadata": True, "e_histogram": True, "s_histogram": True, "histogram_2d": True, "original_bursts": True}


def test_the_export_writes_the_five_files_beside_the_table(tmp_path):
    table = _table(tmp_path / "sample.bur")
    model = LegacyExportModel()
    model.set_burst_files([table])
    assert model._bur_files == [table] and "1 burst file" in model._status_text
    written = model.run_export(str(table), "dsDNA", "TE", PARTS)
    assert len(written) == 5 and all(p.parent == tmp_path and p.is_file() for p in written)
    assert "Wrote 5 file(s)" in model.status_text


def test_no_source_and_a_bad_table_are_reported(tmp_path):
    model = LegacyExportModel()
    assert model.run_export("", "", "", PARTS) == [] and model.status_text == "Pick a burst file first."
    bad = tmp_path / "bad.bur"
    bad.write_text("a\tb\n1\t2\n")
    assert model.run_export(str(bad), "", "", PARTS) == []
    assert model.status_text.startswith("Export failed:")


def test_a_container_run_exports_beside_the_container(tmp_path):
    run = tmp_path / "m000.pto" / "sliding_window_All 0.1500#60"
    assert _export_stem(run) == tmp_path / "m000_sliding_window_All_0.1500_60"
    assert _export_stem(tmp_path / "x.bur") == tmp_path / "x"
