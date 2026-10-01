"""The Qt NumberQuestWidget in the stream's populated state (target 37, guesses 50 and 25, dial at 37)."""
import sys, pathlib
from qtpy.QtWidgets import QApplication
from chisurf.plugins.misc.games.number_quest.test.capture_qt import populate
from chisurf.plugins.misc.games.number_quest.gui.tool import NumberQuestWidget
out = pathlib.Path(sys.argv[1])
app = QApplication.instance() or QApplication([])
w = NumberQuestWidget(); w.show(); app.processEvents()
populate(w.game); w.host.ctx.canvas.force_draw(); app.processEvents()
w.grab().save(str(out / "before_populated.png"))
w.host.close(); w.close()
