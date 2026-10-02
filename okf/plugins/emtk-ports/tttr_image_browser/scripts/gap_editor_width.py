"""Shared gap: the shared setup editor (chisurf/emtk/channel_definition.py) gives every field the whole window width."""
import os, tempfile
os.environ.update(CHISURF_SETTINGS_DIR=tempfile.mkdtemp(), MMFDB_SETTINGS_DIR=tempfile.mkdtemp(), MMFDB_DATABASE_PATH=tempfile.mkdtemp() + "/m.sqlite")
from emtk import im
from emtk.app import ImApp
from emtk.testing import RecordingPainter
from chisurf.emtk.channel_definition import ChannelDefinitionWidget
w = ChannelDefinitionWidget(); seen = []
real = im.combo
def combo(label, *a, **k):
    r = real(label, *a, **k); seen.append((label, round(im.get_item_rect()[2]))); return r
im.combo = combo
app = ImApp(lambda: (im.begin("W", (0, 0, 1200, 800)), w.draw(), im.end()))
for _ in range(3): seen.clear(); app.draw(RecordingPainter(), 0, 0, 1200, 800)
print(seen, "-> the setup combo is as wide as the window (1200 px); a setup name is a few characters")
