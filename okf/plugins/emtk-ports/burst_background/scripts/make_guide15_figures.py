"""Guide 15 figures: burst_background on test/data/tttr/BH/132/BH_SPC132.spc (green 0/8, red 1/9)."""
import pathlib, sys, time
from test.gui.emtk_port_parity import draw_app
from emtk import testing
from emtk.testing import RecordingPainter
from chisurf.plugins.burst.burst_background.gui.app import create_app

out = pathlib.Path(sys.argv[1])
a = create_app(); size = (1280, 820)
a.controller.add_files(["test/data/tttr/BH/132/BH_SPC132.spc"]); a.controller.run()
while a.controller.running:
    time.sleep(0.05); a.draw(RecordingPainter(), 0, 0, *size)
painter = draw_app(a, size)
(out / "15_burst_background.png").write_bytes(testing.png_encode(painter.width, painter.height, painter.px))
from PIL import Image
import io
img = Image.open(io.BytesIO(testing.png_encode(painter.width, painter.height, painter.px)))
img.crop((0, 196, 512, 362)).save(out / "15_burst_background_fit.png")
print(a.model.backgrounds)
a.close()
