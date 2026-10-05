"""Exercise portable project persistence in a fresh MMFDB-free interpreter."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


def test_lightpath_optional_database_boundary(tmp_path):
    """Pure optical helpers work offline; database operations report capability loss."""
    script = textwrap.dedent(
        r"""
        import importlib.abc
        import sys

        class NoMMFDB(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "mmfdb" or fullname.startswith("mmfdb."):
                    raise ModuleNotFoundError("MMFDB deliberately unavailable", name=fullname)
                return None

        sys.meta_path.insert(0, NoMMFDB())
        import numpy as np
        from chisurf.plugins.core.lightpath_simulator.core import workflow
        from chisurf.plugins.core.lightpath_simulator.backend.simulator import OpticalPathSimulator

        assert workflow.has_absorption(["excitation"])
        assert workflow.serialize_numpy(np.array([488.])) == [488.]
        assert workflow.resolve_db_path("explicit.sqlite") == "explicit.sqlite"
        simulator = OpticalPathSimulator(None)
        simulator.load_from_dict({"nodes": [{
            "id": "laser", "type": "light_source", "title": "Laser",
            "inputs": [], "outputs": [{"name": "Light", "is_output": True}],
            "config": {"source_mode": "manual", "manual_lines": "488:1.0"},
        }], "edges": []})
        assert "laser" in simulator.propagate()
        assert simulator.to_instrument_setting().lasers[0].wavelength_nm == 488.
        for operation, arguments in (
            (workflow.simulate_lightpath, ({},)),
            (workflow.save_lightpath, ({},)),
            (workflow.list_lightpaths, ()),
            (workflow.get_lightpath, ("missing",)),
            (workflow.get_probes_info, ()),
        ):
            try:
                operation(*arguments, db_path="explicit.sqlite")
            except RuntimeError as error:
                assert "MMFDB" in str(error) and "unavailable" in str(error)
            else:
                raise AssertionError("Database operation unexpectedly succeeded")
        assert not any(n == "mmfdb" or n.startswith("mmfdb.") for n in sys.modules)
        """
    )
    repo = Path(__file__).resolve().parents[2]
    env = dict(os.environ, CHISURF_SETTINGS_DIR=str(tmp_path / "settings"))
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_session_roundtrip_when_mmfdb_is_unavailable(tmp_path):
    """A clean process must save, reload and resave real curve data without MMFDB."""
    script = textwrap.dedent(
        r"""
        import importlib.abc
        import sys
        from pathlib import Path

        class NoMMFDB(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "mmfdb" or fullname.startswith("mmfdb."):
                    raise ModuleNotFoundError("MMFDB deliberately unavailable", name=fullname)
                return None

        for name in list(sys.modules):
            if name == "mmfdb" or name.startswith("mmfdb."):
                del sys.modules[name]
        sys.meta_path.insert(0, NoMMFDB())

        import numpy as np
        import chisurf as cs
        from chisurf.core.data import DataCurve, DataGroup
        from chisurf.core.project.storage import load_file, save_file, select_backend
        from chisurf.macros.core_fit import get_project_payload, load_project, save_project

        assert select_backend({"client": {"mode": "embedded"}}) == "file"
        a = DataCurve(x=np.arange(6.), y=np.arange(6.) + 3., name="a", unique_identifier="curve-a")
        b = DataCurve(x=np.arange(6.), y=np.arange(6.) + 8., name="b", unique_identifier="curve-b")
        a.meta_data["sample"] = "portable sample"
        cs.cs = None
        cs.imported_datasets[:] = [DataGroup([a, b], name="measurements", unique_identifier="group-a")]
        cs.fits[:] = []
        target = save_file(get_project_payload("portable"), Path(sys.argv[1]) / "portable")
        assert target.name == "portable.cs.pto"
        cs.imported_datasets[:] = []
        load_project(str(target))
        assert len(cs.imported_datasets) == 1
        restored = cs.imported_datasets[0]
        assert restored[0].unique_identifier == "curve-a"
        assert restored[0].meta_data["sample"] == "portable sample"
        np.testing.assert_array_equal(restored[1].y, b.y)
        changed = restored[1].y.copy()
        changed[2] = 123.
        restored[1].y = changed
        second = save_project(str(Path(sys.argv[1]) / "second.cs.pto"), "second")
        state = load_file(second)
        cs.imported_datasets[:] = []
        load_project(str(second))
        assert cs.imported_datasets[0][1].y[2] == 123.
        assert not any(name == "mmfdb" or name.startswith("mmfdb.") for name in sys.modules)
        print("MMFDB-free real-session save/reload/resave verified")
        """
    )
    repo = Path(__file__).resolve().parents[2]
    env = dict(
        os.environ, QT_QPA_PLATFORM="offscreen", CHISURF_SETTINGS_DIR=str(tmp_path / "settings")
    )
    paths = [
        repo / "modules/mmfdb/src",
        repo / "modules/chinet",
        repo / "modules/imp-tricks/src",
        repo / "modules/chimol",
        repo,
    ]
    env["PYTHONPATH"] = os.pathsep.join(map(str, paths))
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MMFDB-free real-session save/reload/resave verified" in result.stdout


def test_sample_picker_reports_unavailable_mmfdb(tmp_path):
    """Offline startup and sample creation expose a useful unavailable capability."""
    script = textwrap.dedent(
        r"""
        import importlib.abc
        import sys

        class NoMMFDB(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "mmfdb" or fullname.startswith("mmfdb."):
                    raise ModuleNotFoundError("MMFDB deliberately unavailable", name=fullname)
                return None

        sys.meta_path.insert(0, NoMMFDB())
        from qtpy import QtWidgets
        from chisurf.gui.widgets import sample_picker

        application = QtWidgets.QApplication([])
        picker = sample_picker.SamplePicker()
        assert picker.selected_sample_id() == ""
        messages = []
        sample_picker.dialogs.warning = lambda parent, title, message: messages.append(message)
        picker._on_new_sample()
        assert len(messages) == 1
        assert "MMFDB" in messages[0] and "unavailable" in messages[0]
        assert not any(n == "mmfdb" or n.startswith("mmfdb.") for n in sys.modules)
        picker.close()
        application.processEvents()
        """
    )
    repo = Path(__file__).resolve().parents[2]
    env = dict(
        os.environ, QT_QPA_PLATFORM="offscreen", CHISURF_SETTINGS_DIR=str(tmp_path / "settings")
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_forster_widget_reports_unavailable_mmfdb(tmp_path):
    """An optional spectra calculator imports and explains missing database capability."""
    script = textwrap.dedent(
        r"""
        import importlib.abc
        import sys

        class NoMMFDB(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "mmfdb" or fullname.startswith("mmfdb."):
                    raise ModuleNotFoundError("MMFDB deliberately unavailable", name=fullname)
                return None

        sys.meta_path.insert(0, NoMMFDB())
        from qtpy import QtWidgets
        from chisurf.gui.widgets.models.tcspc.forster_calculator_dialog import (
            ForsterCalculatorWidget,
        )

        application = QtWidgets.QApplication([])
        widget = ForsterCalculatorWidget()
        assert "MMFDB" in widget.result_label.text()
        assert "unavailable" in widget.result_label.text()
        assert not widget.apply_btn.isEnabled()
        assert not widget.donor_combo.isEnabled()
        assert not widget.acceptor_combo.isEnabled()
        assert not any(n == "mmfdb" or n.startswith("mmfdb.") for n in sys.modules)
        widget.close()
        application.processEvents()
        """
    )
    repo = Path(__file__).resolve().parents[2]
    env = dict(
        os.environ, QT_QPA_PLATFORM="offscreen", CHISURF_SETTINGS_DIR=str(tmp_path / "settings")
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_sample_and_forster_widgets_with_real_mmfdb(tmp_path):
    """Lazy imports retain actual sample persistence and spectra-based calculation."""
    script = textwrap.dedent(
        r"""
        import sys
        from pathlib import Path
        import numpy as np
        from qtpy import QtWidgets
        from mmfdb.repository import MFDatabase
        from mmfdb.samples.sample_manager import create_sample, get_sample
        from chisurf.gui.widgets.sample_picker import SamplePicker, _SampleDefinitionDialog
        from chisurf.gui.widgets.models.tcspc.forster_calculator_dialog import (
            ForsterCalculatorWidget,
        )
        from chisurf.core.fluorescence.fret.forster import forster_radius_from_spectra

        application = QtWidgets.QApplication([])
        with MFDatabase(str(Path(sys.argv[1]) / "spectra.sqlite")) as db:
            definition_dialog = _SampleDefinitionDialog(db)
            definition_dialog.name_edit.setText("Real offline-lane sample")
            definition_dialog.entity_sequence_edit.setText("ACDE")
            definition_dialog.donor_edit.setText("Donor")
            definition_dialog.acceptor_edit.setText("Acceptor")
            definition_dialog.accept()
            assert definition_dialog.result() == QtWidgets.QDialog.Accepted
            definition = definition_dialog.definition
            assert definition.entities[0].sequence == "ACDE"
            assert len(definition.fret_pairs) == 1
            sample_id = create_sample(db, definition)
            assert get_sample(db, sample_id)["name"] == "Real offline-lane sample"
            picker = SamplePicker(db)
            picker.set_selected(sample_id)
            assert picker.selected_sample_id() == sample_id
            picker.refresh()
            picker.set_selected(sample_id)
            assert picker.selected_sample_id() == sample_id

            type_id = db.conn.execute(
                "INSERT INTO probe_types (type_name, display_name) VALUES (?, ?)",
                ("test-spectra", "Test spectra"),
            ).lastrowid
            donor_id = db.add_probe("Spectral donor", type_id, category="organic_dye")
            acceptor_id = db.add_probe("Spectral acceptor", type_id, category="organic_dye")
            wavelengths = np.linspace(450., 700., 101)
            emission = np.exp(-((wavelengths - 535.) / 30.) ** 2)
            absorption = np.exp(-((wavelengths - 555.) / 35.) ** 2)
            db.add_spectrum(donor_id, "emission", wavelengths, emission)
            db.add_spectrum(acceptor_id, "absorption", wavelengths, absorption)
            db.add_optical_property(donor_id, "qy", "0.72")
            db.add_optical_property(acceptor_id, "ext_coeff", "95000")
            db.conn.commit()

        calculator = ForsterCalculatorWidget()
        calculator.donor_combo.setCurrentIndex(calculator.donor_combo.findData(donor_id))
        calculator.acceptor_combo.setCurrentIndex(calculator.acceptor_combo.findData(acceptor_id))
        assert calculator._model.donor_qy == 0.72
        assert calculator._model.acceptor_emax == 95000.
        calculator._debounce.stop()
        calculator._compute()
        grid = np.linspace(450., 700., 1000)
        expected, _ = forster_radius_from_spectra(
            grid, np.interp(grid, wavelengths, emission),
            np.interp(grid, wavelengths, absorption / absorption.max() * 95000.),
            donor_quantum_yield=0.72, kappa2=2./3., refractive_index=1.33,
        )
        np.testing.assert_allclose(calculator._last_r0, expected, rtol=1e-12)
        assert calculator.apply_btn.isEnabled()
        calculator.close()
        picker.close()
        definition_dialog.close()
        application.processEvents()
        """
    )
    repo = Path(__file__).resolve().parents[2]
    env = dict(
        os.environ,
        QT_QPA_PLATFORM="offscreen",
        CHISURF_SETTINGS_DIR=str(tmp_path / "settings"),
        MMFDB_SETTINGS_DIR=str(tmp_path / "mmfdb"),
        MMFDB_DATABASE_PATH=str(tmp_path / "spectra.sqlite"),
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_gui_startup_and_file_roundtrip_without_mmfdb(tmp_path):
    """Exercise the real main window, not just a cached file codec."""
    script = textwrap.dedent(
        r"""
        import importlib.abc
        import sys
        from pathlib import Path

        class NoMMFDB(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "mmfdb" or fullname.startswith("mmfdb."):
                    raise ModuleNotFoundError("MMFDB deliberately unavailable", name=fullname)
                return None

        for name in list(sys.modules):
            if name == "mmfdb" or name.startswith("mmfdb."):
                del sys.modules[name]
        sys.meta_path.insert(0, NoMMFDB())

        import numpy as np
        import chisurf as cs
        import chisurf.gui as gui
        from chisurf.gui.main import Main
        from chisurf.macros.core_fit import load_project

        application = gui.QtWidgets.QApplication.instance() or gui.QtWidgets.QApplication([])
        cs.console = gui.widgets.ipython.QIPythonWidget()
        cs.console.history_widget = None
        main = Main()
        main._save_window_state = lambda: None
        main.resize(1500, 950)
        cs.cs = main
        main.init_setups()
        main.define_actions()
        main.arrange_widgets()
        main.current_experiment = "TCSPC"
        main._refresh_experiment_ui()
        main.show()
        application.processEvents()
        reader = main.current_experiment.readers[0]
        from chisurf.core.experiments.tcspc import TCSPCReader
        assert type(reader) is TCSPCReader
        reader.dt = 0.048
        reader.rep_rate = 80.
        reader.skiprows = 9
        reader.use_header = False
        reader.rebin = (1, 1)
        source = Path("test/data/tcspc/ibh_sample/Decay_577D.txt")
        curve = reader.get_data(filename=str(source))[0]
        curve.unique_identifier = "gui-offline"
        curve.name = source.name
        raw = np.loadtxt(source, skiprows=9)
        np.testing.assert_array_equal(curve.y, raw[:, 1])
        np.testing.assert_allclose(curve.x, raw[:, 0] * reader.dt, rtol=1e-14)
        assert np.count_nonzero(curve.y) > 100
        curve.meta_data["sample"] = "MMFDB-free TCSPC"
        cs.imported_datasets.append(curve)
        main.dataset_selector.update()
        main.dockWidgetDatasets.raise_()
        application.processEvents()
        image = Path(sys.argv[1]) / "mmfdb-free-main-loaded.png"
        assert main.grab().save(str(image))
        assert image.stat().st_size > 0
        assert main.isVisible()
        assert not any(n == "mmfdb" or n.startswith("mmfdb.") for n in sys.modules)
        target = Path(sys.argv[1]) / "gui-offline.cs.pto"
        gui.QtWidgets.QFileDialog.getSaveFileName = lambda *args, **kwargs: (str(target), "")
        assert main.onExportProject() is True
        assert target.is_file()
        print("MMFDB-free real GUI Save As verified", flush=True)
        load_project(str(target))
        restored = next(d for d in cs.imported_datasets if d.unique_identifier == "gui-offline")
        for field in ("x", "y", "ex", "ey"):
            np.testing.assert_array_equal(getattr(restored, field), getattr(curve, field))
        assert restored.meta_data["sample"] == "MMFDB-free TCSPC"
        assert type(restored.data_reader) is type(reader)
        assert restored.experiment.name == "TCSPC"
        assert restored.data_reader.dt == 0.048
        assert restored.data_reader.rep_rate == 80.
        assert restored.data_reader.skiprows == 9
        assert restored.data_reader.use_header is False
        assert tuple(restored.data_reader.rebin) == (1, 1)
        changed = restored.y.copy()
        changed[2] = 123.
        restored.y = changed
        assert main.onSaveProject() is True
        assert main._get_project_document().path == target
        load_project(str(target))
        resaved = next(d for d in cs.imported_datasets if d.unique_identifier == "gui-offline")
        np.testing.assert_array_equal(resaved.y, changed)
        assert resaved.data_reader.dt == 0.048
        assert not any(n == "mmfdb" or n.startswith("mmfdb.") for n in sys.modules)
        main.dataset_selector.update()
        main.dockWidgetDatasets.raise_()
        application.processEvents()
        assert main.isVisible()
        assert main.grab().save(str(Path(sys.argv[1]) / "mmfdb-free-main-resaved.png"))
        main._guard_project_transition = lambda: True
        main.close()
        application.processEvents()
        print("MMFDB-free real GUI startup and project roundtrip verified")
        """
    )
    repo = Path(__file__).resolve().parents[2]
    env = dict(
        os.environ, QT_QPA_PLATFORM="offscreen", CHISURF_SETTINGS_DIR=str(tmp_path / "settings")
    )
    paths = [
        repo / "modules/mmfdb/src",
        repo / "modules/chinet",
        repo / "modules/imp-tricks/src",
        repo / "modules/chimol",
        repo,
    ]
    env["PYTHONPATH"] = os.pathsep.join(map(str, paths))
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MMFDB-free real GUI startup and project roundtrip verified" in result.stdout
