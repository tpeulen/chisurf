"""The figures of docs/guides/75_fcs_toolbox.md, from the native FCS hub, in the states their captions describe.

A two-detector setup "SPC-132" (green = routing 0, 8; red = 1, 9) with its two autocorrelations and the green x red
cross-correlation; BH_SPC132.spc with both optional steps on; a burst filter of >= 30 photons and dT <= 0.5 ms; the
green x red cross-correlation in ten chunks; the merger with chunk 3 unticked. Hermetic settings. usage: capture_docs.py
"""

import json
import os
import pathlib
import tempfile

work = pathlib.Path(tempfile.mkdtemp())
settings = work / "s"
settings.mkdir(parents=True)
os.environ.update(CHISURF_SETTINGS_DIR=str(settings), MMFDB_SETTINGS_DIR=str(work / "m"),
                  MMFDB_DATABASE_PATH=str(work / "m.sqlite"), HOME=str(work))
REPO = pathlib.Path(__file__).resolve().parents[5]
FIG = REPO / "docs/guides/figures"
SPC = REPO / "test/data/tttr/BH/132/BH_SPC132.spc"
SETUP = {"windows": {"prompt": [0, 4095]},
         "detectors": {"green": {"chs": [0, 8], "micro_time_ranges": [[0, 4095]]},
                       "red": {"chs": [1, 9], "micro_time_ranges": [[0, 4095]]}}}
(settings / "detector_setups.json").write_text(json.dumps({"setups": {"SPC-132": SETUP}}), encoding="utf-8")

from emtk import testing  # noqa: E402
from emtk.testing import PixelPainter  # noqa: E402

from chisurf.plugins.fcs.fcs_toolbox.gui.app import make_app  # noqa: E402

SIZE = (1200, 800)
app = make_app()


def shot(name):
    painter = None
    for _ in range(4):
        painter = PixelPainter(*SIZE)
        app.draw(painter, 0, 0, *SIZE)
    (FIG / name).write_bytes(testing.png_encode(painter.width, painter.height, painter.px))
    print("wrote", name)


from chisurf.plugins.fcs.fcs_channel_preset.gui.app import create_app as make_preset  # noqa: E402

# the channel step reads this setup file (the session's own setups live in the database)
app.children["channel_def"] = make_preset(detector_file=str(settings / "detector_setups.json"),
                                          preset_file=str(settings / "fcs_channel_setups.json"))
app.select("channel_def", by_user=False)
preset = app.child
preset.select_setup("SPC-132")
for a, b in (("green", "green"), ("red", "red"), ("green", "red")):
    if (a, b) not in {(p["channel_a"], p["channel_b"]) for p in preset.model.pairs}:
        preset.model.add_pair(a, b, "")
preset.save()
shot("fcs_toolbox_channels.png")

app.select("files", by_user=False)
files = app.child
files.add_paths([str(SPC)])
files.use_filter, files.use_merger = True, True
files.changed()
shot("fcs_toolbox_files.png")

app.select("filter", by_user=False)
app.filter_model.min_ph, app.filter_model.max_dmt, app.filter_model.use_max = 30, 0.5, True
app.filter_model.on_param_changed()
shot("fcs_toolbox_filter.png")
print("filter:", app.filter_model.info_text())

app.select("correlator", by_user=False)
corr = app.child
ccf = next(i for i, name in enumerate(["", *__import__(
    "chisurf.plugins.fcs.fcs_correlator.correlator_model", fromlist=["preset_names"]).preset_names(corr.model)])
    if "red" in name and "green" in name)
corr.model.apply_preset(ccf)
corr.preset = ["", *__import__("chisurf.plugins.fcs.fcs_correlator.correlator_model",
                               fromlist=["preset_names"]).preset_names(corr.model)][ccf]
corr.model.n_splits = 10
corr.correlate(wait=True)
shot("fcs_toolbox_correlator.png")
print("correlator:", corr.model.channel_a, "x", corr.model.channel_b, corr.status)

app.select("merger", by_user=False)
merger = app.child
use = list(merger.use)
if len(use) > 3:
    use[3] = False
    merger.use = use
merger.selected = 3
shot("fcs_toolbox_merger.png")
app.close()
