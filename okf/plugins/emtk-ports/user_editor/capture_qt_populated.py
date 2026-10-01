"""Capture the legacy Qt user editor against a seeded TEMPORARY MMFDB.

Usage: ``python capture_qt_populated.py <out_dir>`` (from the repository root,
with the environment of the PRD: QT_QPA_PLATFORM=offscreen, PYTHONPATH with the
repository, emtk and mmfdb/src). Settings and database live in a temp folder.
"""
import sys
import tempfile
import time
from pathlib import Path

out = Path(sys.argv[1])
tmp = Path(tempfile.mkdtemp(prefix="ue_qt_"))

from chisurf.plugins.core.user_editor.test import seeded_db as db  # noqa: E402

db.use_folder(tmp)
client = db.admin_client()
db.seed(client)

from qtpy import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from chisurf.gui.widgets.chitable import ChiTableWidget  # noqa: E402
from chisurf.plugins.core.user_editor.gui import view_model as vm  # noqa: E402
from chisurf.plugins.core.user_editor.gui.tool import (  # noqa: E402
    PasswordChangeDialog,
    UserEditorWidget,
)

vm.active_user_id = lambda: "admin"
widget = UserEditorWidget(view_model=vm.UserEditorViewModel(client_factory=lambda: client))
widget.resize(1200, 800)
widget.show()


def pump(n=20, wait=0.0):
    end = time.monotonic() + wait
    for _ in range(n):
        app.processEvents()
    while time.monotonic() < end:
        app.processEvents()


def grab(name):
    pump(20, 0.1)
    widget.grab().save(str(out / name))
    print("wrote", name)


pump()
table = widget.auto_form.findChildren(ChiTableWidget)[0]
grab("before_populated.png")

table._view.selectRow(2)
pump(20, 0.2)
grab("before_populated_selected.png")

widget.model.display_name = "Bob Baker-Smith"
grab("before_populated_dirty.png")

widget.model.email = "not-an-email"
grab("before_populated_validation.png")
widget.model.revert()

table._search.setText("car")
pump(20, 0.5)
grab("before_populated_search.png")
table._search.setText("")
pump(20, 0.3)

# sort by role
table._view.sortByColumn(2, __import__("qtpy").QtCore.Qt.AscendingOrder)
grab("before_populated_sorted.png")

widget.model.new_user()
grab("before_populated_new.png")

dialog = PasswordChangeDialog(user_id="bob", is_admin=False)
dialog.edit_password.setText("Abcdef1!")
dialog.edit_confirm.setText("Abcdef1!")
dialog.show()
pump(20, 0.2)
dialog.grab().save(str(out / "before_populated_password.png"))
print("wrote before_populated_password.png")

# permission denied (a plain user lists nothing)
plain = db.admin_client(db.PLAIN_USER)
widget2 = UserEditorWidget(view_model=vm.UserEditorViewModel(client_factory=lambda: plain))
widget2.resize(1200, 800)
widget2.show()
pump(40, 0.3)
widget2.grab().save(str(out / "before_populated_denied.png"))
print("wrote before_populated_denied.png", widget2.model.status_text())
