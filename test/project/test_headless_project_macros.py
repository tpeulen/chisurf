import json
import subprocess
import sys

import numpy as np

import chisurf as cs
from chisurf.core.data import DataCurve
from chisurf.core.fitting.fit import Fit, FitGroup
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.model import ModelCurve
from chisurf.macros.core_fit import (
    _decode_curve_payload,
    _encode_curve_array,
    load_project,
    save_project,
)


class DummyLinearModel(ModelCurve):
    name = "DummyLinearModel"

    def __init__(self, fit: Fit, **kwargs):
        super().__init__(fit, **kwargs)
        self.p0 = FittingParameter(name="p0", value=0.5)
        self.p1 = FittingParameter(name="p1", value=1.5)
        self.find_parameters()

    def _update_model(self, **kwargs):
        x = self.fit.data.x
        if x is None:
            x = np.arange(self.fit.data.y.size, dtype=float)
        self.x = x
        self.y = float(self.p0.value) + float(self.p1.value) * x


def test_project_curve_payload_uses_base64_arrays():
    x = np.array([0.0, 1.0, 2.0], dtype=float)
    payload = {
        "x": _encode_curve_array(x),
        "y": _encode_curve_array(np.array([0.0, 1.0, 4.0], dtype=float)),
        "ex": _encode_curve_array(np.zeros_like(x)),
        "ey": _encode_curve_array(np.ones_like(x)),
    }
    assert isinstance(payload["x"], dict)
    assert payload["x"]["encoding"] == "base64"

    dx, dy, dex, dey = _decode_curve_payload(payload)
    np.testing.assert_allclose(dx, x)
    np.testing.assert_allclose(dy, [0.0, 1.0, 4.0])
    np.testing.assert_allclose(dex, np.zeros_like(x))
    np.testing.assert_allclose(dey, np.ones_like(x))

    legacy_payload = {
        "x": x.tolist(),
        "y": [0.0, 1.0, 4.0],
        "ex": np.zeros_like(x).tolist(),
        "ey": np.ones_like(x).tolist(),
    }
    lx, ly, lex, ley = _decode_curve_payload(legacy_payload)
    np.testing.assert_allclose(lx, x)
    np.testing.assert_allclose(ly, [0.0, 1.0, 4.0])
    np.testing.assert_allclose(lex, np.zeros_like(x))
    np.testing.assert_allclose(ley, np.ones_like(x))


def test_headless_project_save_load(tmp_path):
    """
    Test that save_project and load_project can be called headlessly
    (without ever initializing a GUI or setting `cs.cs` to a window).
    """
    # 1. Ensure headless state
    assert getattr(cs, "cs", None) is None, "Test must run without a GUI instance"

    # 2. Setup some dummy data and a fit group
    cs.fits.clear()
    cs.imported_datasets.clear()

    x = np.linspace(0, 10, 100)
    y = np.sin(x)
    dc = DataCurve(x=x, y=y, name="headless_data")
    cs.imported_datasets.append(dc)

    fit_group = FitGroup(data=[dc], model_class=DummyLinearModel)
    local_fit = fit_group.grouped_fits[0]
    local_fit.fit_range = (10, 90)

    cs.fits.append(fit_group)

    # 3. Save the project headlessly
    archive_path = save_project(str(tmp_path), "test_macro_save")

    assert archive_path.is_file()
    assert archive_path.name.endswith(".cs.pto")

    from chisurf.core.project import ProjectArchive

    archive = ProjectArchive.open(archive_path)
    raw = json.loads(archive.read_text("project.json"))
    archive.close()
    dataset_uid, ds = next(iter(raw["datasets"].items()))
    assert dataset_uid != "ds000"
    assert dataset_uid == dc.unique_identifier
    assert set(ds["arrays"]) == {"x", "y", "ex", "ey", "mask"}
    assert all(set(array) == {"dtype", "values"} for array in ds["arrays"].values())
    saved_arrays = ds["arrays"]

    # 4. Clear current state to simulate a fresh load
    cs.fits.clear()
    cs.imported_datasets.clear()

    # 5. Load the project headlessly
    load_project(str(archive_path))

    second_path = save_project(str(tmp_path), "test_macro_save_again")
    second_archive = ProjectArchive.open(second_path)
    second_raw = json.loads(second_archive.read_text("project.json"))
    second_archive.close()
    assert next(iter(second_raw["datasets"].values()))["arrays"] == saved_arrays

    # 6. Verify restored state
    restored_dc = next(dc for dc in cs.imported_datasets if dc.name == "headless_data")
    assert restored_dc.name == "headless_data"
    np.testing.assert_allclose(restored_dc.x, x)
    np.testing.assert_allclose(restored_dc.y, y)
    np.testing.assert_allclose(restored_dc.ex, np.zeros_like(x))
    np.testing.assert_allclose(restored_dc.ey, np.ones_like(y))

    assert len(cs.fits) == 1
    restored_fit_group = cs.fits[0]
    # Check that model name is populated via the project fallback parsing
    # and fit ranges correctly re-established headlessly.
    assert len(restored_fit_group.grouped_fits) == 1
    restored_local_fit = restored_fit_group.grouped_fits[0]
    assert restored_local_fit.fit_range == (10, 90)

    print("Headless save/load roundtrip successful!")


def test_server_project_lifecycle_without_mmfdb(tmp_path):
    script = r"""\
import builtins
import pathlib
import sys

real_import = builtins.__import__
def blocked(name, *args, **kwargs):
    if name == "mmfdb" or name.startswith("mmfdb."):
        raise ModuleNotFoundError("No module named 'mmfdb'", name="mmfdb")
    return real_import(name, *args, **kwargs)
builtins.__import__ = blocked

from chisurf.server.app import ChiSurfServer
server = ChiSurfServer(cmd_port=0, pub_port=0)
try:
    assert server.state.flr_database is None
    target = pathlib.Path(sys.argv[1]) / "offline.cs.pto"
    saved = server.dispatcher.dispatch("project.save", {"target_path": str(target)})
    assert saved["ok"], saved
    loaded = server.dispatcher.dispatch("project.load", {"project_path": str(target)})
    assert loaded["ok"], loaded
finally:
    server.stop()
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_real_parse_model_expression_roundtrip():
    """Restore an actual scientific expression and its fitted coefficients."""
    from chisurf.core.models.parse.parse import ParseModel
    from chisurf.core.project.session import capture_session, restore_session

    x = np.linspace(0.1, 4.0, 32)
    curve = DataCurve(x=x, y=0.3 + 2.0 * np.exp(-x / 1.5))
    fit = Fit(data=curve, model_class=ParseModel)
    fit.model.func = "b+a1*exp(-x/t1)"
    values = {"b": 0.3, "a1": 2.0, "t1": 1.5}
    for parameter in fit.model.parameters_all:
        parameter.value = values[parameter.name]
    fit.model.update()
    assert fit.model.get_state().get("expression") == fit.model.func
    project = capture_session([curve], [fit])
    state = project.fits[0]["members"][0]["model"]["adapter_state"]
    assert state.get("expression") == fit.model.func
    restored = restore_session(project).fits[0]
    assert restored.model.func == fit.model.func
    assert {p.name: p.value for p in restored.model.parameters_all} == values
    np.testing.assert_allclose(restored.model.y, curve.y, rtol=1e-12)


def test_real_parse_model_numpy_expression_roundtrip():
    """Preserve valid NumPy expressions when the native compiler cannot bind them."""
    from chisurf.core.models.parse.parse import ParseModel
    from chisurf.core.project.session import capture_session, restore_session

    x = np.linspace(0.1, 4.0, 32)
    curve = DataCurve(x=x, y=np.exp(-x / 2.0) + 0.5)
    fit = Fit(data=curve, model_class=ParseModel)
    fit.model.func = "numpy.exp(-x/tau)+offset"
    for parameter in fit.model.parameters_all:
        parameter.value = {"tau": 2.0, "offset": 0.5}[parameter.name]
    fit.model.update()
    restored = restore_session(capture_session([curve], [fit])).fits[0]
    assert restored.model.func == fit.model.func
    np.testing.assert_allclose(restored.model.y, curve.y, rtol=1e-12)


def test_real_parse_model_expression_restores_in_fresh_process(tmp_path):
    """Reopen exact equation state without a live model or process registry."""
    from chisurf.core.models.parse.parse import ParseModel
    from chisurf.core.project.session import capture_session

    curve = DataCurve(x=np.linspace(0.1, 4.0, 32), y=np.ones(32))
    fit = Fit(data=curve, model_class=ParseModel)
    fit.model.load_catalogue("chisurf/core/models/parse/models.yaml")
    fit.model.model_name = fit.model.catalogue_names[0]
    selected = fit.model.model_name
    fit.model.func = "b+a1*exp(-x/t1)"
    values = {"b": 0.3, "a1": 2.0, "t1": 1.5}
    for parameter in fit.model.parameters_all:
        parameter.value = values[parameter.name]
    project = capture_session([curve], [fit])
    path = project.save(tmp_path / "parse.cs.pto")
    script = r"""
import sys
import numpy as np
from chisurf.core.project import Project, restore_session

restored = restore_session(Project.load(sys.argv[1])).fits[0]
assert restored.model.func == "b+a1*exp(-x/t1)"
assert restored.model.model_name == sys.argv[2]
assert {p.name: p.value for p in restored.model.parameters_all} == {
    "b": 0.3, "a1": 2.0, "t1": 1.5,
}
np.testing.assert_allclose(
    restored.model.y, 0.3 + 2.0 * np.exp(-restored.data.x / 1.5), rtol=1e-12,
)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(path), selected],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_parse_archive_expression_rejects_executable_python_before_parsing(monkeypatch):
    """Archive text cannot call arbitrary Python or reach runtime object attributes."""
    import pytest

    from chisurf.core.models.parse.parse import ParseModel

    curve = DataCurve(x=np.linspace(0.1, 4.0, 32), y=np.ones(32))
    model = Fit(data=curve, model_class=ParseModel).model
    parsed = []
    monkeypatch.setattr(model, "parse_code", lambda: parsed.append(True))
    for expression in (
        "__import__('os').system('true')",
        "numpy.load(x)",
        "numpy.exp.__call__(x)",
        "(lambda: x)()",
        "[x for x in x]",
    ):
        with pytest.raises(ValueError):
            model.set_state({"expression": expression, "model_name": ""})
    assert parsed == []


def test_parse_adapter_rejects_boolean_constants():
    """NumPy names cannot disguise boolean literals as scientific coefficients."""
    import pytest

    from chisurf.core.models.parse.parse import ParseModel

    curve = DataCurve(x=np.arange(1.0, 5.0), y=np.arange(1.0, 5.0))
    model = Fit(data=curve, model_class=ParseModel).model
    with pytest.raises(ValueError, match="constants must be finite numbers"):
        model.set_state({"expression": "x+True", "model_name": ""})


def test_no_parameter_parse_model_rejects_empty_archive_adapter_state():
    """An absent expression is incomplete even when no coefficients can reveal it."""
    import pytest

    from chisurf.core.models.parse.parse import ParseModel
    from chisurf.core.project.session import (
        SessionCodecError,
        capture_session,
        restore_session,
    )

    curve = DataCurve(x=np.arange(1.0, 5.0), y=np.arange(1.0, 5.0) * 3.0)
    fit = Fit(data=curve, model_class=ParseModel)
    fit.model.func = "x*3"
    assert fit.model.parameters_all == []
    project = capture_session([curve], [fit])
    project.fits[0]["members"][0]["model"]["adapter_state"] = {}
    with pytest.raises(SessionCodecError, match="cannot restore model state"):
        restore_session(project)


def test_parse_adapter_rejects_unexpected_archive_fields_before_parsing(monkeypatch):
    """External catalogue paths are not part of an explicit expression snapshot."""
    import pytest

    from chisurf.core.models.parse.parse import ParseModel

    curve = DataCurve(x=np.arange(1.0, 5.0), y=np.arange(1.0, 5.0) * 3.0)
    model = Fit(data=curve, model_class=ParseModel).model
    model.func = "x*3"
    state = model.get_state()
    state["catalogue_path"] = "/archive-controlled/catalogue.yaml"
    parsed = []
    monkeypatch.setattr(model, "parse_code", lambda: parsed.append(True))
    with pytest.raises(ValueError, match="unexpected ParseModel state fields"):
        model.set_state(state)
    assert parsed == []
