"""Real dye-shape computation and portable scientific-state regressions."""

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.fitting.fit import Fit
from chisurf.core.fluorescence import dyes
from chisurf.core.models.fcs.dye_shape import DyeShapeFCSModel
from test.project.test_all_model_catalogue_roundtrip import CATALOGUE, _data


def _fit():
    """Read the bundled measured Kristine correlation into the actual model."""
    entry = next(e for e in CATALOGUE if e["identity"].endswith("DyeShapeFCSModel"))
    data = _data(entry, DyeShapeFCSModel)
    return Fit(data=data, model_class=DyeShapeFCSModel, xmin=0, xmax=len(data.y))


def test_selected_reference_is_owned_by_model(monkeypatch):
    """Cache replacement cannot rewrite an already selected reference."""
    fit = _fit()
    model = fit.model
    model.dye_name = "Rhodamine 6G (Rh6G)"
    model._temp.value = 25.0
    model.update()
    before = model.y.copy()
    state = copy.deepcopy(model.get_state())
    assert state["reference"]["d25_um2_s"] == 414.0
    assert state["reference"]["unit"] == "um^2/s"
    changed = copy.deepcopy(dyes.reference_dyes())
    changed["Rhodamine 6G"]["d25_um2_s"] = 470.0
    monkeypatch.setattr(dyes, "_CACHE", changed)
    model.update()
    np.testing.assert_array_equal(model.y, before)
    restored = _fit().model
    restored.set_state(state)
    restored._temp.value = 25.0
    restored.update()
    np.testing.assert_array_equal(restored.y, before)
    assert restored.dye_name == "Rhodamine 6G (Rh6G)"
    assert restored.get_state() == state
    restored._w0.value *= 1.2
    restored.update()
    assert not np.allclose(restored.y, before)


def _portable_script():
    """Return a standalone real-reader loop used in fresh subprocesses."""
    return """
import importlib.abc, json, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "mmfdb" or fullname.startswith("mmfdb."):
            raise AssertionError("optional MMFDB import: " + fullname)
sys.meta_path.insert(0, Block())
from pathlib import Path
import numpy as np
from chisurf.core.fluorescence import dyes
from chisurf.core.project.session import capture_session, restore_session
from chisurf.core.project.storage import save_file, load_file
from chisurf.core.experiments.core.experiment import Experiment
from chisurf.core.experiments.fcs.reader import FCS
from chisurf.core.fitting.fit import Fit
from chisurf.core.models.fcs.dye_shape import DyeShapeFCSModel
def _fit():
    experiment = Experiment(name="fcs")
    experiment.add_model_class(DyeShapeFCSModel)
    reader = FCS(experiment=experiment, experiment_reader="kristine", record_provenance=False)
    data = reader.get_data(filename="test/data/fcs/kristine/Kristine_with_error.cor")[0]
    return Fit(data=data, model_class=DyeShapeFCSModel, xmin=0, xmax=len(data.y))
root = Path(sys.argv[1])
fit = _fit()
model = fit.model
assert len(model.dye_names()) == 16
assert dyes.diffusion_coefficient_25C("AF-647") == 330.0
model.dye_name = "Rh6G"
model._temp.value = 25.0
model._N.value = 2.5
model._s.value = 4.0
model.update()
assert np.isfinite(model.y).all()
assert abs(model._D.value - 414.0) < 1e-10
project = capture_session([fit.data], [fit])
path = save_file(project, root / "dye.cs.pto")
before = model.y.copy()
dyes._CACHE = {}; dyes._ALIASES = {}
restored = restore_session(load_file(path))
model = restored.fits[0].model
np.testing.assert_array_equal(model.y, before)
assert model.dye_name == "Rh6G"
assert "Rh6G" in model.dye_names()
assert capture_session(restored.datasets, restored.fits).fits == project.fits
model._temp.value = 30.0
model._w0.value = 450.0
model.update()
assert np.isfinite(model.y).all()
assert not np.allclose(model.y, before)
edited = capture_session(restored.datasets, restored.fits)
path = save_file(edited, root / "edited.cs.pto")
again = restore_session(load_file(path))
np.testing.assert_array_equal(again.fits[0].model.y, model.y)
assert capture_session(again.datasets, again.fits).fits == edited.fits
assert not any(k == "mmfdb" or k.startswith("mmfdb.") for k in sys.modules)
"""


def test_fresh_blocked_creation_restore_edit_resave(tmp_path):
    """Exercise creation too, before any saved state or reference cache exists."""
    script = _portable_script()
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_physically_absent_package_and_assets(tmp_path):
    """Run an isolated installed-style ChiSurf tree with no MMFDB on any path."""
    import site

    repo = Path(__file__).resolve().parents[2]
    isolated = tmp_path / "installation"

    def ignore(directory, names):
        """Copy code and runtime specs without large unrelated measurement assets."""
        return [
            name
            for name in names
            if name == "__pycache__"
            or (
                Path(directory, name).is_file()
                and Path(name).suffix not in {".py", ".json", ".yaml", ".ui", ".qss", ".css"}
            )
        ]

    shutil.copytree(repo / "chisurf", isolated / "chisurf", ignore=ignore)
    paths = [
        str(isolated),
        *site.getsitepackages(),
        str(repo / "modules/chinet"),
        str(repo / "modules/imp-tricks/src"),
        str(repo / "modules/chimol"),
        "/Users/tpeulen/dev/imp/cmake-build-arm64/lib",
    ]
    prefix = f"""
import sys, importlib.util
sys.path[:0] = {paths!r}
assert importlib.util.find_spec("mmfdb") is None
"""
    script = (
        prefix
        + _portable_script()
        .replace("sys.meta_path.insert(0, Block())", "")
        .replace(
            '"test/data/fcs/kristine/Kristine_with_error.cor"',
            repr(str(repo / "test/data/fcs/kristine/Kristine_with_error.cor")),
        )
        + """
assert importlib.util.find_spec("mmfdb") is None
assert not any("mmfdb" in path for path in sys.path)
"""
    )
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", script, str(tmp_path)],
        cwd=isolated,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_repository_change_and_removal_do_not_change_saved_reference(tmp_path, monkeypatch):
    """Configured repository values survive mutation, deletion, edits and resave."""
    from mmfdb.repository import MFDatabase

    from chisurf.core.project.session import capture_session, restore_session
    from chisurf.core.project.storage import load_file, save_file

    database = tmp_path / "configured.db"
    with MFDatabase(database) as db:
        db.import_reference_diffusion()
        from mmfdb.admin.backend.password_services import hash_password
        from mmfdb.security.login import login

        # Explicit test deployment provisioning/authentication, never done by
        # ChiSurf's reference lookup. This does not change a global provider.
        db.add_user(
            "calibrator",
            "Reference calibrator",
            password_hash=hash_password("test-only-reference-password"),
        )
        authenticated = login(
            db.conn, provider="local", user_id="calibrator", password="test-only-reference-password"
        )
        assert authenticated["authenticated"]
        # A deliberate stored-property perturbation proves the model uses the
        # configured source's actual value, rather than silently taking its export.
        db.conn.execute(
            "UPDATE optical_properties SET property_value=property_value*1.1 "
            "WHERE property_name='d25'"
        )
        db.conn.commit()
        original = next(
            e
            for e in db.get_diffusion_reference(seed_if_empty=False)
            if e["name"] == "Rhodamine 6G"
        )
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(database))
    monkeypatch.setattr(dyes, "_CACHE", None)
    monkeypatch.setattr(dyes, "_ALIASES", None)
    fit = _fit()
    fit.model.dye_name = "Rh6G"
    fit.model._temp.value = 25.0
    fit.model.update()
    assert fit.model._D.value == pytest.approx(original["d25_um2_s"], abs=1e-10)
    reference = fit.model.get_state()["reference"]
    assert reference["probe_id"] == original["probe_id"]
    assert reference["sources"] == original["sources"]
    project = capture_session([fit.data], [fit])
    saved = save_file(project, tmp_path / "configured.cs.pto")
    with MFDatabase(database) as db:
        # Test perturbation of a real stored property; not a scientific default.
        db.conn.execute(
            "UPDATE optical_properties SET property_value=? WHERE probe_id=? "
            "AND property_name='d25'",
            (original["d25_um2_s"] * 1.1, original["probe_id"]),
        )
        db.conn.commit()
    assert dyes.reference_dyes(refresh=True)["Rhodamine 6G"]["d25_um2_s"] != reference["d25_um2_s"]
    restored = restore_session(load_file(saved))
    np.testing.assert_array_equal(restored.fits[0].model.y, fit.model.y)
    assert capture_session(restored.datasets, restored.fits).fits == project.fits
    database.unlink()
    monkeypatch.setattr(dyes, "_CACHE", None)
    monkeypatch.setattr(dyes, "_ALIASES", None)
    with pytest.raises(Exception):
        dyes.reference_dyes(refresh=True)
    assert not database.exists(), "reference lookup bootstrapped a missing database"
    restored = restore_session(load_file(saved))
    model = restored.fits[0].model
    assert "Rh6G" in model.dye_names()
    model.dye_name = "Rhodamine 6G (Rh6G)"
    model._temp.value = 30.0
    model._w0.value = 450.0
    model.update()
    assert not np.allclose(model.y, fit.model.y)
    edited = capture_session(restored.datasets, restored.fits)
    resaved = save_file(edited, tmp_path / "configured-edited.cs.pto")
    again = restore_session(load_file(resaved))
    np.testing.assert_array_equal(again.fits[0].model.y, model.y)
    assert again.fits[0].model.get_state()["reference"] == reference
    assert capture_session(again.datasets, again.fits).fits == edited.fits
    before = model.y.copy()
    model.dye_name = "Cy5"
    model.update()
    assert model.get_state()["reference"]["source"] == "reference_diffusion"
    assert model.get_state()["reference"]["d25_um2_s"] == 360.0
    assert not np.allclose(model.y, before)
    assert not database.exists()


@pytest.mark.parametrize(
    "key,value",
    [
        ("d25_um2_s", float("nan")),
        ("d25_um2_s", float("inf")),
        ("d25_um2_s", 0.0),
        ("d25_um2_s", -1.0),
        ("d25_um2_s", True),
        ("unit", "m^2/s"),
        ("name", ""),
        ("sources", [object()]),
    ],
)
def test_invalid_reference_state_is_rejected_atomically(key, value):
    """Corrupt or ambiguous scientific inputs never enter restored computation."""
    model = _fit().model
    before = model.get_state()
    invalid = copy.deepcopy(before)
    invalid["reference"][key] = value
    with pytest.raises((ValueError, TypeError)):
        model.set_state(invalid)
    assert model.get_state() == before


def test_state_has_no_live_objects_and_preserves_identity():
    """The explicit adapter is plain data and retains source identifiers."""
    model = _fit().model
    state = model.get_state()
    assert json.loads(json.dumps(state, allow_nan=False)) == state
    state["reference"]["probe_id"] = 918
    state["reference"]["source"] = "curated-experiment"
    model.set_state(state)
    assert model.get_state() == state


def test_portable_export_matches_pinned_upstream_definitions():
    """Prevent an independently maintained numeric/provenance table from drifting."""
    import hashlib

    root = Path(dyes.__file__).parent
    origin = json.loads((root / "reference_diffusion.origin.json").read_text())
    data = (root / "reference_diffusion.json").read_bytes()
    upstream = Path("modules/mmfdb/src/mmfdb/data/reference_diffusion.json").read_bytes()
    assert data == upstream
    assert hashlib.sha256(data).hexdigest() == origin["sha256"]
    assert origin["temperature_K"] == 298.15
    assert origin["solvent"] == "water"
    table = json.loads(data)
    assert len(table) == 16
    for entry in table:
        assert entry["sources"]
        assert entry["d25_um2_s"] > 0


@pytest.mark.parametrize(
    "name",
    [
        "AF647",
        "AF-647",
        "af 647",
        "Alexa Fluor 647™",
        "Cyanine 5",
        "Rhodamine 6G (Rh6G)",
        "RNase A",
    ],
)
def test_name_normalization_preserves_upstream_equivalence(name):
    """Only display-name spelling is normalized, by the exact upstream rule."""
    from mmfdb.admin.backend.duplicate_grouping import normalize_name

    assert dyes._normalized(name) == normalize_name(name)


def test_unknown_selection_and_mismatched_state_are_rejected():
    """Typing a typo cannot replace scientific inputs with a guess or NaN."""
    model = _fit().model
    before = model.get_state()
    with pytest.raises(ValueError, match="unknown"):
        model.dye_name = "not a reference species"
    assert model.get_state() == before
    invalid = copy.deepcopy(before)
    invalid["dye_name"] = "Cy5"
    with pytest.raises(ValueError, match="saved reference"):
        model.set_state(invalid)
    assert model.get_state() == before


def test_restored_editor_keeps_reference_and_model_controls(tmp_path, monkeypatch):
    """Render measured-data controls and use the actual restored reference picker."""
    from qtpy import QtWidgets

    from chisurf.gui.widgets.models.model_editor import build_model_editor

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    fit = _fit()
    model = fit.model
    model.dye_name = "Rh6G"
    state = model.get_state()
    model.set_state(state)
    monkeypatch.setattr(dyes, "_CACHE", {})
    monkeypatch.setattr(dyes, "_ALIASES", {})
    model.update()
    first = model.y.copy()
    editor = build_model_editor(model)
    editor.resize(780, 820)
    editor.show()
    app.processEvents()
    combos = editor.findChildren(QtWidgets.QComboBox)
    picker = next(combo for combo in combos if combo.findText("Cy5") >= 0)
    assert picker.currentText() == "Rh6G"
    picker.setCurrentIndex(picker.findText("Cy5"))
    app.processEvents()
    model.update()
    assert model.dye_name == "Cy5"
    assert not np.allclose(model.y, first)
    assert [p.name for p in model._shape_parameter_rows()] == ["N", "s", "w0", "b", "temp"]
    assert [p.name for p in model._bunching_parameter_rows()] == ["ba", "bt"]
    assert [p.name for p in model._output_parameter_rows()] == ["D", "tauD", "cpm", "cpm_all"]
    assert editor.grab().save(str(tmp_path / "dye-restored-controls.png"))
    editor.close()


@pytest.mark.parametrize("operation", ["selection", "choices"])
def test_restored_model_does_not_mask_configured_source_failures(monkeypatch, operation):
    """Authentication/schema/data errors remain errors, unlike source removal."""
    from chisurf.core.models.fcs import dye_shape

    model = _fit().model
    model.dye_name = "Rh6G"
    before = model.get_state()
    model.set_state(before)

    def denied(*args, **kwargs):
        """Inject a genuine failure category at the source seam, not reference data."""
        raise PermissionError("configured source denied access")

    if operation == "selection":
        monkeypatch.setattr(dye_shape, "get_dye", denied)
        with pytest.raises(PermissionError, match="denied"):
            model.dye_name = "Cy5"
    else:
        monkeypatch.setattr(dye_shape, "dye_names", denied)
        with pytest.raises(PermissionError, match="denied"):
            model.dye_names()
    assert model.get_state() == before


def test_new_picker_default_uses_actual_configured_species(tmp_path, monkeypatch):
    """A new picker must not offer a placeholder missing from its real source."""
    from mmfdb.repository import MFDatabase

    database = tmp_path / "one-reference.db"
    with MFDatabase(database) as db:
        db.import_reference_diffusion()
        db.conn.execute("UPDATE probes SET deleted_at='2026-10-04' WHERE chromophore_name <> 'Cy5'")
        db.conn.commit()
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(database))
    monkeypatch.setattr(dyes, "_CACHE", None)
    monkeypatch.setattr(dyes, "_ALIASES", None)
    model = _fit().model
    assert model.dye_name == "Cy5"
    assert model.dye_names() == ["Cy5"]
    assert model.get_state()["reference"]["probe_id"] is not None
    model.update()
    assert np.isfinite(model.y).all()
