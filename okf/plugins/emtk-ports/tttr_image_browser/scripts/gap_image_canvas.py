"""Shared gap: chisurf/emtk/image_canvas.ImageCanvas stacks its controls and offers 4 colormaps (the Qt image dock had 7)."""
import numpy as np
from emtk import im
from emtk.app import ImApp
from emtk.testing import RecordingPainter
from chisurf.emtk.image_canvas import ImageCanvas
c = ImageCanvas("c"); a = np.random.default_rng(1).random((64, 64))
app = ImApp(lambda: (im.begin("W", (0, 0, 800, 600)), c.draw(a), im.end()))
for _ in range(3): p = RecordingPainter(); app.draw(p, 0, 0, 800, 600)
print("plot top y =", c.rect[1], "of 600; plot height =", c.rect[3], "; colormaps offered: magma, inferno, viridis, gray (4 of the Qt dock's 7)")
