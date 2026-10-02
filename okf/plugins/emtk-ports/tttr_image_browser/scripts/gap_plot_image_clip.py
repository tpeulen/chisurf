"""emtk gap: PixelPainter (the screenshot painter) ignores the clip stack when it draws a texture, so a zoomed implot.plot_image
paints over the neighbouring windows in screenshots. PilPainter clips correctly (same frame, same atlas)."""
import numpy as np
from emtk import Texture, im, implot
from emtk.app import ImApp
from emtk.pil_painter import PilPainter
from emtk.testing import PixelPainter
tex = Texture(4, 4, bytes([200, 40, 40, 255]) * 16); box = []
def gui():
    im.begin("W", (0, 0, 400, 300)); implot.begin_plot("##p", (200, 200)); implot.setup_axes_limits(0, 1, 0, 1, implot.COND_ALWAYS)  # zoomed into the image
    implot.plot_image("i", tex, (-5, -5), (6, 6)); box[:] = [*implot.get_plot_pos(), *implot.get_plot_size()]; implot.end_plot(); im.end()
for painter in (PixelPainter, PilPainter):
    app = ImApp(gui)
    for _ in range(2): p = painter(400, 300); app.draw(p, 0, 0, 400, 300)
    px = np.frombuffer(bytes(p.px), np.uint8).reshape(300, 400, 4); x, y, w, h = (int(v) for v in box)
    print(painter.__name__, "red pixels outside the plot area", box, ":", int((px[:, :, 0] > 150).sum() - (px[y:y + h, x:x + w, 0] > 150).sum()))
