"""Capture the native emtk MMFDB Admin against a seeded TEMPORARY MMFDB (the after half).

Usage, from the repository root::

    QT_QPA_PLATFORM=offscreen PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:.:$HOME/dev/emtk" \
        python okf/plugins/emtk-ports/mmfdb_admin/capture_emtk_populated.py okf/plugins/emtk-ports/mmfdb_admin

The same seeded state as ``capture_qt_populated.py`` (``seeded_admin.seed``), the same
visits: every panel of the rail in turn (entity panels with their first row selected,
Sample Metadata on ``sample_gui``, the Provenance Graph loaded on ``prod_gui``), the three menus opened, then the
dialogs. Each state is drawn headlessly through ``app.draw`` at 1200x800 and saved as
``after_<panel>.png`` (a few also at 800x600 as ``after_small_<panel>.png``);
``CAPTURE_NO_PNG=1`` skips the PNG encoding (an inventory-only run, minutes not an hour).

Comparison format (the one the before half used): the normalised text of every control
the app drew and every string it painted, plus the option labels of every choice drawn
with at most 40 options (the Qt half recorded a combo's options; a longer list is
recorded as ``combo with N options``). Written as ``after.json`` (with the per-control
tooltip audit and the Qt-free check) and per state as ``after_panels.json``; then
``compare.json`` via ``test.gui.emtk_port_parity.compare``.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))  # the repository root: ``test`` is the repo's, not the stdlib's
for _name in [m for m in sys.modules if m == "test" or m.startswith("test.")]:
    del sys.modules[_name]
from test.gui.emtk_port_parity import ControlRecorder, compare, normalize, qt_free  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp(prefix="mmfdb_admin_emtk_"))

from chisurf.plugins.core.mmfdb_admin.test import seeded_admin as sa  # noqa: E402

sa.use_folder(tmp)
client = sa.admin_client()
sa.seed(tmp, client)

from emtk import testing  # noqa: E402
from emtk.view_form import _options  # noqa: E402

from chisurf.emtk.i18n import install  # noqa: E402
from chisurf.plugins.core.mmfdb_admin.gui.app import MMFDBAdminApp  # noqa: E402
from chisurf.plugins.core.mmfdb_admin.gui.native import dialogs as dlg  # noqa: E402
from chisurf.plugins.core.mmfdb_admin.gui.native.runner import InlineRunner  # noqa: E402
from chisurf.plugins.core.mmfdb_admin.gui.native.spectra import DuplicatesDialog  # noqa: E402
from chisurf.plugins.core.mmfdb_admin.gui.optical_components.duplicates import (  # noqa: E402
    find_duplicate_groups,
)

install()
ENTRY = "chisurf.plugins.core.mmfdb_admin.gui.app:make_app"
SIZE, SMALL = (1200, 800), (800, 600)
SMALL_PANELS = {"overview", "sample", "spectra", "provenance", "metadata", "user", "elabftw", "studies"}

app = MMFDBAdminApp(client=client, runner=InlineRunner())
app.model.user = "admin"
model = app.model

#: Qt panel name of each native panel key (the before images are named after them).
QT_NAMES = {key: model.panel_name(key) for key in model.panel_keys()}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def draw(size=SIZE, frames: int = 3):
    painter = None
    for _ in range(frames):
        painter = testing.PixelPainter(*size)
        app.draw(painter, 0.0, 0.0, float(size[0]), float(size[1]))
    return painter


def shot(name: str, size=SIZE) -> None:
    if os.environ.get("CAPTURE_NO_PNG"):  # inventory only (the PNGs take ~1 min each)
        draw(size)
        return
    painter = draw(size)
    (out / name).write_bytes(testing.png_encode(painter.width, painter.height, painter.px))


def choice_labels(sections, owner) -> set[str]:
    """Option labels of the choices in *sections* (<= 40 options; the Qt half's rule), and placeholders.

    The Qt half read a line edit's ``placeholderText`` whether or not the field was
    empty; a placeholder is only painted on an empty field, so it is taken from the
    spec here (the same attribute, recorded the same way).
    """
    found: set[str] = set()
    for section in sections or ():
        if not isinstance(section, dict):
            continue
        if section.get("placeholder"):
            found.add(normalize(str(section["placeholder"])))
        if isinstance(section.get("sections"), list):
            found |= choice_labels(section["sections"], owner)
        if section.get("type") == "choice":
            try:
                _values, labels = _options(section, owner)
            except Exception:  # noqa: BLE001 - an option source that needs data
                labels = []
            if len(labels) <= 40:
                found |= {normalize(label) for label in labels}
            else:
                found.add(normalize(f"combo with {len(labels)} options"))
    return found


def drawn_sections():
    """``(sections, model)`` of everything the current frame drew from a spec."""
    key = model.selected
    panel = model.current
    pairs = [(app.shell["toolbar"]["sections"], model)]
    if panel.spec == "entity":
        pairs.append((panel.form_sections(), panel.form))
    elif key in app.panel_specs:
        pairs.append((app.panel_specs[key]["sections"], panel))
    if key == "spectra":
        pairs.append((panel.form_spec()["sections"], panel.values))
    for d in model.dialogs:
        pairs.append((app.shell[d.spec]["sections"], d))
    return pairs


def record() -> tuple[set[str], list[dict]]:
    recorder = ControlRecorder()
    with recorder.installed():
        for _ in range(3):
            recorder.rows.clear()
            painter = testing.RecordingPainter()
            app.draw(painter, 0.0, 0.0, float(SIZE[0]), float(SIZE[1]))
    controls = set(recorder.texts) | {normalize(s) for s in painter.strings}
    for sections, owner in drawn_sections():
        controls |= choice_labels(sections, owner)
    controls.discard("")
    rows = []
    for r in recorder.rows:
        name = r["label"] or r["id"].lstrip("#")
        if name:
            rows.append(dict(r, label=name))
    return controls, rows


panels: dict[str, list[str]] = {}
interactive: dict[str, dict] = {}


def visit(name: str) -> None:
    controls, rows = record()
    panels[name] = sorted(controls)
    for r in rows:
        interactive.setdefault(f"{r['kind']}: {r['label']}", r)
    print(name, len(controls))


draw()
assert model.connected, model.status
for key in model.panel_keys():
    model.select(key)
    draw()
    panel = model.current
    if panel.spec == "entity" and panel.rows:
        panel.select_row(panel.rows[0])
    elif key == "metadata":
        panel.load_sample("sample_gui")
        draw()
        if panel.rows:
            panel.select_row(panel.rows[0])
    elif key == "spectra" and panel.rows:
        panel.select_row(panel.rows[0])
    elif key == "provenance":
        panel.set_seed("processed_data", "prod_gui")
    elif key == "studies" and panel.studies:
        panel.select_study(panel.studies[0])
    elif key == "protocols" and panel.protocols:
        panel.select_protocol(panel.protocols[-1])
    elif key == "lifecycle":
        panel.entity_type, panel.entity_id = "sample", "sample_gui"
        panel.load()
    elif key == "reagents" and panel.lots:
        panel.select_lot(panel.lots[0])
    draw()
    file = f"after_{slug(QT_NAMES[key])}.png"
    shot(file)
    if key in SMALL_PANELS:
        shot(f"after_small_{slug(QT_NAMES[key])}.png", SMALL)
    visit(QT_NAMES[key])

# The menus (the Qt half recorded the menu bar's actions): open each, record, close.
from chisurf.plugins.emtk_test_input import Driver  # noqa: E402

driver = Driver(app, size=SIZE)
model.select("overview")
for menu in ("File", "Settings", "Help"):
    driver.click_text(menu, last=False)
    visit(f"menu:{menu}")
    driver.escape()

# The dialogs a user reaches from the window, each drawn over the panel that opens it.
model.select("user")
draw()
users = model.current
users.jump_to("john_doe")
draw()


def dialog(dialog_obj, name: str) -> None:
    model.show(dialog_obj)
    draw()
    shot(f"after_dialog_{name}.png")
    visit(f"dialog:{name}")
    dialog_obj.close()
    draw()


login = dlg.ConnectionDialog("admin", "127.0.0.1", 8765, 8766, lambda _v: None)
dialog(login, "connection")
password = dlg.PasswordDialog("john_doe", False, lambda *_a: None, model.show)
password.password_new = "Abc12"
dialog(password, "password")
dialog(dlg.JumpBranchDialog("john_doe", lambda _v: None), "jump_branch")

model.select("branch")
draw()
dialog(dlg.TextDialog("Set branch head", "Operation ID (leave empty to reset to None):",
                      lambda _t: None, value="ver_gui", label="Operation ID"), "branch_head")

model.select("raw_data")
draw()
dialog(dlg.ChoiceDialog("Set validation status", "Validation status for raw_gui:",
                        ["unvalidated", "valid", "invalid", "suspect"], "valid", lambda _v: None),
       "validation_status")
dialog(dlg.ConfirmDialog("Delete artifact", "Delete raw-data artifact 'raw_gui'?\n\nThis soft-deletes "
                         "the artifact and direct provenance links.", lambda: None), "confirm")

model.select("analysis")
draw()
detail = client.get_analysis_run_full("analysis_gui")
dialog(dlg.AnalysisDetailsDialog("analysis_gui", detail), "analysis_details")
dialog(dlg.MessageDialog("About mmfdb-admin", model.about_text()), "about")

model.select("spectra")
draw()
probes = client._call("fluorophores.find_duplicates", {}).get("probes", [])
groups = find_duplicate_groups(probes) or []
dup = DuplicatesDialog(groups, model.current)
model.show(dup)
draw()
tree = dup.tree_rows()
dup.select_row(next(r for r in tree if r["_row"].startswith("p:")))
draw()
shot("after_dialog_duplicates.png")
visit("dialog:duplicates")
dup.close()

after = set()
for controls in panels.values():
    after |= set(controls)
rows = list(interactive.values())
(out / "after_panels.json").write_text(json.dumps(panels, indent=2, ensure_ascii=False))
inventory = {
    "entrypoint": ENTRY,
    "size": list(SIZE),
    "format": "drawn controls, painted strings and choice options (<= 40) of every panel and "
    "dialog; see capture_emtk_populated.py",
    "controls": sorted(after),
    "interactive": rows,
    "controls_without_tooltip": sorted({k for k, r in interactive.items() if not r["tooltip"]}),
    "qt_free": qt_free("mmfdb_admin", ENTRY),
}
(out / "after.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False))
result = compare("mmfdb_admin", out)
print("controls", len(after), "lost", len(result["lost"]), "untooltipped", len(result["untooltipped"]),
      "qt_free", result["qt_free"].get("ok"))
app.close()
