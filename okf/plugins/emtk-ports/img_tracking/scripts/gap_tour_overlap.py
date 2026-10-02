"""emtk gap: a tour card over a window's control cannot be pressed (the control under it takes the press). Run from the repo root."""
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
from chisurf.plugins.microscopy.img_tracking.gui.app import make_app
app = make_app(); d = Driver(app, (1000, 700)); d.draw(3)
d.click("guide")                       # the first step is centred: its Close Tour button lies over the "Tracks drawn" field
d.click_text("Close Tour")
print("tour still active:", app.tour.active, "| a field took the keyboard:", app.io.want_capture_keyboard)   # True, True
