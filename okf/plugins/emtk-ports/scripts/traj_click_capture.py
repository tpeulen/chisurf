"""Click-driven captures of a trajectory tool's emtk app: a populated session operated only with pointer, keys and drops.

usage: traj_click_capture.py <tool> <out_dir>      (run from the repo root; PYTHONPATH as in UPGRADE_BRIEF plus
modules/imp-tricks/src for traj_energy)

The input is a small real trajectory made from the hgbp1 test DCD (8 frames, 5235 atoms; the peptide trajectory of the
potential-energy tests for traj_energy). Every step is a real input (``Ui`` of ``traj_save_topology/test/real_input.py``);
after each one a PNG ``click_<n>_<what>.png`` is written, to be read.
"""
import os
import sys

sys.path.insert(0, os.getcwd())          # the repository's own ``test`` package, not the standard library's
import importlib
import pathlib
import shutil
import sys
import tempfile

from test.gui.emtk_port_parity import emtk_screenshot  # first: later imports put another ``test`` package on the path
from emtk import keys

from chisurf.plugins.traj.traj_save_topology.test.real_input import DATA, Ui

tool, out = sys.argv[1], pathlib.Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
work = pathlib.Path(tempfile.mkdtemp())
APPS = {"traj_save_topology": "traj_save_topology", "traj_align": "traj_align", "traj_rotate_translate": "traj_rotate_translate",
        "traj_remove_clashes": "traj_remove_clashes", "traj_join": "traj_join", "traj_convert": "traj_convert",
        "traj_fret": "fret_trajectory", "traj_energy": "potential_energy"}
make_app = importlib.import_module(f"chisurf.plugins.traj.{APPS[tool]}.app").make_app
SIZE = (800, 700) if tool in ("traj_convert", "traj_fret", "traj_energy") else (800, 600)

if tool == "traj_energy":
    from chisurf.plugins.traj.potential_energy.test.test_view_model import _peptide_trajectory
    _peptide_trajectory(str(work / "small.dcd"))
    shutil.copy(work / "small.pdb", work / "topol.pdb")
else:
    from chisurf.core.structure import trajectory_data as md
    full = md.load(str(DATA / "hgbp1_transition.dcd"), top=str(DATA / "topol.pdb"))
    full[:8].save_dcd(str(work / "small.dcd"))
    full[8:16].save_dcd(str(work / "other.dcd"))
    shutil.copy(DATA / "topol.pdb", work / "topol.pdb")
(work / "sub").mkdir()
(work / "out").mkdir()

ui = Ui(make_app(), SIZE)
n = [0]


def shot(what):
    ui.draw(2)
    emtk_screenshot(ui.app, out / f"click_{n[0]}_{what}.png", SIZE)   # drawn with the pixel painter, whose line height
    n[0] += 1                                                         # differs from the recorder's: re-lay out
    ui.draw(2)


def save_via_dialog(name):
    ui.click(ui.app.action.key)
    shot("save_dialog_open")
    ui.save_dialog_type_name(str(work / "out" / name))
    shot("save_dialog_name_typed")
    ui.press_text("Save")
    ui.settle()
    shot("saved")


import os
os.chdir(work)
shot("empty")
ui.click("trajectory_browse" if tool != "traj_join" else "trajectory_1_browse")
shot("trajectory_dialog_open")
ui.press_text("small.dcd" if tool != "traj_energy" else "small.dcd")
shot("trajectory_entry_selected")
ui.press_text("Open")
ui.click("topology_browse")
ui.press_text("topol.pdb")
ui.press_text("Open")
if tool == "traj_join":
    ui.drop(work / "other.dcd")
shot("both_files_chosen")

if tool == "traj_save_topology":
    save_via_dialog("frame0.pdb")
elif tool == "traj_align":
    ui.type_into("atom_selection", "0, 1, 2, 3")
    ui.arrow("stride", +1)
    ui.arrow("stride", +1)
    shot("selection_typed_stride_stepped")
    save_via_dialog("aligned.dcd")
elif tool == "traj_rotate_translate":
    x, y, w, h = ui.app.item_rects["rotation_matrix"]
    for i, text in ((1, "-1"), (3, "1"), (0, "0"), (4, "0")):
        ui.click_at(x + (i % 3) * w / 3 + 60, y + (i // 3) * h / 3 + 10)
        ui.type_text(text)
        ui.key(keys.KEY_RETURN, "\r")
    x, y, w, h = ui.app.item_rects["translation"]
    ui.click_at(x + 60, y + 10)
    ui.type_text("10")
    ui.key(keys.KEY_RETURN, "\r")
    shot("matrix_and_translation_typed")
    ui.click_at(*[v for v in (x + 2 * w / 3 + 60, y + 10)])
    ui.type_text("abc")
    shot("a_cell_being_typed")
    ui.click("log", fy=0.9)
    ui.arrow("stride", +1)
    save_via_dialog("moved.dcd")
elif tool == "traj_remove_clashes":
    ui.type_into("min_distance", "3.72")
    ui.arrow("stride", +1)
    shot("distance_typed_stride_stepped")
    save_via_dialog("clash_free.dcd")
elif tool == "traj_join":
    ui.click("reverse_traj_2")
    ui.click("join_mode.1")
    shot("atoms_mode_reverse_ticked")
    ui.click("join_mode.0")
    ui.type_into("chunk_size", "3")
    save_via_dialog("joined.dcd")
elif tool == "traj_convert":
    ui.click("target_browse")
    shot("folder_dialog_open")
    ui.press_text("[out]")
    ui.press_text("Choose")
    ui.type_into("first_frame", "1")
    ui.type_into("last_frame", "6")
    ui.type_into("stride", "2")
    ui.type_into("filename", "frames")
    ui.click("ending")
    shot("format_list_open")
    ui.press_text(".pdb")
    ui.click("split")
    shot("range_typed_format_split")
    ui.click("convert")
    ui.settle()
    shot("converted")
elif tool == "traj_fret":
    for role, slot, which in (("donor", 1, 2), ("acceptor", 0, 2)):
        ui.draw(2)
        caption = sorted([t for t in ui.last.texts if t[5] == "Atom"], key=lambda t: t[0])[0 if role == "donor" else 1]
        ui.click_at(caption[0] + 8, caption[1] + 19 + 23 * slot + 8)
        shot(f"{role}_atom_list_open")
        index = ui.app.atom_index()
        chain, residue = index.where(getattr(ui.app.model, role)[slot])
        ui.press_text(index.name(index.atoms(chain, residue)[2]))
    ui.type_into("t_step", "2.5")
    ui.type_into("stride", "2")
    shot("pickers_and_parameters_set")
    save_via_dialog("fret.csv")
elif tool == "traj_energy":
    ui.click("potential_type")
    shot("type_list_open")
    ui.press_text("Radius of Gyration")
    ui.type_into("potential_weight", "0.5")
    ui.click("add")
    ui.click("potential_type")
    ui.press_text("Clash potential")
    ui.type_into("clash_tolerance", "1.5")
    ui.click("add")
    shot("two_potentials_added")
    x, y, w, h = ui.app.item_rects["added_potentials"]
    ui.click_at(x + 30, y + 30)
    shot("row_selected")
    ui.click_at(x + 30, y + 30, clicks=2)
    shot("row_removed_by_double_click")
    ui.click("potential_type")
    ui.press_text("Radius of Gyration")
    ui.click("add")
    save_via_dialog("energies.txt")
ui.click("guide")
shot("guide_open")
ui.press_text("Close Tour") if not ui.app.tour.active is False else None
ui.click("help")
shot("help_open")
ui.app.close()
print("wrote", n[0], "captures to", out)
