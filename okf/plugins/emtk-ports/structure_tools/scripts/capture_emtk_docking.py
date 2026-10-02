import sys, tempfile, time, pathlib
sys.path.insert(0,'okf/plugins/emtk-ports/structure_tools/scripts')
import fixtures
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.modelling.structure_tools.cards.docking import make_app
out=pathlib.Path(sys.argv[1]); out.mkdir(exist_ok=True,parents=True)
work=pathlib.Path(tempfile.mkdtemp())
fps,pdbs=fixtures.make(work)
app=make_app(); s=app.session
s.add_pdbs([str(p) for p in pdbs]); s.fps_json=str(fps); s.output_dir=str(work/'dock_out'); s.n_frames=60; s.n_repeats=int(sys.argv[2]) if len(sys.argv)>2 else 1
for size in [(1200,800),(800,600)]:
    for _ in range(3): app.draw(RecordingPainter(),0,0,*size)
    emtk_screenshot(app,out/f"d_inputs_{size[0]}x{size[1]}.png",size)
app.run(); t=time.time()
while s.running and time.time()-t<120:
    app.draw(RecordingPainter(),0,0,1200,800); time.sleep(0.05)
print(s.status, len(s.rows), [ (r['trial'],round(r['score'],2)) for r in s.rows])
for size in [(1200,800),(800,600)]:
    for tab in ("Results","Score","Structure"):
        app.tab=tab
        for _ in range(4): app.draw(RecordingPainter(),0,0,*size)
        emtk_screenshot(app,out/f"d_{tab}_{size[0]}x{size[1]}.png",size)
