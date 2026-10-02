"""The Qt updater and package manager, populated, on fakes. Usage: <out_dir>.

Writes before_populated_*.png and qt_values.json (every number, text and command line the Qt tool produced). SAFETY: every system
action is a fake (chisurf.plugins.core.updater.test.fakes): no update, install, removal, environment change or network; settings, HOME
and the MMFDB paths are in a temporary folder.
"""
import json, os, pathlib, sys, tempfile

tmp = pathlib.Path(tempfile.mkdtemp(prefix="upd_qt_"))
os.environ.update(CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"),
                  MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"), HOME=str(tmp / "home"), QT_QPA_PLATFORM="offscreen")
(tmp / "s").mkdir(); (tmp / "home").mkdir()
import pytest
from qtpy import QtCore, QtTest, QtWidgets

out = pathlib.Path(sys.argv[1])
mp = pytest.MonkeyPatch()
from chisurf.plugins.core.updater.test.fakes import Fakes
fakes = Fakes().install(mp)

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.gui import dialogs
import chisurf.plugins.core.updater as upd
from chisurf.plugins.core.updater import package_widget as pw

asked, answers = [], {"confirm": True, "question": QtWidgets.QMessageBox.Yes}
mp.setattr(dialogs, "confirm", lambda parent, title, text, **k: (asked.append(("confirm", title, text)), answers["confirm"])[1])
mp.setattr(dialogs, "question", lambda parent, title, text, *a, **k: (asked.append(("question", title, text)), answers["question"])[1])
mp.setattr(dialogs, "information", lambda parent, title, text, **k: asked.append(("information", title, text)))
mp.setattr(dialogs, "error", lambda parent, title, text, **k: asked.append(("error", title, text)))
typed = {"names": []}
mp.setattr(QtWidgets.QInputDialog, "getText", staticmethod(lambda parent, title, label, *a, **k: (asked.append(("input", title, label)), (typed["names"].pop(0) if typed["names"] else "", True))[1]))
mp.setattr(QtWidgets.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(tmp / "exported.yaml"), "")))
mp.setattr(QtWidgets.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(tmp / "env.yaml"), "")))
(tmp / "env.yaml").write_text("name: imported\n")

values = {}


def pump(ms=300):
    QtTest.QTest.qWait(ms)


def grab(widget, name):
    pump(100)
    widget.grab().save(str(out / f"before_populated_{name}.png"))


# ---------------------------------------------------------------- the updater tab
w = upd.UpdaterWidget()
w.resize(800, 600); w.show()
pump(900)                       # the 150 ms auto check on start
htmls = []
orig = w.changelog_text.setHtml
w.changelog_text.setHtml = lambda h: (htmls.append(h), orig(h))
grab(w, "updater_initial")
values["initial"] = dict(status=w.status_label.text(), tooltip=w.status_label.toolTip(), branch=w.branch_label.text(),
                         dev_checked=w.dev_checkbox.isChecked(), dev_enabled=w.dev_checkbox.isEnabled(),
                         check_on_start=w.cb_check_on_start.isChecked(), ignore=w.cb_ignore_updates.isChecked(),
                         items=[w.version_dropdown.itemText(i) for i in range(w.version_dropdown.count())],
                         dropdown_enabled=w.version_dropdown.isEnabled(), update_enabled=w.update_button.isEnabled(),
                         check_enabled=w.check_button.isEnabled(), changelog_plain=w.changelog_text.toPlainText(),
                         current_version=w.updater.current_version)
w.check_button.click(); pump(200)
values["checked"] = dict(status=w.status_label.text(), items=[w.version_dropdown.itemText(i) for i in range(w.version_dropdown.count())],
                         index=w.version_dropdown.currentIndex(), changelog_plain=w.changelog_text.toPlainText(), html=htmls[-1])
values["html_by_index"] = {}
for i in range(w.version_dropdown.count()):
    w.version_dropdown.setCurrentIndex(i); pump(100)
    values["html_by_index"][i] = htmls[-1]
    if i == 1:
        grab(w, "updater_version_2")
w.version_dropdown.setCurrentIndex(0); pump(100)
grab(w, "updater_checked")
w.cb_check_on_start.setChecked(False); w.cb_ignore_updates.setChecked(True); pump(100)
import yaml
settings_file = tmp / "s" / "settings_chisurf.yaml"
values["startup_saved"] = yaml.safe_load(settings_file.read_text()) if settings_file.exists() else None
grab(w, "updater_startup_toggled")
# Update Now: declined, then accepted (a version selected)
answers["confirm"] = False
w.update_button.click(); pump(100)
values["update_declined"] = dict(status=w.status_label.text(), commands=list(fakes.update_commands), asked=list(asked))
answers["confirm"] = True
asked.clear()
w.update_button.click(); pump(100)
values["update_accepted"] = dict(status=w.status_label.text(), commands=list(fakes.update_commands), asked=list(asked))
for dialog in app.topLevelWidgets():
    if dialog is not w and dialog.isVisible():
        dialog.grab().save(str(out / "before_populated_updater_progress.png"))
        dialog.close()
# the fallback (no version list): no package file, the standard update
fakes.update_commands.clear()
fakes.releases = []
w2 = upd.UpdaterWidget(suppress_initial_notification=False); w2.show(); pump(900)
grab(w2, "updater_no_versions")
values["no_versions"] = dict(status=w2.status_label.text(), items=w2.version_dropdown.count(), update_enabled=w2.update_button.isEnabled(),
                             changelog_plain=w2.changelog_text.toPlainText())
w2.close()
fakes.releases = [dict(r) for r in __import__("chisurf.plugins.core.updater.test.fakes", fromlist=["RELEASES"]).RELEASES]
w.close()
fakes.update_commands.clear()
# the fallback standard update (selected index absent): the module function builds the latest line
from chisurf.plugins.core.updater.updater import update_chisurf
update_chisurf(callback=lambda m: None, auto_restart=False)
values["standard_update_commands"] = list(fakes.update_commands)
values["http"] = list(fakes.http_requests)
values["format_changelog"] = {}
sample = ("Changes between 26.09.20 and 26.10.02:\n- 2026-10-01 Add <the> updater (by Ada)\nplain line & more\n"
          "\nMore details: https://github.com/Fluorescence-Tools/chisurf/commits")
values["format_changelog"] = {"input": sample, "html": upd.UpdaterWidget._format_changelog_html(None, sample),
                              "empty": upd.UpdaterWidget._format_changelog_html(None, "  ")}

# ---------------------------------------------------------------- the package manager
fakes.solver_commands.clear(); asked.clear()
d = pw.PackageManagerDialog(); d.resize(800, 600); d.show(); pump(900)
m = d.widget
values["pm_initial"] = dict(env=m.current_env_label.text(), installed=[[m.installed_table.item(r, c).text() for c in range(3)] for r in range(m.installed_table.rowCount())],
                            envs=[m.envs_list.item(i).text() for i in range(m.envs_list.count())], channels=[m.channels_list.item(i).text() for i in range(m.channels_list.count())],
                            log=m.log_text.toPlainText(), tabs=[m.tabs.tabText(i) for i in range(m.tabs.count())], startup_commands=list(fakes.solver_commands))
grab(d, "pm_installed")
m.installed_filter.setText("NUM"); pump(100)
values["pm_filter"] = [[m.installed_table.item(r, c).text() for c in range(3)] for r in range(m.installed_table.rowCount())]
grab(d, "pm_installed_filtered")
m.installed_filter.setText("")
m.tabs.setCurrentIndex(1); m.search_input.setText("numpy"); m.search_btn.click(); pump(400)
values["pm_search_rows"] = m.search_results.rowCount()
values["pm_search_log"] = m.log_text.toPlainText()
grab(d, "pm_search")
mp.setattr(type(fakes), "popen", type(fakes).popen)
fakes.search_payload = [{"name": "numpy", "version": "2.0.1", "channel": "conda-forge"}, {"name": "numpy-base", "version": "1.26.4", "channel": "defaults"}]
m.search_btn.click(); pump(400)
values["pm_search_rows_list_payload"] = [[m.search_results.item(r, c).text() for c in range(3)] for r in range(m.search_results.rowCount())]
grab(d, "pm_search_list_payload")
fakes.solver_commands.clear()
m.search_results.selectRow(0); m.install_btn.click(); pump(400)
values["pm_install"] = dict(asked=list(asked), commands=[c for c in fakes.solver_commands if c[1] not in ("list",)])
m.tabs.setCurrentIndex(0); m.installed_table.selectRow(1)
asked.clear(); fakes.solver_commands.clear()
m.update_btn.click(); pump(400)
values["pm_update_selected"] = dict(asked=list(asked), commands=[c for c in fakes.solver_commands if c[1] != "list" and c[1:3] != ["env", "list"] and "--show" not in c])
fakes.solver_commands.clear(); asked.clear()
m.update_all_btn.click(); pump(400)
values["pm_update_all"] = dict(asked=list(asked), commands=[c for c in fakes.solver_commands if c[1] == "update"])
fakes.solver_commands.clear(); asked.clear()
m.installed_table.selectRow(1)
answers["question"] = QtWidgets.QMessageBox.No
m.remove_btn.click(); pump(300)
values["pm_remove_declined"] = dict(asked=list(asked), commands=[c for c in fakes.solver_commands if c[1] == "remove"])
answers["question"] = QtWidgets.QMessageBox.Yes
asked.clear(); fakes.solver_commands.clear()
m.remove_btn.click(); pump(400)
values["pm_remove"] = dict(asked=list(asked), commands=[c for c in fakes.solver_commands if c[1] == "remove"])
grab(d, "pm_after_remove")
m.tabs.setCurrentIndex(2); pump(100)
grab(d, "pm_envs")
fakes.solver_commands.clear(); asked.clear()
typed["names"] = ["scratch"]; m.create_env_btn.click(); pump(400)
values["pm_create_env"] = dict(asked=list(asked), commands=[c for c in fakes.solver_commands if c[1] == "create"])
m.envs_list.setCurrentRow(2); typed["names"] = ["analysis-copy"]; asked.clear(); fakes.solver_commands.clear()
m.clone_env_btn.click(); pump(400)
values["pm_clone_env"] = dict(asked=list(asked), commands=[c for c in fakes.solver_commands if c[1] == "create"])
m.envs_list.setCurrentRow(1); asked.clear(); fakes.solver_commands.clear()
m.remove_env_btn.click(); pump(400)
values["pm_remove_env"] = dict(asked=list(asked), commands=[c for c in fakes.solver_commands if c[1:3] == ["env", "remove"]])
m.envs_list.setCurrentRow(2); asked.clear(); fakes.solver_commands.clear()
m.export_env_btn.click(); pump(400)
values["pm_export_env"] = dict(commands=[c for c in fakes.solver_commands if c[1:3] == ["env", "export"]], file=(tmp / "exported.yaml").read_text() if (tmp / "exported.yaml").exists() else None)
typed["names"] = ["imported"]; asked.clear(); fakes.solver_commands.clear()
m.import_env_btn.click(); pump(400)
values["pm_import_env"] = dict(asked=list(asked), commands=[c for c in fakes.solver_commands if c[1:3] == ["env", "create"]])
grab(d, "pm_envs_after")
m.tabs.setCurrentIndex(3); pump(100)
grab(d, "pm_channels")
typed["names"] = ["bioconda"]; asked.clear(); fakes.solver_commands.clear()
m.add_channel_btn.click(); pump(400)
values["pm_add_channel"] = dict(asked=list(asked), commands=[c for c in fakes.solver_commands if c[1] == "config" and "--show" not in c])
m.channels_list.setCurrentRow(0); fakes.solver_commands.clear()
m.remove_channel_btn.click(); pump(400)
values["pm_remove_channel"] = dict(commands=[c for c in fakes.solver_commands if c[1] == "config" and "--show" not in c])
values["pm_log_end"] = m.log_text.toPlainText()
grab(d, "pm_log")
fakes.solver_fails = True; fakes.solver_commands.clear(); asked.clear()
m.tabs.setCurrentIndex(0); m.installed_table.selectRow(0); answers["question"] = QtWidgets.QMessageBox.Yes
m.remove_btn.click(); pump(400)
values["pm_failure"] = dict(asked=list(asked))
grab(d, "pm_failure")
d.close()
values["safety"] = dict(process_attempts=len(fakes.process_attempts), mutating_solver_commands_in_failure=len(fakes.mutating_solver_commands))
(out / "qt_values.json").write_text(json.dumps(values, indent=2, ensure_ascii=False, default=str))
print(json.dumps({k: (v if k in ("safety",) else "...") for k, v in values.items()}, indent=1))
mp.undo()
