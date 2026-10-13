"""Repeatable populated native-app screenshots for the acquisition port report."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
from emtk import testing

from chisurf.plugins.core.acq.gui.app import AcquisitionApp, AcquisitionNativeModel
from chisurf.plugins.core.acq.gui.setup_models import BHSetupModel
from chisurf.plugins.core.acq.tcspc_devices.simulation.core.algorithms import generate_spc132_uint32


class FakeCaptureDevice:
    """Small deterministic B&H-shaped source used only for screenshot evidence."""

    device_type = "BH_SPC"

    def __init__(self, words: np.ndarray) -> None:
        """Store fixture words and their next FIFO offset."""
        self.words = words
        self.offset = 0
        self.active_cards = [0]
        #: setup-card writes by (module, parameter id)
        self.parameters: dict[tuple[int, int], float] = {}

    def initialize(self) -> bool:
        """Report deterministic successful initialization."""
        return True

    def start_measurement(self) -> bool:
        """Report deterministic successful FIFO start."""
        return True

    def read_fifo(self, maximum: int) -> np.ndarray:
        """Return the next bounded encoded FIFO chunk."""
        start = self.offset
        self.offset = min(len(self.words), start + maximum)
        return self.words[start : self.offset]

    def stop_measurement(self) -> bool:
        """Accept a screenshot-run stop request."""
        return True

    def close(self) -> None:
        """Close no external resource."""

    def detect_cards(self, simulation=False):
        """Return deterministic setup-card inventory without hardware access."""
        return [{"module_number": 0, "status": "Initialized fake", "active": True}]

    def set_active_cards(self, cards) -> None:
        """Record selected cards for the setup-card capture."""
        self.active_cards = list(cards)

    def get_parameter(self, module, parameter):
        """Return a valid retained parameter value for the native setup card."""
        defaults = {9: 1, 13: 6, 18: 1, 19: 1, 25: 1, 27: 1, 41: 1}
        return self.parameters.get((module, parameter), defaults.get(parameter, 1.0))

    def set_parameter(self, module, parameter, value) -> None:
        """Store deterministic setup-card writes without contacting a device."""
        self.parameters[module, parameter] = value


def capture(out: Path) -> list[Path]:
    """Run the deterministic app and write populated 1200×800 and 800×600 PNGs."""
    out.mkdir(parents=True, exist_ok=True)
    app = AcquisitionApp()
    try:
        app.model.photon_limit = 256
        app.model.start()
        deadline = time.monotonic() + 30.0
        while app.model.running and time.monotonic() < deadline:
            from emtk.testing import RecordingPainter

            app.draw(RecordingPainter(), 0, 0, 1200, 800)
            time.sleep(0.01)
        if app.model.running:
            raise TimeoutError("deterministic simulator did not finish")
        app.model.poll()
        paths = []
        for width, height in ((1200, 800), (800, 600)):
            painter = testing.PixelPainter(width, height)
            for _ in range(3):
                app.draw(painter, 0, 0, width, height)
            path = out / f"after_populated_{width}x{height}.png"
            path.write_bytes(testing.png_encode(painter.width, painter.height, painter.px))
            paths.append(path)
        return paths
    finally:
        app.close()


def capture_fake_device(out: Path) -> list[Path]:
    """Capture a populated injected-device session at both required resolutions."""
    params = AcquisitionNativeModel().simulation_params()
    params["N_ph_max"] = 256
    fake = FakeCaptureDevice(generate_spc132_uint32(params))
    app = AcquisitionApp(AcquisitionNativeModel(device_factory=lambda _kind: fake))
    try:
        app.model.device_type = "BH_SPC"
        assert app.model.initialize_device()
        assert app.model.start()
        deadline = time.monotonic() + 30.0
        while app.model.running and time.monotonic() < deadline:
            app.draw(testing.RecordingPainter(), 0, 0, 1200, 800)
            time.sleep(0.01)
        if app.model.running:
            raise TimeoutError("fake device did not finish")
        app.model.poll()
        paths = []
        for width, height in ((1200, 800), (800, 600)):
            painter = testing.PixelPainter(width, height)
            for _ in range(3):
                app.draw(painter, 0, 0, width, height)
            path = out / f"after_fake_device_{width}x{height}.png"
            path.write_bytes(testing.png_encode(painter.width, painter.height, painter.px))
            paths.append(path)
        return paths
    finally:
        app.close()


def capture_setup_cards(out: Path) -> list[Path]:
    """Capture populated native BH, simulator, and PicoQuant configuration cards."""
    fake = FakeCaptureDevice(np.array([], dtype=np.uint32))
    app = AcquisitionApp(AcquisitionNativeModel(device_factory=lambda _kind: fake))
    try:
        paths = []
        for kind, suffix, sizes in (
            ("BH_SPC", "bh_setup", ((1200, 800), (800, 600))),
            ("SIMULATION", "simulation_setup", ((1200, 800),)),
            ("PICOQUANT", "picoquant_setup", ((1200, 800),)),
            ("BRICKMIC", "brickmic_setup", ((1200, 800), (800, 600))),
        ):
            app.model.device_type, app.model.device = kind, fake if kind == "BH_SPC" else None
            app.model.open_device_setup()
            app.draw(testing.RecordingPainter(), 0, 0, 1200, 800)
            if kind == "BH_SPC":
                setup = app.setup_model
                assert isinstance(setup, BHSetupModel)
                setup.detect_cards()
                setup.read_parameters()
            for width, height in sizes:
                painter = testing.PixelPainter(width, height)
                for _ in range(3):
                    app.draw(painter, 0, 0, width, height)
                path = out / f"{suffix}_{width}x{height}.png"
                path.write_bytes(testing.png_encode(painter.width, painter.height, painter.px))
                paths.append(path)
            app._close_device_setup()
        return paths
    finally:
        app.close()


def main() -> None:
    """Parse the evidence output directory and perform the capture."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    for path in [
        *capture(args.out),
        *capture_fake_device(args.out),
        *capture_setup_cards(args.out),
    ]:
        print(path)


if __name__ == "__main__":
    main()
