"""Native browser reads, numerical gating/selection and exports."""

from concurrent.futures import CancelledError

import numpy as np
import pandas as pd

from chisurf.core.datastore import row_count
from chisurf.plugins.burst.burst_browser.gui.app import create_app


def test_native_load_gates_selection_and_exports(tmp_path, caplog):
    app = create_app()
    rows = pd.DataFrame(
        {
            "First Photon": [0, 10, 20],
            "Last Photon": [9, 19, 29],
            "Number of Photons": [100, 200, 300],
            "E": [0.1, 0.5, 0.9],
            "S": [0.4, 0.5, 0.6],
        }
    )
    interleaved = pd.DataFrame(np.zeros((7, 5)), columns=rows.columns)
    interleaved.loc[1::2] = rows.values
    path = tmp_path / "test.bur"
    interleaved.to_csv(path, sep="\t", index=False)
    try:
        app.load_bur(path)
        app.controller._future.result(timeout=5)
        app.controller.poll()
        assert row_count(app.table) == 3
        app.model.e_min, app.model.e_max = 0.3, 0.7
        app.model.refresh()
        np.testing.assert_array_equal(app.model.masked_row_indices(), [1])
        app.model.hist_column = "E"
        assert app.model.histogram()["counts"].sum() == 1
        app.model.selected_indices = [0, 1, 2]
        output = tmp_path / "selected.csv"
        app.controller.export(output, selected=True)
        exported = pd.read_csv(output, sep="\t")
        np.testing.assert_allclose(exported["E"], [0.5])

        class Painter:
            def text_width(self, text):
                return len(str(text)) * 7

            def line_height(self):
                return 14

            def __getattr__(self, name):
                return lambda *args, **kwargs: None

        app.draw(Painter(), 0.0, 0.0, 1200.0, 800.0)
        assert not [record for record in caplog.records if record.levelno >= 40]
        previous = app.table
        app.controller.load(path)
        app.controller.stop()
        try:
            app.controller._future.result(timeout=5)
        except CancelledError:
            pass
        app.controller.poll()
        assert app.table is previous
        app.controller.clear()
        assert app.table is None
        assert not app.model.have_E and not app.model.have_S
    finally:
        app.close()
