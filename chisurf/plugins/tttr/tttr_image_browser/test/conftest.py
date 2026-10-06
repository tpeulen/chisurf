"""Fixtures of the emtk tests: real CLSM photon files in a temporary folder, on temporary settings (no network)."""

import json
import pathlib
import shutil

import pytest

REPO = next(p for p in pathlib.Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
DATA = REPO / "test" / "data" / "clsm"

#: Detector setup of the tests: two detectors over the routing channels of the Leica files (SP8 has channel 1, SP5 0 to 2).
SETUP_DETECTORS = {
    "windows": {"all": [0, 4095]},
    "detectors": {
        "green": {
            "chs": [0, 1],
            "micro_time_ranges": [[0, 4095]],
            "g_factor": 1.0,
            "l1": 0.0,
            "l2": 0.0,
        },
        "red": {
            "chs": [2],
            "micro_time_ranges": [[0, 4095]],
            "g_factor": 1.0,
            "l1": 0.0,
            "l2": 0.0,
        },
    },
    "tttr_reading": {
        "file_type": "PTU",
        "macro_time_resolution": 50.0,
        "micro_time_resolution": 16.0,
        "micro_time_binning": 1,
        "effective_micro_time_resolution": 16.0,
        "excitation_period": 50.0,
    },
    "setup_name": "",
    "apply_lut": False,
    "polarization_resolved": True,
    "channel_luts": {},
    "channel_shifts": {},
}


def two_detector_setup() -> dict:
    """The setup of the tests with its window x detector cross product (what the setup page hands over)."""
    from chisurf.core.setup_channel_definition import ChannelDefinition

    return ChannelDefinition(json.loads(json.dumps(SETUP_DETECTORS))).get_settings()


@pytest.fixture
def hermetic(tmp_path, monkeypatch):
    """Settings, MMFDB and its database into a temporary folder; the user's own are never touched."""
    from chisurf.plugins.microscopy.imaging_emtk.testing import hermetic_env

    hermetic_env(tmp_path, monkeypatch)
    return tmp_path


@pytest.fixture(scope="session")
def photon_template(tmp_path_factory):
    """``imgs/Leica_SP8.ptu``, ``imgs/corrupt.ptu`` (empty), ``imgs/sub/Leica_SP5.ptu`` and a text file, mosaics cached.

    The caches of the default (auto-detect) reading and of the two-detector setup are built once here, so the
    per-test copies (``copytree`` keeps the modification times the cache keys include) do not reconstruct them.
    """
    for name in ("Leica_SP8.ptu", "Leica_SP5.ptu"):
        if not (DATA / name).is_file():
            pytest.fail(f"test data missing: {DATA / name}")
    root = tmp_path_factory.mktemp("photon_template") / "imgs"
    (root / "sub").mkdir(parents=True)
    shutil.copy2(DATA / "Leica_SP8.ptu", root / "Leica_SP8.ptu")
    shutil.copy2(DATA / "Leica_SP5.ptu", root / "sub" / "Leica_SP5.ptu")
    (root / "corrupt.ptu").write_bytes(b"")
    (root / "notes.txt").write_text("not a photon file")
    from chisurf.plugins.tttr.tttr_image_browser.core.image import load_image

    for path in (root / "Leica_SP8.ptu", root / "sub" / "Leica_SP5.ptu"):
        load_image(str(path), None, 512, str(root))
        load_image(str(path), two_detector_setup(), 512, str(root))
    return root


@pytest.fixture
def photon_folder(photon_template, tmp_path):
    """A private copy of the template folder (files, caches)."""
    target = tmp_path / "imgs"
    shutil.copytree(photon_template, target)
    return target
