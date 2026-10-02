"""The native updater in every state worth a screenshot, at 1200x800 and 800x600, on fakes. Usage: <out_dir> [card: u1|u2].

Writes after_populated_<state>_<size>.png, after.json (union of the control inventories of every state) and prints the numbers.
SAFETY: every system action is a fake (chisurf.plugins.core.updater.test.fakes): no update, install, removal, environment change
or network; settings, HOME and the MMFDB paths are in a temporary folder.
"""
import json, os, pathlib, sys, tempfile, time

tmp = pathlib.Path(tempfile.mkdtemp(prefix="upd_after_"))
os.environ.update(CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"), HOME=str(tmp / "home"))
(tmp / "s").mkdir(); (tmp / "home").mkdir()
from test.gui.emtk_port_parity import emtk_inventory, qt_free
import pytest
from emtk.pil_painter import PilPainter
from emtk.testing import RecordingPainter, png_encode
from chisurf.plugins.core.updater.test.fakes import Fakes
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

mp = pytest.MonkeyPatch()
fakes = Fakes().install(mp)
from chisurf.plugins.core.updater.gui.app import UpdaterApp
from chisurf.plugins.core.updater.gui.model import UpdaterModel
from chisurf.plugins.core.updater import updater as up

out = pathlib.Path(sys.argv[1])
SIZES = ((1200, 800), (800, 600))
union, interactive, missing = set(), [], set()


def inventory(app, size=(1200, 800)):
    inv = emtk_inventory(app, size)
    union.update(inv["controls"]); interactive.extend(inv["interactive"]); missing.update(inv["controls_without_tooltip"])


def shot(app, name, sizes=SIZES, inv=True):
    for size in sizes:
        app.pointer_move(-1.0, -1.0)
        for _ in range(3):
            p = PilPainter(*size)
            app.draw(p, 0, 0, *size)
        (out / f"after_populated_{name}_{size[0]}x{size[1]}.png").write_bytes(png_encode(p.width, p.height, p.px))
        if inv:
            inventory(app, size)


def fresh(size):
    app = UpdaterApp(UpdaterModel(), auto_check=False)
    return app, Driver(app, size)


def settle(drv):
    end = time.monotonic() + 30
    drv.draw(1)
    while (drv.app.job.busy or drv.app.model.busy or drv.app.model.updating) and time.monotonic() < end:
        time.sleep(0.01); drv.draw(1)
    drv.draw(3)


def each_size(name, setup, inv=True):
    """A fresh app per size (a window remembers where it stood), set up by *setup(app, drv)*, shot at that size."""
    for size in SIZES:
        app, drv = fresh(size)
        drv.draw(3)
        setup(app, drv)
        shot(app, name, (size,), inv)
        app.close()


each_size("empty", lambda app, drv: None)
def checked(app, drv):
    drv.click("check_for_updates"); settle(drv)
each_size("checked", checked)
def version2(app, drv):
    checked(app, drv); drv.click("selected_version"); drv.click_text("Version 26.09.20", last=True); settle(drv)
each_size("version_2", version2)
def version_list_open(app, drv):
    checked(app, drv); drv.click("selected_version"); drv.draw(3)
each_size("version_list_open", version_list_open)
def confirm(app, drv):
    checked(app, drv); drv.click("ask_update"); drv.draw(3)
each_size("confirm_update", confirm)
def declined(app, drv):
    confirm(app, drv); drv.click_text("No", last=True); drv.draw(3)
each_size("update_declined", declined)
def toggled(app, drv):
    checked(app, drv); drv.click("check_on_startup", fx=0.05); drv.click("ignore_updates_on_startup", fx=0.05); drv.draw(3)
each_size("startup_toggled", toggled)
def accepted(app, drv):
    confirm(app, drv); drv.click_text("Yes", last=True); settle(drv)
each_size("update_started", accepted)
# the progress window while the update is prepared (the runner waits)
gate = {"go": False}
orig = up.ChiSurfUpdater._run_update_in_separate_process
def slow(self, cmd, callback=None):
    fakes.update_commands.append(("separate_process", list(cmd)))
    callback("Preparing to run update in a separate process...")
    end = time.monotonic() + 20
    while not gate["go"] and time.monotonic() < end:
        time.sleep(0.01)
    return True, None
mp.setattr(up.ChiSurfUpdater, "_run_update_in_separate_process", slow)
for size in SIZES:
    gate["go"] = False
    app, drv = fresh(size); drv.draw(3); checked(app, drv)
    drv.click("ask_update"); drv.click_text("Yes", last=True)
    end = time.monotonic() + 5
    while "Preparing to run update in a separate process..." not in drv.draw(1).strings and time.monotonic() < end:
        time.sleep(0.02)
    shot(app, "update_progress", (size,))
    gate["go"] = True; settle(drv); app.close()
mp.setattr(up.ChiSurfUpdater, "_run_update_in_separate_process", orig)
# no versions / error
fakes.releases.clear()
each_size("error_no_versions", checked)
fakes.releases.extend([{"version": "26.10.02", "file_path": "https://downloads.invalid/x/chisurf-macos-26.10.02.conda", "file_name": "x"}])
# the notice of the start-up check
for size in SIZES:
    app = UpdaterApp(UpdaterModel(), auto_check=True, auto_check_delay=0.0); drv = Driver(app, size); drv.draw(3); settle(drv)
    shot(app, "startup_notice", (size,)); app.close()
# a long changelog, scrolled with the wheel
def long_log(app, drv):
    checked(app, drv)
    app.model._show_changelog("Changes between 26.09.20 and 26.10.02:\n" + "\n".join(f"- 2026-10-{1 + i % 28:02d} commit message number {i}: refactor the update path (by Ada)" for i in range(60)) + "\nMore details: https://github.com/Fluorescence-Tools/chisurf/commits")
    drv.draw(3)
    x, y, w, h = drv.rect("changelog"); drv.wheel(x + w / 2, y + h / 2, -8); drv.draw(3)
each_size("changelog_scrolled", long_log)
def help_open(app, drv):
    drv.click("help"); drv.draw(3)
each_size("help", help_open)
def guide(app, drv):
    checked(app, drv); drv.click("guide"); drv.press = None; drv.draw(3)
each_size("guide_step_1", guide)
def guide4(app, drv):
    checked(app, drv); app.tour.start(3); drv.draw(3)
each_size("guide_step_changelog", guide4)
def tooltip(app, drv):
    checked(app, drv)
    x, y, w, h = drv.rect("ask_update"); app.pointer_move(x + w / 2, y + h / 2)
    for _ in range(8):
        time.sleep(0.15); drv.draw(1)
for size in SIZES:
    app, drv = fresh(size); drv.draw(3); tooltip(app, drv); shot(app, "tooltip", (size,), inv=False); app.close()

# ---------------------------------------------------------------- card U2: the package manager
from chisurf.plugins.core.updater.gui.package_app import PackageApp
from chisurf.plugins.core.updater.test.test_emtk_packages_clicks import PkgDriver


def pkg(name, setup, sizes=SIZES):
    for size in sizes:
        app = PackageApp(); drv = PkgDriver(app, size); drv.draw(3); drv.settle()
        setup(app, drv)
        shot(app, name, (size,))
        app.close()


def tab(name):
    return lambda app, drv: drv.open_tab(name)


pkg("pm_installed", lambda app, drv: None)
pkg("pm_installed_selected", lambda app, drv: drv.row("scipy"))
def filtered(app, drv): drv.type_into("installed_filter", "NUM")
pkg("pm_installed_filtered", filtered)
def remove_q(app, drv): drv.row("scipy"); drv.click("ask_remove_selected"); drv.draw(3)
pkg("pm_remove_question", remove_q)
def removed(app, drv): remove_q(app, drv); drv.press_text("Yes"); drv.settle()
pkg("pm_after_remove", removed)
def search(app, drv): drv.open_tab("search"); drv.type_into("search_query", "numpy"); drv.settle(); drv.row("2.0.1")
pkg("pm_search_results", search)
pkg("pm_envs", tab("envs"))
def create(app, drv):
    drv.open_tab("envs"); drv.click("ask_create_env"); drv.draw(3)
    x, y, w, h = drv.dialog_rect("dialog_input"); drv.click_at(x + 10, y + h / 2); drv.type_text("scratch"); drv.draw(2)
pkg("pm_create_env_dialog", create)
def export_dialog(app, drv): drv.open_tab("envs"); drv.row("/fake/mambaforge/envs/analysis"); drv.click("request_export"); drv.draw(3)
pkg("pm_export_dialog", export_dialog)
pkg("pm_channels", tab("channels"))
def failed(app, drv):
    fakes.solver_fails = True; drv.row("numpy"); drv.click("ask_remove_selected"); drv.press_text("Yes"); drv.settle()
pkg("pm_failure", failed)
fakes.solver_fails = False
def pm_help(app, drv): drv.click("help"); drv.draw(3)
pkg("pm_help", pm_help)
def pm_guide(app, drv): drv.click("guide"); drv.draw(3)
pkg("pm_guide_step_1", pm_guide)
# inside the updater window
def in_updater(app, drv):
    drv.click("open_package_manager"); drv.draw(5)
    end = time.monotonic() + 10
    while (app.packages.job.busy or app.packages.model.busy) and time.monotonic() < end:
        time.sleep(0.01); drv.draw(1)
    drv.draw(3)
each_size("pm_in_updater_window", in_updater)

# every spec control in the union (the control tool also reads the default app)
app, drv = fresh((1200, 800)); drv.draw(3); inventory(app); app.close()
report = ("fakes: process attempts", len(fakes.process_attempts), "| solver mutating", len(fakes.mutating_solver_commands),
          "| update commands", [c[0] for c in fakes.update_commands][:6], "| http", len(fakes.http_requests))
mp.undo()          # the fakes are done; the Qt-free proof starts a Python child that only imports and draws the window (3 frames)
after = {"controls": sorted(union), "interactive": sorted({str(i) for i in interactive}), "controls_without_tooltip": sorted(missing),
         "qt_free": qt_free("updater", "chisurf.plugins.core.updater.gui.app:make_app")}
(out / "after.json").write_text(json.dumps(after, indent=2, ensure_ascii=False))
print(len(union), "controls;", len(missing), "without tooltip;", "qt-free:", after["qt_free"]["ok"])
print(*report)
