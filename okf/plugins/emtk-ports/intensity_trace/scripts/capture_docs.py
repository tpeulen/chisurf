"""docs/guides/figures/intensity_trace.png from the native tool, in its caption's state: BH_SPC132.spc (a temp copy),
a red (1, 9) / green (0, 8) setup, 5 ms bins, a two-state HMM, the dwell times. usage: capture_docs.py"""

import os
import pathlib
import shutil
import tempfile

work = pathlib.Path(tempfile.mkdtemp())
os.environ.update(CHISURF_SETTINGS_DIR=str(work / "s"), MMFDB_SETTINGS_DIR=str(work / "m"),
                  MMFDB_DATABASE_PATH=str(work / "m.sqlite"), HOME=str(work))
REPO = pathlib.Path(__file__).resolve().parents[5]
SPC = work / "BH_SPC132.spc"
shutil.copy(REPO / "test/data/tttr/BH/132/BH_SPC132.spc", SPC)
from emtk import testing  # noqa: E402
from emtk.testing import PixelPainter  # noqa: E402

from chisurf.plugins.tttr.intensity_trace.gui.app import make_app  # noqa: E402

app = make_app()
app.model.window_ms = 5.0
app.setup_edited({"detectors": {"red": {"chs": [1, 9], "micro_time_ranges": []},
                                "green": {"chs": [0, 8], "micro_time_ranges": []}}})
app.open_file(str(SPC))
app.wait()
app.model.n_states = 2
app.tab = "HMM"
app.compute_hmm()
app.wait()
app.show_result("Dwell Times")
p = None
for _ in range(4):
    p = PixelPainter(1400, 860)
    app.draw(p, 0, 0, 1400, 860)
(REPO / "docs/guides/figures/intensity_trace.png").write_bytes(testing.png_encode(p.width, p.height, p.px))
print(app.status)
app.close()
