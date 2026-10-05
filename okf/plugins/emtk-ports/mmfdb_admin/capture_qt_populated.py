"""Capture the legacy Qt MMFDB Admin against a seeded TEMPORARY MMFDB (the before half).

Usage, from the repository root::

    QT_QPA_PLATFORM=offscreen PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:.:$HOME/dev/emtk" \
        python okf/plugins/emtk-ports/mmfdb_admin/capture_qt_populated.py okf/plugins/emtk-ports/mmfdb_admin

Settings, database and object store live in a temp folder (``seeded_admin.use_folder``).
Every navigation panel is opened in turn (entity panels with their first row selected),
grabbed at 1200x800 as ``before_<panel>.png``, and its *visible* controls are recorded.
The dialogs a user reaches from the window are built and grabbed too.

Comparison format (fixed before capturing): a control is the normalised text of a
visible label, button, check box, radio button, menu/toolbar action, combo option,
line-edit placeholder, group-box title, tab title, or table *column header*. Table
cell data is not a control (it is checked by the native app's tests instead). The
union over all panels and dialogs is written to ``before.json`` in the format
``test.gui.emtk_port_parity compare`` reads; ``before_panels.json`` keeps it per panel.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path.cwd()))  # the repository root: ``test`` is the repo's, not the stdlib's
for _name in [m for m in sys.modules if m == "test" or m.startswith("test.")]:
    del sys.modules[_name]
from test.gui.emtk_port_parity import normalize  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp(prefix="mmfdb_admin_qt_"))

from chisurf.plugins.core.mmfdb_admin.test import seeded_admin as sa  # noqa: E402

sa.use_folder(tmp)
client = sa.admin_client()
sa.seed(tmp, client)

from qtpy import QtCore, QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from chisurf.plugins.core.mmfdb_admin.gui.tool import MMFDBWidget  # noqa: E402

with mock.patch.object(MMFDBWidget, "_active_mmfdb_user_id", lambda self: "admin"):
    widget = MMFDBWidget(client=client)
widget._active_mmfdb_user_id = lambda: "admin"
widget.resize(1200, 800)
widget.show()


def pump(wait: float = 0.3) -> None:
    end = time.monotonic() + wait
    for _ in range(10):
        app.processEvents()
    while time.monotonic() < end:
        app.processEvents()


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def visible_controls(root: QtWidgets.QWidget) -> set[str]:
    """Normalised texts of the visible controls under *root* (see the module docstring)."""
    found: set[str] = set()

    def add(text) -> None:
        if text is not None and str(text).strip():
            found.add(normalize(str(text)))

    for w in root.findChildren(QtWidgets.QWidget):
        if not w.isVisible():
            continue
        if isinstance(w, QtWidgets.QLabel):
            add(w.text())
        elif isinstance(w, QtWidgets.QAbstractButton):
            add(w.text())
        elif isinstance(w, QtWidgets.QComboBox):
            # A short option list is a set of controls; a vocabulary picker (the
            # thousands of mmCIF metadata keys) is data, recorded by its size only.
            if w.count() <= 40:
                for i in range(w.count()):
                    add(w.itemText(i))
            else:
                add(f"combo with {w.count()} options")
        elif isinstance(w, QtWidgets.QLineEdit):
            add(w.placeholderText())
        elif isinstance(w, QtWidgets.QGroupBox):
            add(w.title())
        elif isinstance(w, QtWidgets.QTabWidget):
            for i in range(w.count()):
                add(w.tabText(i))
        elif isinstance(w, QtWidgets.QTableWidget):
            for c in range(w.columnCount()):
                item = w.horizontalHeaderItem(c)
                add(item.text() if item else "")
        elif isinstance(w, QtWidgets.QTreeWidget):
            header = w.headerItem()
            for c in range(w.columnCount()):
                add(header.text(c))
        elif isinstance(w, QtWidgets.QToolBar):
            for action in w.actions():
                if action.isVisible():
                    add(action.text())
    found.discard("")
    return found


panels: dict[str, list[str]] = {}
shell: set[str] = set()
# Window chrome: menus and toolbar (seen with any panel).
for menu_action in widget.menuBar().actions():
    shell.add(normalize(menu_action.text()))
    menu = menu_action.menu()
    if menu is not None:
        for action in menu.actions():
            if action.text():
                shell.add(normalize(action.text()))
for row in range(widget.nav_list.count()):
    item = widget.nav_list.item(row)
    if item is not None and item.text().strip():
        shell.add(normalize(item.text()))
shell.discard("")
panels["_shell"] = sorted(shell)

for row, panel in enumerate(widget.panels):
    if panel.get("separator"):
        continue
    name = panel["name"]
    widget.nav_list.setCurrentRow(row)
    pump(0.6)
    inst = widget._unwrap(panel.get("instance"))
    table = getattr(inst, "_table", None) or getattr(inst, "table", None)
    if isinstance(table, QtWidgets.QTableWidget) and table.rowCount():
        table.selectRow(0)
        pump(0.4)
    if name == "Sample Metadata" and inst is not None:
        inst.refresh_samples()
        inst.load_sample("sample_gui")
        pump(0.3)
    if name == "All items":
        widget._populate_all_items()
        pump(0.2)
    if name == "Measurements":
        widget._refresh_measurements()
        pump(0.2)
    widget.grab().save(str(out / f"before_{slug(name)}.png"))
    panels[name] = sorted(visible_controls(widget) - shell)
    print("panel", name, len(panels[name]))

# Provenance graph with a loaded seed (the visible panel has no seed controls of its own).
widget._set_provenance_seed("processed_data", "prod_gui")
widget.load_provenance_full_graph()
pump(0.5)
widget.grab().save(str(out / "before_provenance_graph_loaded.png"))


def grab_dialog(dialog: QtWidgets.QWidget, name: str, size=(520, 320)) -> None:
    dialog.resize(*size)
    dialog.show()
    pump(0.3)
    dialog.grab().save(str(out / f"before_dialog_{name}.png"))
    panels[f"dialog:{name}"] = sorted(visible_controls(dialog))
    dialog.close()
    print("dialog", name, len(panels[f"dialog:{name}"]))


from chisurf.plugins.core.mmfdb_admin.gui.connection_dialog import (  # noqa: E402
    ConnectionAuthDialog,
)
from chisurf.plugins.core.mmfdb_admin.gui.tool import PasswordChangeDialog  # noqa: E402

grab_dialog(ConnectionAuthDialog(user="admin", host="127.0.0.1"), "connection", (460, 320))
grab_dialog(PasswordChangeDialog(user_id="john_doe", is_admin=False), "password", (380, 240))

# Analysis details (the Analyses panel's Details button).
row = widget._row_by_entity["analysis"]
widget.nav_list.setCurrentRow(row)
pump(0.5)
dock = widget._entity_docks["analysis"]
dock.refresh()
for r in range(dock.table.rowCount()):
    if dock.table.item(r, 1) and dock.table.item(r, 1).text() == "analysis_gui":
        dock.table.selectRow(r)
pump(0.3)
widget._show_selected_analysis_details()
pump(0.3)
details = getattr(widget, "_analysis_drilldown_dialog", None)
if details is not None:
    details.grab().save(str(out / "before_dialog_analysis_details.png"))
    panels["dialog:analysis_details"] = sorted(visible_controls(details))
    details.close()

# Find duplicates (the Spectra panel's duplicates dialog), groups computed in-process.
from chisurf.plugins.core.mmfdb_admin.gui.optical_components.duplicates_dialog import (  # noqa: E402
    DuplicateFinderThread,
    DuplicatesDialog,
)

probes = client._call("fluorophores.find_duplicates", {}).get("probes", [])
finder = DuplicateFinderThread(probes)
groups: list = []
finder.finished_groups.connect(groups.extend)
finder.run()
dup = DuplicatesDialog(groups or [], client)
grab_dialog(dup, "duplicates", (1000, 600))

before = set()
for controls in panels.values():
    before |= set(controls)
(out / "before_panels.json").write_text(json.dumps(panels, indent=2, ensure_ascii=False))
(out / "before.json").write_text(
    json.dumps(
        {
            "entrypoint": "chisurf.plugins.core.mmfdb_admin.gui.tool:MMFDBWidget",
            "size": [1200, 800],
            "format": "visible controls of every panel and dialog; see capture_qt_populated.py",
            "controls": sorted(before),
        },
        indent=2,
        ensure_ascii=False,
    )
)
print("total controls", len(before))
widget.close()
