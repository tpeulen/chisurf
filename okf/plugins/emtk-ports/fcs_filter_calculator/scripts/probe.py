import sys
from chisurf.plugins.fcs.fcs_filter_calculator.test.driving import *
from chisurf.plugins.fcs.fcs_filter_calculator.gui.app import create_app
import time
a=create_app(); d=FilterDriver(a,BIG); d.settle()
print(sorted(a.item_rects))
t=time.time(); d.click("autofit"); d.settle(); print("autofit", time.time()-t, a.model.message, len(a.model.components))
d.click("unmix"); d.settle(); print(a.model.message)
