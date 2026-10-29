"""Guide 115: Excitation Windows, the setup editor's Auto-detect and Record's live check (headless emtk).

Uses the plugin's simulated PIE measurement (32 ps channels, 3125 per 100 ns, pulses at 2 and
52 ns) and a setup made for an SPC-130 (50 ps, prompt 0–2048, delayed 2048–4095), and writes
``docs/guides/figures/115_excitation_windows_{check,setup_editor,record}.png``. Read the PNGs
afterwards.

Run from the repository root::

    CHISURF_SETTINGS_DIR=$(mktemp -d) python docs/guides/screenshots/excitation_windows_shot.py
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from emtk_shot import FIG  # noqa: E402


def tool() -> None:
    """The Excitation Windows tool checking the SPC-130 setup against the demo."""
    from emtk.export import save_png

    from chisurf.plugins.core.excitation_windows.demo import make_demo, wrong_setup
    from chisurf.plugins.core.excitation_windows.gui.app import make_app

    app = make_app(setup=wrong_setup())
    app.setup_text = "Setup: SPC-130 setup (50 ps, prompt 0–2048, delayed 2048–4095)"
    app.review.set_measurement(str(make_demo(pathlib.Path(tempfile.mkdtemp()))))
    save_png(app, FIG / "115_excitation_windows_check.png", size=(860, 900), frames=4)


def setup_editor() -> None:
    """The setup editor's Auto-detect on the demo, the setup still holding the SPC-130 windows."""
    from emtk.export import save_png

    from chisurf.plugins.core.excitation_windows.demo import make_demo, wrong_setup
    from chisurf.plugins.core.setup_channel_definition.gui.app import make_app

    settings = wrong_setup()
    settings["tttr_reading"]["file_type"] = "Auto"
    app = make_app(settings=settings, autoload=False, open_last_used=False)
    app.page.read(str(make_demo(pathlib.Path(tempfile.mkdtemp()))))
    while app.page._future is not None:
        app.page.poll()
        time.sleep(0.05)
    app.model.data["tttr_reading"]["micro_time_resolution"] = 50.0  # as made on the SPC-130
    app.model.data["windows"] = {"prompt": [0, 2048], "delayed": [2048, 4095]}
    app.page.auto_detect_windows()
    save_png(app, FIG / "115_excitation_windows_setup_editor.png", size=(1200, 860), frames=4)


def record() -> None:
    """A simulated PIE run in Record under windows of another instrument: the warning."""
    from emtk.export import save_png

    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    from chisurf.plugins.core.acq.gui.record_settings import SETTINGS_SETUP

    m = RecordModel(output_dir=tempfile.mkdtemp(), realtime=False)
    m.load_example()
    m.duration_s = 4.0
    m.settings_setup = {"detectors": {"green": {"chs": [0]}, "red": {"chs": [1]}},
                        "windows": {"prompt": [2048, 3000], "delayed": [3000, 4000]}}
    m.settings_name, m.setup_address, m.preset = "SPC-130 setup", SETTINGS_SETUP, "pie"
    app = RecordApp(m)
    m.start()
    while m.running:
        m.poll(force=True)
        time.sleep(0.02)
    m.poll(force=True)
    save_png(app, FIG / "115_excitation_windows_record.png", size=(1500, 950), frames=4)


if __name__ == "__main__":
    tool()
    setup_editor()
    record()
