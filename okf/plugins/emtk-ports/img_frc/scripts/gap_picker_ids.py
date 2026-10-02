"""emtk gap: the dataset picker's Refresh / Previous / Next / Open selected / Cancel buttons are all spelled '...##dataset', so they share one id
(emtk keeps only the text after '##') and the disabled Previous / Next swallow the release: 'Open selected' and 'Cancel' never fire. Run from the repo root."""
import time
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
from chisurf.plugins.microscopy.img_frc.gui.app import make_app


class Client:
    def call(self, method, params=None):
        if method == "mmfdb.datasets.browse":
            return {"datasets": [{"artifact_id": "a1", "artifact_kind": "raw_data", "data_format": "tif", "original_filename": "x.tif"}], "total": 1}
        return {"local_path": "/tmp/x.tif"}


app = make_app(); d = Driver(app, (1000, 700)); app.picker.client = Client()
d.click("open_database"); d.draw(2); time.sleep(0.3); d.draw(2)
d.click_text("x.tif [raw_data] (tif)"); d.click_text("Open selected")
print("picker still open after pressing Open selected:", app.picker.is_open)            # True (expected False)
d.click_text("Cancel"); print("picker still open after pressing Cancel:", app.picker.is_open)   # True (expected False)
