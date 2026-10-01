"""The upgraded emtk app in the states of capture_qt_populated.py. Usage: <out_dir>."""
import pathlib, sys
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.calculator.fret_calculator.gui.app import make_app

out = pathlib.Path(sys.argv[1])
for size in [(1200, 800), (800, 600)]:
    app = make_app()
    def shot(name):
        for _ in range(3): app.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(app, out / f"after_{name}_{size[0]}x{size[1]}.png", size)
    shot("populated_hetero_default")
    m = app.model.hetero
    m.tau0, m.R0, m.R, m.sigma, m.use_chi = 3.5, 60.0, 55.0, 8.0, True
    m.compute_forward(); shot("populated_hetero_forward_chi")
    m.E = 0.8; m.from_efficiency(); shot("populated_hetero_inverse")
    m.E = 1.0; m.from_efficiency(); shot("populated_hetero_error")
    app.select_tab(1); app.draw(RecordingPainter(), 0, 0, *size)
    h = app.model.homo
    h.tau0, h.R0, h.rho, h.t_RM = 2.5, 55.0, 20.0, 1.5
    h.compute_forward(); shot("populated_homo_forward")
    h.R_DA = 45.0; h.backmap(); h.use_chi = True; h.sigma = 10.0; shot("populated_homo_chi_backmap")
    print(size, vars(m).keys() and {k: v for k, v in vars(m).items() if k not in ("client", "_series_cache")}, {k: v for k, v in vars(h).items() if k not in ("client", "_series_cache")})

# dialogs: help window, guided tour (awaiting a field), a narrow window, the dropped-file notice
size = (1200, 800)
app = make_app()
def shot(name, size=size):
    for _ in range(3): app.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(app, out / f"after_{name}_{size[0]}x{size[1]}.png", size)
app.show_help(); shot("populated_help")
app.help_window.hide(); app.tour.start(); shot("populated_guide_step1")
app.tour.step_idx = 5; app.tour._notify_change(); shot("populated_guide_homo_tab")
app.tour.stop(); app.files_dropped(["/tmp/run.ptu"]); shot("populated_dropped_file")
app = make_app(); app.model.hetero.R = 55.0; app.model.hetero.compute_forward(); shot("populated_narrow", (500, 500))
