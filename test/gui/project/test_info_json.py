import json
import pathlib
import shutil
import tempfile
from datetime import datetime

from chisurf.gui.widgets.wizard.tttr_photonfilter import WizardTTTRPhotonFilter
from chisurf.gui.widgets.wizard.tttr_photonfilter import (
    tttr_photon_filter as photon_filter_module,
)


def test_info_json_location(qapp, qtbot):
    temp_dir = tempfile.mkdtemp()

    try:
        test_folder = "burstwise_All 0.4000#30"
        test_folder_with_suffix = f"{test_folder}_0"

        original_folder_path = pathlib.Path(temp_dir) / test_folder
        suffixed_folder_path = pathlib.Path(temp_dir) / test_folder_with_suffix

        original_folder_path.mkdir(exist_ok=True)
        suffixed_folder_path.mkdir(exist_ok=True)

        windows = {}
        detectors = {}

        filter_widget = WizardTTTRPhotonFilter(windows=windows, detectors=detectors)
        qtbot.addWidget(filter_widget)

        filter_widget.lineEdit_2.setText(test_folder)

        mock_filename = str(pathlib.Path(temp_dir) / "test_file.ptu")
        filter_widget.settings['tttr_filenames'] = [mock_filename]

        original_dirs = filter_widget.original_directories
        parent_dirs = filter_widget.parent_directories

        assert original_dirs[0].name == test_folder
        assert parent_dirs[0].name.startswith(test_folder)
        assert "_" in parent_dirs[0].name

        info_dir = original_dirs[0] / 'info'
        info_dir.mkdir(exist_ok=True, parents=True)

        parameters = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "test_param": "test_value"
        }

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        params_filename = info_dir / f"photon_selection_parameters_{timestamp}.json"

        with open(params_filename, 'w') as f:
            json.dump(parameters, f, indent=4)

        assert params_filename.exists()
        assert params_filename.parent.parent.name == test_folder

    finally:
        shutil.rmtree(temp_dir)


def test_info_json_uppercase(qapp, qtbot, monkeypatch):
    temp_dir = tempfile.mkdtemp()

    try:
        test_folder = "burstwise_All 0.4000#30"

        original_folder_path = pathlib.Path(temp_dir) / test_folder
        original_folder_path.mkdir(exist_ok=True)

        windows = {}
        detectors = {}

        filter_widget = WizardTTTRPhotonFilter(windows=windows, detectors=detectors)
        qtbot.addWidget(filter_widget)

        filter_widget.lineEdit_2.setText(test_folder)

        mock_filename = str(pathlib.Path(temp_dir) / "test_file.ptu")
        filter_widget.settings['tttr_filenames'] = [mock_filename]

        mock_setup_name = "Test Setup"
        mock_setup_data = {
            "detectors": {
                "Detector1": {"chs": [0, 1, 2]},
                "Detector2": {"chs": [3, 4, 5]}
            },
            "windows": {
                "Window1": [0, 100],
                "Window2": [200, 300]
            },
            "tttr_reading": {
                "file_type": "PTU",
                "micro_time_binning": 8
            }
        }

        mock_setups = {
            "setups": {
                mock_setup_name: mock_setup_data
            },
            "last_used": mock_setup_name
        }

        # Patch the module-level function the page actually calls. Assigning
        # ``filter_widget.load_detector_setups`` did nothing but raise
        # ``AttributeError`` -- the page imports the function rather than
        # carrying it as an attribute -- so the test was reading the developer's
        # own detector-setups file instead of this fixture.
        monkeypatch.setattr(
            photon_filter_module, "load_detector_setups", lambda *a, **k: mock_setups
        )
        filter_widget.comboBox.currentText = lambda: mock_setup_name

        assert photon_filter_module.load_detector_setups() is mock_setups

        original_dirs = filter_widget.original_directories

        info_dir = original_dirs[0] / 'Info'
        info_dir.mkdir(exist_ok=True, parents=True)

        parameters = filter_widget.get_burst_selection_parameters()
        parameters["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        parameters["selected_setup"] = mock_setup_name

        setup_data = mock_setups["setups"][mock_setup_name]
        parameters["setup_info"] = setup_data

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        params_filename = info_dir / f"photon_selection_parameters_{timestamp}.json"

        with open(params_filename, 'w') as f:
            json.dump(parameters, f, indent=4)

        assert params_filename.exists()
        assert params_filename.parent.name == "Info"

        with open(params_filename, 'r') as f:
            saved_params = json.load(f)

        assert "setup_info" in saved_params
        assert "detectors" in saved_params["setup_info"]
        assert "windows" in saved_params["setup_info"]
        assert "tttr_reading" in saved_params["setup_info"]

    finally:
        shutil.rmtree(temp_dir)
