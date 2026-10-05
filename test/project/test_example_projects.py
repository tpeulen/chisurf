"""Tests that the example projects under examples/projects can be loaded.

These tests ensure that the project JSON format used by the example
projects is compatible with the loader and that the project state
(datasets and, where applicable, fits) is restored.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import numpy as np
import pytest

# Ensure chisurf package is on the path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import chisurf as cs  # noqa: E402
import chisurf.gui  # noqa: E402,F401  # ensure cs.gui is a module
import chisurf.gui.widgets  # noqa: E402,F401  # ensure cs.gui.widgets resolves
from chisurf.core.data import DataCurve  # noqa: E402
from chisurf.core.project import capture_session, restore_session, save_project  # noqa: E402
from chisurf.core.project.storage import ProjectStorageError  # noqa: E402
from chisurf.macros.core_fit import load_project_data  # noqa: E402

EXAMPLES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "examples", "projects")
)


@pytest.fixture(autouse=True)
def isolated_project_owner(monkeypatch):
    """Use a concrete local owner without borrowing another test's GUI or lists."""
    from chisurf.core.project.project import ResourceContext
    from chisurf.history.core import OperationHistory

    for name, value in (
        ("fits", []),
        ("imported_datasets", []),
        ("cs", None),
        ("__client__", None),
        ("_project_gui", None),
        ("_project_authorizations", {}),
        ("_project_transition", None),
        ("history", OperationHistory()),
        ("native_session", None),
        ("project_resources", ResourceContext()),
    ):
        monkeypatch.setattr(cs, name, value, raising=False)


def _reset_state():
    """Reset this fixture's local owner collections to a headless baseline."""
    cs.fits.clear()
    cs.imported_datasets.clear()
    try:
        cs.cs = None
    except Exception:
        pass


def test_cs_gui_is_module():
    """`chisurf.gui` must remain a module — code paths like
    `cs.gui.widgets.hide_items_in_layout(...)` rely on it. A
    regression where something assigns a Main instance to
    ``cs.gui`` would break every GUI call site.
    """
    # Sanity: it's a module and exposes the standard submodules
    assert isinstance(cs.gui.__name__, str) and cs.gui.__name__ == "chisurf.gui"
    assert cs.gui.widgets.__name__ == "chisurf.gui.widgets"


def _is_csp_project(path):
    """Check if path is a .cs.pto project or a directory containing project.cs.pto."""
    if os.path.isfile(path) and path.endswith(".cs.pto"):
        return True
    if os.path.isdir(path) and os.path.isfile(os.path.join(path, "project.cs.pto")):
        return True
    return False


def test_t4l_chimol_project_loads(tmp_path):
    """The v4 fixture is rejected; an equivalent v5 PTO loads end-to-end."""
    project_path = os.path.join(EXAMPLES_DIR, "t4l_chimol")
    csp_path = project_path + ".cs.pto"
    if _is_csp_project(csp_path):
        load_path = csp_path
    elif _is_csp_project(project_path):
        load_path = project_path
    elif os.path.isdir(project_path):
        pytest.skip(f"Example project {project_path} has not been converted to .cs.pto format yet")
    else:
        pytest.skip(f"Example project not found: {project_path}")

    _reset_state()
    sentinel = object()
    cs.imported_datasets.append(sentinel)
    with pytest.raises(ProjectStorageError, match="Could not load project file"):
        load_project_data(load_path)
    assert cs.imported_datasets == [sentinel]
    assert cs.fits == []

    curve = DataCurve(
        x=np.arange(4, dtype=float),
        y=np.array([1.0, 2.0, 3.0, 4.0]),
        name="t4l-chimol-v5",
        unique_identifier="t4l-chimol-dataset",
    )
    v5_path = save_project(
        capture_session([curve], [], name="t4l_chimol-v5"), tmp_path / "t4l_chimol_v5"
    )
    _reset_state()
    fit_uids = load_project_data(str(v5_path))
    assert isinstance(fit_uids, list)
    # 0 fits by design
    assert len(cs.fits) == 0
    # Loading must not have corrupted `cs.gui`.
    assert cs.gui.__name__ == "chisurf.gui"


def test_t4l_proteinmc_project_loads(tmp_path):
    """Reject the v4 example, then portably restore an actual structured T4L fit."""
    project_path = os.path.join(EXAMPLES_DIR, "t4l_proteinmc")
    csp_path = project_path + ".cs.pto"
    if _is_csp_project(csp_path):
        load_path = csp_path
    elif _is_csp_project(project_path):
        load_path = project_path
    elif os.path.isdir(project_path):
        pytest.skip(f"Example project {project_path} has not been converted to .cs.pto format yet")
    else:
        pytest.skip(f"Example project not found: {project_path}")

    _reset_state()
    sentinel = object()
    cs.imported_datasets.append(sentinel)
    with pytest.raises(ProjectStorageError, match="Could not load project file"):
        load_project_data(load_path)
    assert cs.imported_datasets == [sentinel]
    assert cs.fits == []

    import shutil
    from pathlib import Path

    from chisurf.core.experiments.core import Experiment
    from chisurf.core.experiments.modelling.reader import StructureReader
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.structure.proteinmc_model import ProteinMCModel

    source = tmp_path / "148l.pdb"
    shutil.copyfile(Path(ROOT) / "test/data/atomic_coordinates/pdb_files/148l.pdb", source)
    reader = StructureReader(experiment=Experiment(name="Structure"), record_provenance=False)
    curve = reader.get_data(filename=str(source))[0]
    curve.data_reader = reader
    curve.name = "t4l-proteinmc-v5"
    curve.unique_identifier = "t4l-proteinmc-dataset"
    assert curve.atoms.dtype.names and len(curve.atoms) > 0

    fit = Fit(model_class=ProteinMCModel, data=curve)
    fit.unique_identifier = "t4l-proteinmc-fit"
    fit.fit_range = reader.autofitrange(curve)
    assert tuple(fit.fit_range) == (0, 0)  # Structure data has no curve interval.
    fit.model.n_iter = 37
    fit.model.n_out = 3
    captured = capture_session([curve], [fit], name="t4l_proteinmc-v5")
    v5_path = save_project(captured, tmp_path / "t4l_proteinmc_v5")
    source.unlink()
    restored = restore_session(captured)
    _reset_state()
    fit_uids = load_project_data(str(v5_path))
    assert isinstance(fit_uids, list)
    assert len(restored.fits) == 1
    restored_fit = restored.fits[0]
    assert type(restored_fit.model) is ProteinMCModel
    assert restored_fit.fit_range == (0, 0)
    assert restored_fit.model.n_iter == fit.model.n_iter == 37
    assert restored_fit.model.n_out == fit.model.n_out == 3
    assert restored_fit.data is restored.datasets[0]
    restored_structure = restored_fit.model.structure
    assert restored_structure is not None
    np.testing.assert_array_equal(restored_structure.atoms, curve.atoms)
    np.testing.assert_array_equal(restored_structure.xyz, curve.xyz)
    assert len(cs.fits) == 1
    assert cs.fits[0].unique_identifier == fit.unique_identifier
    assert cs.fits[0].data is cs.imported_datasets[0]
    loaded_structure = cs.fits[0].model.structure
    assert loaded_structure is not None
    np.testing.assert_array_equal(loaded_structure.atoms, curve.atoms)
    assert not source.exists()
    # Loading must not have corrupted `cs.gui`.
    assert cs.gui.__name__ == "chisurf.gui"


def test_load_project_payload_does_not_reinitialize_gui_during_staging(monkeypatch):
    """Detached loading must not reset the GUI before restoration completes."""
    from chisurf.core.project import Project
    from chisurf.macros.core_fit import load_project_payload

    calls = []
    guard_calls = []

    class FakeGui:
        def _guard_project_transition(self):
            """Represent explicit consent from this concrete document owner."""
            guard_calls.append("confirm")
            return True

        def reinitialize(self, show_confirmation=True, show_success=True):
            calls.append((show_confirmation, show_success))

        def update(self):
            pass

        dataset_selector = SimpleNamespace(update=lambda: None)
        fit_selector = SimpleNamespace(update=lambda: None)

    gui = FakeGui()
    monkeypatch.setattr(cs, "cs", gui)
    monkeypatch.setattr(cs, "_project_gui", gui, raising=False)
    monkeypatch.setattr(chisurf.gui, "fit_windows", [])
    result = load_project_payload(Project(name="test"), project_path=None)

    assert result["ok"] is True
    assert guard_calls and set(guard_calls) == {"confirm"}
    assert calls == []


def test_reinitialize_application_does_not_overwrite_cs_gui():
    """`reinitialize_application` previously did
    ``setattr(cs, 'gui', main_window)`` which clobbered the
    ``chisurf.gui`` module reference with a Main instance. Every
    later call into ``cs.gui.widgets.*`` then raised
    ``AttributeError: 'Main' object has no attribute 'widgets'``.
    """
    # Pre-import to ensure the package attribute is set
    from chisurf.macros.core_data import reinitialize_application

    class _MockMain:
        def onCloseAllFits(self):
            pass

    # Save and restore cs.cs to avoid polluting subsequent tests
    saved_cs_cs = getattr(cs, "cs", None)
    try:
        # Run the full reinitialize sequence. Internal steps that need
        # a real Main window log a warning instead of crashing.
        reinitialize_application(main_window=_MockMain())

        # The critical assertion: cs.gui is still the module.
        assert cs.gui.__name__ == "chisurf.gui"
        assert cs.gui.widgets.__name__ == "chisurf.gui.widgets"
    finally:
        cs.cs = saved_cs_cs
