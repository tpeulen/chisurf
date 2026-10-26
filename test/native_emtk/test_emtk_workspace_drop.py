"""One way in: a photon file dropped on the window becomes a linked photons dataset in the workspace.

The drop goes through the shell's own handler (:meth:`EmtkShellApp.on_files_dropped`), the import runs
on the shell's worker, and the Datasets table is read back; the dock is rendered for inspection.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from emtk.testing import Driver

from chisurf.emtk.fit_docks import DATASETS_KEY
from test.native_emtk.test_emtk_shell_fits import (  # noqa: F401  (the fixture and the helpers)
    SHOTS,
    _idle,
    _settle,
    shell,
)

REPO = Path(__file__).resolve().parents[2]
SPC = REPO / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"


def _photon_rows(shell):  # noqa: F811
    return [r for r in shell.data.datasets.datasets if r.get("kind") == "photons"]


def test_a_dropped_photon_file_is_linked_into_the_workspace(shell, tmp_path):  # noqa: F811
    driver = Driver(shell, (1300, 900))
    driver.frame(4)
    target = tmp_path / "m000.spc"
    shutil.copy(SPC, target)
    assert shell.on_files_dropped([str(target)])
    _settle(driver, lambda: _idle(shell) and _photon_rows(shell), "the photon dataset")
    (row,) = _photon_rows(shell)
    assert row["name"] == "m000.spc"
    assert row["source"] == "m000.spc" and row["source_address"] == str(target)
    assert "Photons" in row["kind_label"]
    # Not fittable: no model offered for it.
    shell.data.datasets.select_dataset(row)
    assert not shell.data.datasets.model_names()
    shell.docks.focus(DATASETS_KEY)
    shell.data.datasets.kind_filter = "photons"
    driver.frame(4)
    driver.screenshot(SHOTS / "workspace_photon_drop.png")


def test_add_as_embed_marks_the_dropped_file_embedded_and_the_menu_switches_it(
    shell,  # noqa: F811
    tmp_path,
):
    """Add as: Embed stores the file in the project; right-click switches a dataset either way."""
    options = dict(shell.data.datasets.import_mode_options())
    assert set(options) == {"link", "embed"}
    assert shell.data.datasets.import_mode == "link"
    driver = Driver(shell, (1300, 900))
    driver.frame(4)
    shell.data.datasets.import_mode = "embed"
    try:
        target = tmp_path / "m001.spc"
        shutil.copy(SPC, target)
        assert shell.on_files_dropped([str(target)])
        _settle(driver, lambda: _idle(shell) and _photon_rows(shell), "the photon dataset")
    finally:
        shell.data.datasets.import_mode = "link"
    (row,) = _photon_rows(shell)
    assert row["embedded"] and row["source"].startswith("📦")
    shell.data.datasets.select_dataset(row)
    assert shell.data.datasets.can_link() and not shell.data.datasets.can_embed()
    shell.data.datasets.link_selected()  # not saved yet: simply linked again
    _settle(driver, lambda: _idle(shell) and not _photon_rows(shell)[0]["embedded"], "relinked")
    shell.data.datasets.select_dataset(_photon_rows(shell)[0])
    assert shell.data.datasets.can_embed()
    shell.data.datasets.embed_selected()
    _settle(driver, lambda: _idle(shell) and _photon_rows(shell)[0]["embedded"], "embedded")


def test_export_project_names_the_data_it_only_links(shell, tmp_path):  # noqa: F811
    """Export Project… writes the copy and says which data stays outside it (not a block)."""
    driver = Driver(shell, (1300, 900))
    driver.frame(4)
    target = tmp_path / "m002.spc"
    shutil.copy(SPC, target)
    assert shell.on_files_dropped([str(target)])
    _settle(driver, lambda: _idle(shell) and _photon_rows(shell), "the photon dataset")
    project = shell.project
    project.save_as()
    driver.frame(2)
    assert project.file_dialog is not None and project.file_dialog.mode == "save"
    exported = tmp_path / "exported.cs.pto"
    project.choose_file(exported)
    _settle(driver, lambda: _idle(shell) and exported.is_file(), "the export")
    assert "links 1 data file(s) outside it (m002.spc)" in project.status
    assert "Make Self-contained" in project.status
