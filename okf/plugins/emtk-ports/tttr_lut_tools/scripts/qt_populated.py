import os, sys, shutil, json, pathlib
T = pathlib.Path(sys.argv[1]); E = pathlib.Path(sys.argv[2])
os.environ["CHISURF_SETTINGS_DIR"] = str(T/"settings"); os.environ["MMFDB_SETTINGS_DIR"]=str(T/"mmfdb"); os.environ["MMFDB_DATABASE_PATH"]=str(T/"mmfdb"/"db.sqlite")
from qtpy import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
src = pathlib.Path("test/data/tttr/BH/132/BH_SPC132.spc")
cp = T/"BH_SPC132.spc"; shutil.copy(src, cp)
for s in src.parent.glob("BH_SPC132*"):
    if s != src: shutil.copy(s, T/s.name)
from chisurf.plugins.tttr.tttr_lut_tools.gui.tool import TTRLutToolsWidget
import numpy as np
w = TTRLutToolsWidget(); w.resize(1200,800); w.show()
def grab(name):
    for _ in range(30): app.processEvents()
    w.grab().save(str(E/name))
m = w.tac_panel.model
m.files=[str(cp)]; m.update()
grab("before_populated_loaded.png")
out = {"channels": m.available_channels, "channel": m.channel, "region_auto": [m.linear_start, m.linear_stop], "info": m.info_text()}
m.linear_start, m.linear_stop = 1200, 1900; m.compute(); m.notify("plot")
out["region_hand"]=[1200,1900]; out["info_hand"]=m.info_text()
grab("before_populated_region_picked.png")
m.autodetect(); out["ch0_autodetect_fails_keeps"]=[m.linear_start,m.linear_stop]
m.channel="8"; m.update(); m.linear_start,m.linear_stop=1200,1900; m.compute(); m.autodetect(); out["ch8_autodetect"]=[m.linear_start,m.linear_stop]; out["ch8_info"]=m.info_text()
grab("before_populated_autodetect.png")
lut = T/"lut.npy"; m.channel="0"; m.update(); m.linear_start,m.linear_stop=1200,1900; m.compute(); m.save_lut(str(lut)); out["lut_saved"]=lut.name; out["lut_len"]=int(np.load(lut).size) if lut.suffix==".npy" else None
corr = T/"corr.npy"; m.export_corrected(str(corr)); out["corrected_n"]=int(np.load(corr).size)
w._bridge_compute_to_assign()
out["assigned_channels"]=sorted(w.settings_panel.channel_luts)
w.dock_area.setCurrentIndex(1); grab("before_populated_tab_settings.png")
print(json.dumps(out)); (E/"before_populated.json").write_text(json.dumps(out,indent=2))
