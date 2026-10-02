import sys, pathlib
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.modelling.structure_tools.app import make_app
out=pathlib.Path(sys.argv[1]); out.mkdir(exist_ok=True,parents=True)
app=make_app()
for name in ("FPS JSON Editor","Docking & Screening","QuEst"):
    app.select(name)
    for size in [(1200,800),(800,600)]:
        for _ in range(4): app.draw(RecordingPainter(),0,0,*size)
        emtk_screenshot(app,out/f"h_{name.split()[0]}_{size[0]}x{size[1]}.png",size)
