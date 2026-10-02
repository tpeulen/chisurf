import sys, tempfile, time, pathlib
sys.path.insert(0,'okf/plugins/emtk-ports/structure_tools/scripts')
import fixtures
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.modelling.structure_tools.cards.fps_json import make_app
out=pathlib.Path(sys.argv[1]); out.mkdir(exist_ok=True,parents=True)
fps,_=fixtures.make(tempfile.mkdtemp())
app=make_app()
app.load_path(str(fps)); app.editor.wait(120)
for size in [(1200,800),(800,600)] if len(sys.argv)<4 else [tuple(map(int,sys.argv[3].split("x")))]:
    for tab in sys.argv[2].split(","):
        app.tab=tab
        for _ in range(4): app.draw(RecordingPainter(),0,0,*size)
        if tab=="Positions": app.editor.selected_pos="p66_Q6C"
        if tab=="Distances": app.editor.selected_dist=app.editor.rows_dist[0]["row"]
        for _ in range(3): app.draw(RecordingPainter(),0,0,*size)
        emtk_screenshot(app, out/f"s_{tab.replace(' ','')}_{size[0]}x{size[1]}.png", size)
print('done')
