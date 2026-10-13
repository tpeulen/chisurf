"""Drive the emtk shell headlessly for the guide figures: data in, a fit added, a dock cropped.

``Shell`` starts the shell on a private in-process server (a fresh session, scratch settings), as the shell
tests do. ``add_curve`` puts a ``DataCurve`` into the session, ``load`` reads a file through the *Read data*
dock, ``add_fit`` presses *+ Analysis* with a model chosen, and ``crop_dock`` floats a dock into a box and
writes just that box to ``docs/guides/figures/``. Read every PNG afterwards.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import time

os.environ.setdefault("CHISURF_SETTINGS_DIR", tempfile.mkdtemp(prefix="chisurf_shell_shots_"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

REPO = pathlib.Path(__file__).resolve().parents[3]
FIG = REPO / "docs" / "guides" / "figures"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class Shell:
    """An emtk shell with its own session, and the helpers the guide generators share."""

    def __init__(self, size=(1500, 950)) -> None:
        from emtk.testing import Driver

        from chisurf.emtk.main_app import EmtkShellApp
        from chisurf.emtk.session import start_session
        from chisurf.server.session import SessionState

        self.state = SessionState()
        self.app = EmtkShellApp()  # the real plugin catalogue and loader, as make_app builds it
        self.app.data.adopt(start_session(state=self.state))
        self.data = self.app.data
        self.driver = Driver(self.app, size)
        self.size = size
        # The figures float a dock into a box anywhere in the window to crop it; the workspace
        # would keep it inside the centre. A figure of the workspace itself turns this back on.
        self.app.docks.confine = False
        self.driver.frame(2)

    # -- waiting --------------------------------------------------------------------------
    def idle(self) -> bool:
        """No worker call is running and no dock is waiting to refresh."""
        return not self.data.busy and not self.data._dirty

    def settle(self, predicate, what: str, timeout: float = 240.0) -> None:
        """Draw frames until *predicate* holds (a worker call landed)."""
        end = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > end:
                raise TimeoutError(f"{what}: {self.data.status}")
            self.driver.frame(1)
            time.sleep(0.02)
        self.driver.frame(2)

    def frames(self, n: int = 3) -> None:
        """Draw *n* frames."""
        self.driver.frame(n)

    # -- data and fits --------------------------------------------------------------------
    def add_curve(self, curve) -> dict:
        """Put *curve* (a ``DataCurve``) into the session's datasets and return its row."""
        count = len(self.data.datasets.datasets)
        self.state.add_dataset(curve)
        self.data._dirty |= {"datasets"}
        self.settle(lambda: self.idle() and len(self.data.datasets.datasets) > count, "the dataset")
        return self.data.datasets.datasets[-1]

    def load(self, path, experiment: str, setup: str) -> dict:
        """Read *path* through the *Read data* dock."""
        from chisurf.emtk.fit_docks import READ_KEY

        self.app.docks.focus(READ_KEY)
        self.driver.frame(2)
        read = self.data.read
        read.experiment = experiment
        read.experiment_changed(experiment)
        read.setup = setup
        read.path = str(path)
        count = len(self.data.datasets.datasets)
        self.driver.click("read.load")
        self.settle(lambda: self.idle() and len(self.data.datasets.datasets) > count, str(path))
        return self.data.datasets.datasets[-1]

    def add_fit(self, model: str, dataset: dict | None = None) -> str:
        """Press *+ Analysis* with *model* for *dataset* (the selected one by default); the new fit's uid."""
        from chisurf.emtk.fit_docks import DATASETS_KEY

        self.app.docks.focus(DATASETS_KEY)
        self.driver.frame(2)
        if dataset is not None:
            self.data.datasets.select_dataset(dataset)
        self.data.datasets.model = model
        count = len(self.data.datasets.fits)
        self.driver.click("datasets.add_fit")
        def landed() -> bool:
            if "failed" in str(self.data.status):
                raise RuntimeError(str(self.data.status))
            return self.idle() and len(self.data.datasets.fits) > count

        self.settle(landed, f"the {model} fit")
        self.settle(lambda: self.data.windows and self.data.analysis.info, "the fit window")
        return self.data.datasets.fits[-1]["uid"]

    def fit(self):
        """The newest fit of the session (the live object, for setting up a state the figure shows)."""
        return self.state.fits[-1]

    def refresh(self) -> None:
        """Make every dock re-read the session after the fit object was changed directly."""
        self.data._dirty |= {"datasets", "fits", "current"}
        self.settle(self.idle, "the refresh")

    # -- pictures -------------------------------------------------------------------------
    def shot(self, name: str, crop=None) -> pathlib.Path:
        """Write the whole window (or the pixel box *crop* = (x0, y0, x1, y1)) to ``FIG / name``."""
        from PIL import Image

        path = FIG / name
        self.driver.frame(3)
        self.driver.screenshot(path)
        if crop is not None:
            Image.open(path).convert("RGB").crop(tuple(int(v) for v in crop)).save(path)
        print("wrote", name, flush=True)
        return path

    def crop_dock(self, key: str, name: str, box=(0, 0, 640, 900), tab: str | None = None) -> pathlib.Path:
        """Float the dock *key* into *box* (x, y, w, h), draw, and write only that box to ``FIG / name``."""
        docks = self.app.docks
        docks.undock(key, tuple(float(v) for v in box))
        docks.focus(key)
        if tab:
            docks.focus(tab)
        self.driver.frame(4)
        x, y, w, h = box
        return self.shot(name, crop=(x, y, x + w, y + h))

    def close(self) -> None:
        """Shut the shell and its server down."""
        self.app.close()
