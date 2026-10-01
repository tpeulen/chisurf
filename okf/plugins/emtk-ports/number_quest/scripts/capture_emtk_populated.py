"""The emtk NumberQuestApp in the same state, both sizes."""
import sys, pathlib
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.misc.games.number_quest.app import make_app
out = pathlib.Path(sys.argv[1]); prefix = sys.argv[2]
for size in [(1200, 800), (800, 600), (560, 420)]:
    a = make_app(); a.game.reset(target=37)
    for value in (50, 25):
        a.estimate = value; a.submit()
    a.estimate = 37
    for _ in range(2): a.draw(RecordingPainter(), 0, 0, *size)
    emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
