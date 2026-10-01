"""The CURRENT (pre-upgrade) emtk app in the same states as capture_qt_populated.py. Usage: <out_dir>."""
import pathlib, sys
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.calculator.fret_calculator.gui.app import make_app

out = pathlib.Path(sys.argv[1])
for size in [(1200, 800), (800, 600)]:
    app = make_app()
    def shot(name):
        emtk_screenshot(app, out / f"before_emtk_{name}_{size[0]}x{size[1]}.png", size)
    shot("hetero_default")
    het, homo = app.hetero, app.homo
    m = het.model
    m.tau0, m.R0, m.R, m.sigma, m.use_chi = 3.5, 60.0, 55.0, 8.0, True
    het._compute_forward(); shot("hetero_forward_chi")
    m.E = 0.8; het._compute_from_efficiency(); shot("hetero_inverse")
    app.select_tab(1); app.draw(__import__("emtk.testing", fromlist=["x"]).RecordingPainter(), 0, 0, *size)
    h = homo.model
    h.tau0, h.R0, h.rho, h.t_RM = 2.5, 55.0, 20.0, 1.5
    homo._compute(); shot("homo_forward")
    h.R_DA = 45.0; homo._compute_backmap(); h.use_chi = True; h.sigma = 10.0; shot("homo_chi_backmap")
    print(size, vars(m), vars(h))
