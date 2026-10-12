"""Guide figures drawn by the emtk shell around a fit: sampling settings, the MFD fit window.

    IMP_BFF_GPU=off python docs/guides/screenshots/guides_shell_tools.py [39 | 57 ...]

Read every PNG afterwards.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
os.chdir(pathlib.Path(__file__).resolve().parents[3])

import numpy as np  # noqa: E402
import shell_emtk as se  # noqa: E402


def _grab_39() -> None:
    """Fit controller (Sample, gear) beside the gear's sampling/fitting settings form."""
    from PIL import Image

    from chisurf.core.data import DataCurve

    shell = se.Shell(size=(1500, 900))
    rng = np.random.default_rng(0)
    x = np.linspace(1.0, 2.0, 96)
    y = 1.0 + 2.0 * x + 0.5 * x**2 + rng.normal(0.0, 0.02, x.size)
    curve = DataCurve(x=x, y=y, ey=np.full_like(y, 0.02), load_filename_on_init=False)
    curve.name = "quadratic.txt"
    row = shell.add_curve(curve)
    shell.add_fit("Parse-Model", row)
    fit = shell.fit()
    fit.model.func = "c+a*x+b*x**2"
    fit.model.find_parameters()
    fit.fit_range = 0, len(fit.model.y)
    fit.run()
    shell.refresh()
    controller = shell.shot("_39_controller.png", crop=(0, 535, 405, 665))
    shell.driver.click("analysis.settings")
    shell.frames(4)
    dialog = shell.shot("_39_dialog.png", crop=(470, 190, 1032, 484))
    left, right = Image.open(controller).convert("RGB"), Image.open(dialog).convert("RGB")
    sheet = Image.new("RGB", (left.width + right.width + 30, max(left.height, right.height) + 20),
                      left.getpixel((3, 3)))
    sheet.paste(left, (10, 10))
    sheet.paste(right, (left.width + 20, 10))
    sheet.save(se.FIG / "39_sampling_controls.png")
    controller.unlink()
    dialog.unlink()
    print("wrote 39_sampling_controls.png", flush=True)
    shell.close()


def _grab_57() -> None:
    """The simulated intermediate-exchange MFD folder loaded with an MFD 2D fit; the map and the marginals."""
    from chisurf.core.fluorescence.burst.simulate import rate_matrix_for, simulate_smfret
    from chisurf.emtk.fit_docks import ANALYSIS_KEY

    shell = se.Shell(size=(1700, 1250))
    folder = pathlib.Path(tempfile.mkdtemp(prefix="mfd57_data_"))
    sim = simulate_smfret(
        alex=False, polarized=True, efficiencies=(0.786, 0.152), donor_only=0.15,
        n_photons=360_000, irf_centre=1.2, irf_width=0.09,
        rate_matrix=rate_matrix_for("intermediate", mean_duration=2e-3),
    )
    folder = pathlib.Path(sim.write_folder(str(folder)))
    burs = sorted(folder.glob("**/*.bur"))
    row = shell.load(burs[0].parent if burs else folder, "MFD", "MFD (burst folder)")
    shell.add_fit("MFD 2D", row)
    shell.app.docks.focus(ANALYSIS_KEY)
    window = shell.data.windows[shell.data.current_uid]
    print("pages", window.names, flush=True)
    window.surface.set_current(window.names.index("MFD map"))
    shell.frames(6)
    shell.shot("57_mfd_fit_window.png")
    window.surface.set_current(window.names.index("MFD marginals"))
    shell.settle(lambda: shell.idle(), "marginals")
    shell.frames(8)
    shell.shot("57_mfd_marginals.png")
    shell.close()


def _grab_65() -> None:
    """The Acquisition fit window with the demo stream, after the stream has ended."""
    import time

    from chisurf.core.experiments import types as experiment_types
    from chisurf.core.models.acquisition import AcquisitionModel
    from chisurf.emtk.fit_docks import ANALYSIS_KEY
    from chisurf.plugins.core.acq import demo
    from chisurf.plugins.core.acq.dataset import MODEL_NAME, AcquisitionDataset
    from chisurf.plugins.core.acq.pipeline import PipelineConfig, record_type_for_device

    class _Device:
        device_type = "SIMULATION"

    shell = se.Shell(size=(1500, 950))
    params = demo.simulation_params()
    dataset = AcquisitionDataset(
        name="Acquisition demo", n_bins=params["N_tac_channels"], tac_dt_ns=params["tac_dt"]
    )
    experiment = experiment_types["tcspc"]
    if AcquisitionModel.name not in experiment.model_names:
        experiment.add_model_class(AcquisitionModel)
    dataset.experiment = experiment
    for window in range(len(dataset.live._config_channels)):
        setattr(dataset.live, f"decay_show{window}", window < int(params["N_channels"]))
    dataset.live.decay_log_y = True
    config = PipelineConfig(
        record_type=record_type_for_device(_Device()), n_microtime_bins=params["N_tac_channels"]
    )
    row = shell.add_curve(dataset)
    shell.add_fit(MODEL_NAME, row)
    fit = shell.fit()
    fit.name = MODEL_NAME

    class _Api:
        """What ``AcquisitionDataset.update_fit`` asks of the session: recompute the fit, redraw its pages."""

        @staticmethod
        def fit_update(fit_uid):
            fit.update()
            shell.data.windows[shell.data.current_uid].refresh()
            return {"ok": True}

    dataset.api, dataset.fit = _Api(), fit
    dataset.start_stream(demo.words(demo.make_demo()), config)
    end = time.monotonic() + 90
    while time.monotonic() < end:
        shell.driver.frame(1)
        time.sleep(0.05)
        if dataset.refresh():
            dataset.update_fit()
        if not dataset.streaming and dataset.snapshot is not None:
            break
    for _ in range(10):
        dataset.refresh()
        dataset.update_fit()
        shell.driver.frame(2)
    print("photons", dataset.snapshot["total_photons"], flush=True)
    shell.app.docks.focus(ANALYSIS_KEY)
    shell.frames(6)
    shell.shot("65_acquisition_fit_window.png")
    shell.close()


GRABS = {"39": _grab_39, "57": _grab_57, "65": _grab_65}

if __name__ == "__main__":
    for key in sys.argv[1:] or GRABS:
        GRABS[key]()
    os._exit(0)
