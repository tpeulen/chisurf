"""The emtk shell in the states the manual's figures show (IBH lifetime fit, fit pages, dock crops).

Builds on :class:`shell_emtk.Shell` (a shell on a private in-process server, scratch settings) and adds
what the manual pages share: the IBH sample decay and its measured prompt loaded through the *Read data*
dock, a lifetime fit with the prompt picked as IRF, a scoring range and a run, and the helpers that bring
a fit page or a dock forward and write the window to ``docs/manual/figures/``. Read every PNG afterwards.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

os.environ.setdefault("CHISURF_SETTINGS_DIR", tempfile.mkdtemp(prefix="chisurf_manual_shots_"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

REPO = pathlib.Path(__file__).resolve().parents[3]
OUT = REPO / "docs" / "manual" / "figures"
IBH = REPO / "test" / "data" / "tcspc" / "ibh_sample"
for path in (str(REPO), str(pathlib.Path(__file__).parent)):
    if path not in sys.path:
        sys.path.insert(0, path)

from shell_emtk import Shell  # noqa: E402

#: The IBH decay's scoring range (channels): from the rise to before the tail's noise floor.
FIT_RANGE = (522, 3793)
#: The IBH card's channel width in ns.
IBH_DT = 0.0141


class ManualShell(Shell):
    """A :class:`Shell` with the manual's helpers."""

    # -- data and fits --------------------------------------------------------------------
    def load_ibh(self, name: str) -> dict:
        """Read an IBH sample file (``Prompt.txt``, ``Decay_577D.txt``, ...) as TCSPC text data.

        The reader's *dt* is the channel width of the IBH card (0.0141 ns), so the lifetimes come out in ns.
        """
        from chisurf.emtk.fit_docks import READ_KEY

        self.app.docks.focus(READ_KEY)
        self.driver.frame(2)
        read = self.data.read
        read.experiment = "TCSPC"
        read.experiment_changed("TCSPC")
        read.setup = "TXT/CSV"
        read.reader().dt = IBH_DT
        return self.load(IBH / name, "TCSPC", "TXT/CSV")

    def click_editor(self, name: str) -> None:
        """Click the model editor control ``editor.<name>`` once its rectangle has settled."""
        key = f"editor.{name}"
        last = None
        for _ in range(10):
            self.driver.frame(1)
            rect = self.app.item_rects.get(key)
            if rect is not None and rect == last:
                break
            last = rect
        self.driver.click(key)

    def pick_curve(self, key: str, row: dict) -> None:
        """Press ``...`` of the curve picker *key* (``convolve.irf``, ...) and pick the dataset *row*."""
        self.click_editor(f"curve.{key}.pick")
        picker = self.data.dataset_picker
        picker.pick(next(i for i, r in enumerate(picker.rows) if r["uid"] == row["uid"]))
        self.settle(self.idle, f"{key} loaded")

    def show_analysis(self) -> None:
        """Bring the Analysis dock to the front."""
        from chisurf.emtk.fit_docks import ANALYSIS_KEY

        self.app.docks.focus(ANALYSIS_KEY)
        self.driver.frame(3)

    def ibh_fit(self, decay="Decay_577D.txt", model="Lifetime", free=(), run=True, lifetimes: int = 1) -> str:
        """A lifetime fit of an IBH decay with the prompt as IRF, scored over :data:`FIT_RANGE`; its uid.

        Loads ``Prompt.txt`` once and *decay* (each as the dataset of that name), adds a *model* fit,
        picks the prompt as IRF, frees the *free* parameters (by name), sets the range and
        runs the fit when *run*. *lifetimes* components are used (the *add* of the Lifetimes box):
        the FRET decay needs two, fitted with one the IRF shift wanders off to compensate.
        """
        rows = {r["name"]: r for r in self.data.datasets.datasets}
        prompt = rows.get("Prompt.txt") or self.load_ibh("Prompt.txt")
        data = rows.get(decay) or self.load_ibh(decay)
        uid = self.add_fit(model, data)
        self.show_analysis()
        self.pick_curve("convolve.irf", prompt)
        self.set_range(*FIT_RANGE)
        for _ in range(lifetimes - 1):  # the Lifetimes box's *add*, through the session like the button
            self.data.change_components("lifetimes", True)
            self.settle(self.idle, "the lifetime component")
        live = self.fit().model
        for parameter in live.parameters_all:
            if parameter.name in free:
                parameter.fixed = False
        self.refresh()
        if run:
            self.run_fit()
        return uid

    def set_range(self, first: int, last: int) -> None:
        """Type the scoring range into First / Last."""
        self.data.set_range(first, last)
        self.settle(self.idle, "the range")

    def run_fit(self) -> None:
        """Press **Fit** and wait for the verdict."""
        before = self.data.analysis.info.get("n_results", 0)
        self.driver.click("analysis.run_fit")
        self.settle(
            lambda: self.idle() and self.data.analysis.info.get("n_results", 0) > before,
            "the fit",
            timeout=600.0,
        )

    # -- pages ----------------------------------------------------------------------------
    def window(self):
        """The current fit's window."""
        return self.data.current_window()

    def page(self, name: str):
        """Bring the fit window's page *name* forward (a click on its tab) and return the page."""
        window = self.window()
        if name in window.names:
            # A narrow fit window elides its tab captions ("Chain di…"), so a click by caption
            # misses; select the page by its index as the tab click does.
            window.surface.set_current(window.names.index(name))
        else:
            self.driver.click(name)
        self.driver.frame(4)
        return window.current_page()

    def settings(self) -> None:
        """Bring the Plot settings dock to the front."""
        from chisurf.emtk.fit_docks import PLOT_KEY

        self.app.docks.focus(PLOT_KEY)
        self.driver.frame(4)

    def below_ribbon(self, right: float, bottom: float) -> tuple[int, int, int, int]:
        """The crop box ``(0, top, right, bottom)`` that leaves out the menu bar and the ribbon.

        *top* is measured from the shell now (the menu bar's height plus the ribbon's, which
        changes with its group captions, its fold and *Menu Switch*), never a constant: a fixed
        top cut off the docks' tab row once the ribbon grew.
        """
        from chisurf.emtk.main_app import MENU_BAR

        self.driver.frame(2)
        app = self.app
        top = MENU_BAR + (app.ribbon.height() if getattr(app, "_ribbon_enabled", True) else 0.0)
        return (0, int(round(top)), int(right), int(bottom))

    def save(self, name: str, crop=None) -> pathlib.Path:
        """Write the window (or the pixel box *crop*) to ``docs/manual/figures/<name>``."""
        from PIL import Image

        OUT.mkdir(parents=True, exist_ok=True)
        path = OUT / name
        self.driver.frame(3)
        self.driver.screenshot(path)
        if crop is not None:
            Image.open(path).convert("RGB").crop(tuple(int(v) for v in crop)).save(path)
        print("wrote", name, flush=True)
        return path

    # -- docks ----------------------------------------------------------------------------
    def folds(self, *open_titles: str, fit: bool = True) -> None:
        """Open the Analysis dock's boxes *open_titles* and fold the other editor boxes (and *Fit* unless *fit*)."""
        editor = self.data.editor
        for title in ("Lifetimes", "Anisotropy", "Convolution", "Generic", "Corrections", "Equation", "Equation parameters"):
            editor.form.folds[title] = title in open_titles
        self.data.forms["analysis"].folds["Fit"] = bool(fit)
        self.driver.frame(3)

    def crop_dock(self, key: str, name: str, box=(0, 0, 560, 600), skip: int = 0) -> pathlib.Path:
        """Float the dock *key* into *box* (x, y, w, h), draw, and write only that box to the manual figures.

        *skip* pixels of the box's top are left out (the dock's header and what is above a box).
        """
        docks = self.app.docks
        docks.undock(key, tuple(float(v) for v in box))
        docks.focus(key)
        self.driver.hover((1495.0, 5.0))  # no tooltip over the figure
        self.driver.frame(5)
        x, y, w, h = box
        return self.save(name, crop=(x, y + skip, x + w, y + h))

    def stack(self, name: str, images, labels=None, vertical: bool = True, gap: int = 14) -> pathlib.Path:
        """Write the PNGs *images* (paths) one under (or beside) the other, each with a label, to ``name``."""
        from PIL import Image, ImageDraw, ImageFont

        tiles = [Image.open(p).convert("RGB") for p in images]
        pad = 32 if labels else 0
        if vertical:
            width = max(i.width for i in tiles)
            height = sum(i.height + pad for i in tiles) + gap * (len(tiles) - 1)
        else:
            width = sum(i.width for i in tiles) + gap * (len(tiles) - 1)
            height = max(i.height for i in tiles) + pad
        sheet = Image.new("RGB", (width, height), (24, 24, 28))
        draw = ImageDraw.Draw(sheet)
        try:
            font = ImageFont.load_default(size=20)
        except TypeError:  # an old Pillow has one size
            font = ImageFont.load_default()
        x = y = 0
        for index, tile in enumerate(tiles):
            if labels:
                draw.text((x + 6, y + 6), labels[index], fill=(235, 235, 235), font=font)
            sheet.paste(tile, (x, y + pad))
            if vertical:
                y += tile.height + pad + gap
            else:
                x += tile.width + gap
        path = OUT / name
        sheet.save(path)
        print("wrote", name, flush=True)
        return path
