"""Shared gap: the shared setup editor's TTTR format list lacks 9 of the 15 types the Qt DetectorWizardPage offers (CZ-RAW, SM, PHOTONS, ...)."""
import os, tempfile
os.environ.update(CHISURF_SETTINGS_DIR=tempfile.mkdtemp(), MMFDB_SETTINGS_DIR=tempfile.mkdtemp(), MMFDB_DATABASE_PATH=tempfile.mkdtemp() + "/m.sqlite", QT_QPA_PLATFORM="offscreen")
from emtk import im
from emtk.app import ImApp
from emtk.testing import RecordingPainter
from chisurf.emtk.channel_definition import ChannelDefinitionWidget
w = ChannelDefinitionWidget(); seen = []; real = im.combo
im.combo = lambda label, index, options, *a, **k: (seen.append(list(options)) or real(label, index, options, *a, **k))
app = ImApp(lambda: (im.begin("W", (0, 0, 1200, 800)), w._reading_controls(), im.end()))
for _ in range(3): seen.clear(); app.draw(RecordingPainter(), 0, 0, 1200, 800)
from qtpy import QtWidgets; qapp = QtWidgets.QApplication([]); from chisurf.gui.widgets.wizard.tttr_channeldefinition import DetectorWizardPage
qt = [c for c in DetectorWizardPage(show_help=False, show_tttr_reading=True).findChildren(QtWidgets.QComboBox) if "PTU" in [c.itemText(i) for i in range(c.count())]][0]
print("emtk:", seen[-1] if seen else seen, "\nQt  :", [qt.itemText(i) for i in range(qt.count())])
