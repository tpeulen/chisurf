"""Native fit actions and rendered toolkit-free boundary."""

import subprocess
import sys
from concurrent.futures import CancelledError

import numpy as np

from chisurf.plugins.burst.burst_gs.gui.app import create_app


def test_native_render_does_not_load_qt_or_log_errors():
    code = """
import sys, logging
class Fail(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.ERROR:
            raise AssertionError(record.getMessage())
logging.getLogger().addHandler(Fail())
class Painter:
    def text_width(self, text): return len(str(text))*7
    def line_height(self): return 14
    def __getattr__(self,name): return lambda *a, **kw: None
from chisurf.plugins.burst.burst_gs.gui.app import create_app as gs
from chisurf.plugins.burst.burst_fcs_correlator.gui.app import create_app as fcs
for factory in (gs, fcs):
    app = factory()
    app.draw(Painter(), 0., 0., 1000., 700.)
    app.close()
qt = [m for m in sys.modules if m.startswith(('qtpy','PyQt','PySide'))]
assert not qt, qt
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr


def test_native_real_simulation_fit_exports_numerical_rates(tmp_path, caplog):
    app = create_app()
    model = app.model
    model.use_simulation = True
    model.sim_n_bursts = 8
    model.sim_photons_per_burst = 30
    model.max_iterations = 10
    try:
        app.controller.run()
        app.controller._future.result(timeout=30)
        app.controller.poll()
        assert model.analysis is not None
        assert np.isfinite(model.analysis.fit.log_likelihood)
        assert model.analysis.fit.rate_matrix.shape == (2, 2)

        class Painter:
            def text_width(self, text):
                return len(str(text)) * 7

            def line_height(self):
                return 14

            def __getattr__(self, name):
                return lambda *args, **kwargs: None

        app.draw(Painter(), 0.0, 0.0, 1000.0, 700.0)
        assert not [record for record in caplog.records if record.levelno >= 40]

        out = tmp_path / "kinetics.csv"
        app.controller.export(out)
        import csv

        with out.open() as stream:
            values = dict(list(csv.reader(stream))[1:])
        assert np.isclose(
            float(values["k_12_per_s"]), model.analysis.fit.rate_matrix[1, 0], rtol=1e-5
        )
        previous = model.analysis
        app.controller.run()
        app.controller.stop()
        try:
            app.controller._future.result(timeout=30)
        except CancelledError:
            pass
        app.controller.poll()
        assert model.analysis is previous
    finally:
        app.close()
