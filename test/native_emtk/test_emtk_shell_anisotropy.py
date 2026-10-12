"""The anisotropy wizard's fits reach the emtk shell: listed, windowed, fitted, linked.

The wizard runs in the shell's process and registers its VV, VH and global fits; the shell reads them
through the session's server, whatever state that server owns. Every check reads what the shell shows.
"""

from __future__ import annotations

import time

import pytest
from emtk.testing import Driver

from chisurf.emtk.fit_docks import ANALYSIS_KEY, DATASETS_KEY
from chisurf.emtk.main_app import EmtkShellApp


@pytest.fixture
def shell(tmp_path, monkeypatch):
    """A shell with no plugins on a session with its own state (not the process lists)."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    from chisurf.emtk.session import start_session
    from chisurf.server.session import SessionState

    session = start_session(state=SessionState())
    app = EmtkShellApp({}, loader=lambda plugin_id: None)
    app.data.adopt(session)
    yield app
    app.close()


def _settle(driver, predicate, what, timeout=180.0):
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end, f"timed out waiting for {what}: {driver.app.data.status}"
        driver.frame(1)
        time.sleep(0.02)
    driver.frame(2)


def _idle(shell):
    return not shell.data.busy and not shell.data._dirty


def _wizard_fits(tmp_path):
    """The wizard's own path: demo files, load, create the three fits."""
    from chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.model import NativeAnisotropyModel

    model = NativeAnisotropyModel()
    model.example_folder = tmp_path / "demo"
    model.load_example()
    assert model.load_data(), model.status
    assert model.create_fits() is not None, model.status
    return model


def _rows(shell):
    return {row["name"]: row for row in shell.data.datasets.fits}


def _show(driver, shell, name):
    row = _rows(shell)[name]
    shell.data.show_fit(row["uid"])
    _settle(driver, lambda: _idle(shell) and shell.data.current_uid == row["uid"], name)
    return row["uid"]


def _param(shell, name, nth=0):
    return [r for r in shell.data.analysis.parameters if r["name"] == name][nth]


def test_wizard_fits_are_listed_windowed_and_fitted(shell, tmp_path):
    driver = Driver(shell, size=(1500, 950))
    driver.frame(2)
    data = shell.data
    _wizard_fits(tmp_path)
    _settle(driver, lambda: _idle(shell) and len(data.windows) == 3, "three fit windows")
    names = _rows(shell)
    assert set(names) == {
        "Lifetime - Anisotropy VV",
        "Lifetime - Anisotropy VH",
        "Global anisotropy",
    }
    assert {r["model"] for r in names.values()} == {"Lifetime", "GlobalFitModel"}
    datasets = {r["name"]: r["experiment"] for r in data.datasets.datasets}
    assert datasets["anis_decay_vv.dat"] == datasets["anis_decay_vh.dat"] == "TCSPC"
    # The Datasets dock offers the TCSPC models for a wizard curve, polarisation ones included.
    shell.docks.focus(DATASETS_KEY)
    data.datasets.select_dataset(next(r for r in data.datasets.datasets if r["name"] == "anis_decay_vv.dat"))
    assert "Lifetime" in data.datasets.model_names()
    assert "PDA2c-anisotropy" not in data.datasets.model_names()

    # VV is the master of the shared parameters, VH follows: the editor marks the followers.
    _show(driver, shell, "Lifetime - Anisotropy VV")
    editor = data.session.api.model_editor(fit_uid=data.current_uid)
    assert "anisotropy.polarization_type" in repr(editor), "the polarisation is a model choice"
    assert not _param(shell, "g")["linked"] and not _param(shell, "rho0")["linked"]
    _show(driver, shell, "Lifetime - Anisotropy VH")
    for name in ("g", "l1", "n0", "rho0", "b0", "t0"):
        assert _param(shell, name)["linked"] == name
    assert not _param(shell, "a1")["linked"], "only the shared parameters are linked"
    assert not data.analysis.cell_editable(_param(shell, "g"), "value"), "a follower is not edited"


def test_global_anisotropy_fit_runs_and_keeps_the_links(shell, tmp_path):
    driver = Driver(shell, size=(1500, 950))
    driver.frame(2)
    data = shell.data
    _wizard_fits(tmp_path)
    _settle(driver, lambda: _idle(shell) and len(data.windows) == 3, "three fit windows")
    _show(driver, shell, "Global anisotropy")
    shell.docks.focus(ANALYSIS_KEY)
    driver.frame(2)
    before = data.analysis.info["chi2r_current"]
    driver.click("analysis.run_fit")
    _settle(
        driver,
        lambda: _idle(shell) and data.analysis.info.get("chi2r_current") != before,
        "the global fit",
    )
    assert data.analysis.info["chi2r_current"] < before
    # The linked parameters stayed one value: the VV follower reads the VH master.
    api = data.session.api
    uids = {n: r["uid"] for n, r in _rows(shell).items()}
    for name in ("rho0", "t0", "n0"):
        vv = api.get_parameter(name, fit_uid=uids["Lifetime - Anisotropy VV"])["value"]
        vh = api.get_parameter(name, fit_uid=uids["Lifetime - Anisotropy VH"])["value"]
        assert vv == vh, name
    assert len(data.analysis.parameters) == 48, "both linked fits are edited in the global fit"


def test_dataset_picker_attaches_a_wizard_dataset(shell, tmp_path):
    driver = Driver(shell, size=(1500, 950))
    driver.frame(2)
    data = shell.data
    _wizard_fits(tmp_path)
    _settle(driver, lambda: _idle(shell) and len(data.windows) == 3, "three fit windows")
    _show(driver, shell, "Lifetime - Anisotropy VH")
    shell.docks.focus(ANALYSIS_KEY)
    driver.frame(2)
    assert data.analysis.info["dataset_name"] == "anis_decay_vh.dat"
    driver.click("analysis.select_dataset")
    driver.frame(2)
    picker = data.dataset_picker
    assert picker is not None
    names = [row["name"] for row in picker.rows]
    assert "Global Dataset" not in names and {"anis_decay_vv.dat", "anis_decay_vh.dat"} <= set(names)
    picker.pick(names.index("anis_decay_vv.dat"))
    _settle(
        driver,
        lambda: _idle(shell) and data.analysis.info.get("dataset_name") == "anis_decay_vv.dat",
        "VV attached",
    )
