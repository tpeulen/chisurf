"""Native PSF optics, 3-D volume, orthogonal slices and export."""

import copy
import json
import threading
import time
from pathlib import Path

import numpy as np
from emtk import im, implot, implot3d
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.calculator.native_form import fields

from ..core import PSFModel


class PSFApp(ImApp):
    def __init__(self, model=None):
        self.model = model or PSFModel()
        self.busy = False
        self.error = ""
        self.pending = []
        self.deadline = time.monotonic()
        self.dialog = None
        self.slice_axis = 0
        self.item_rects = {}
        self.spec = json.loads(
            Path(__file__).parents[1].joinpath("psf_calculator.view.json").read_text()
        )["sections"][0]["sections"][0]["sections"]
        self.help_window = EmTkHelpWindow(
            title="PSF calculator — Help", resource=Path(__file__).with_name("help.md"), owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).with_name("guide.json"),
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=self,
            wait_for_controls=True,
        )
        self.docks = DockManager(
            Split(
                "h", 0.35, Region("controls"), Split("v", 0.65, Region("volume"), Region("slice"))
            )
        )
        self.docks.add_window(
            "controls", "Parameters", self.controls, dock="controls", closable=False
        )
        self.docks.add_window("volume", "3-D PSF", self.volume, dock="volume", closable=False)
        self.docks.add_window("slice", "Orthogonal slice", self.slice, dock="slice", closable=False)
        super().__init__(self.render, continuous=True)

    def schedule(self):
        self.error = ""
        self.deadline = time.monotonic() + 0.25

    def compute(self):
        if self.busy:
            return
        self.busy = True
        self.error = ""
        snapshot = copy.copy(self.model)

        def run():
            try:
                snapshot.compute()
                self.pending.append((snapshot, ""))
            except Exception as exc:
                self.pending.append((None, str(exc)))

        threading.Thread(target=run, daemon=True).start()

    def controls(self, box):
        if im.button("Compute"):
            self.compute()
        im.set_item_tooltip("Compute the current optics in a background thread.")
        self.item_rects["compute"] = im.get_item_rect()
        im.same_line()
        if im.button("Export NPY"):
            self.tour.notify_used("Export")
            self.dialog = FileDialog(
                "Export PSF", mode="save", filename="psf.npy", filters="NumPy (*.npy)"
            )
        im.set_item_tooltip("Save the complete PSF volume at full numerical precision.")
        self.item_rects["Export"] = im.get_item_rect()
        if im.button("Export TIFF"):
            self.tour.notify_used("Export")
            self.dialog = FileDialog(
                "Export PSF", mode="save", filename="psf.tif", filters="TIFF (*.tif *.tiff)"
            )
        im.set_item_tooltip("Save an ImageJ TIFF stack with the physical voxel size.")
        im.same_line()
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip("Explain optical models, polarization and volume interpretation.")
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("Start a guided tour of PSF controls and export.")
        im.separator()
        fields(self.model, self.spec, self.schedule, self.item_rects, self.tour.notify_used)
        im.text_wrapped(self.model.summary_text())
        if self.busy:
            im.text_unformatted("Computing…")
        if self.error:
            im.text_wrapped(self.error)

    def volume(self, box):
        v = self.model.volume
        if v is None:
            im.text_unformatted("Waiting for the first PSF calculation.")
            return
        if implot3d.begin_plot("PSF volume", (-1, -1)):
            implot3d.setup_axes("x [nm]", "y [nm]", "z [nm]")
            nz, ny, nx = v.shape
            # Keep the interactive reference responsive; bins retain the opacity ramp.
            z, y, x = np.nonzero(v >= float(self.model.threshold) * float(v.max()))
            stride = max(1, (len(x) + 5999) // 6000)
            x, y, z = x[::stride], y[::stride], z[::stride]
            intensity = (v[z, y, x] / max(float(v.max()), 1e-30)) ** self.model.gamma
            from matplotlib import colormaps

            cmap = colormaps[self.model.colormap]
            for k in range(12):
                mask = (intensity >= k / 12) & (
                    intensity < (k + 1) / 12 if k < 11 else intensity <= 1
                )
                if mask.any():
                    colour = cmap((k + 0.5) / 12)
                    spec = implot3d.Spec(marker_size=2, marker_fill_color=colour)
                    implot3d.plot_scatter(
                        f"Intensity {k}##psf",
                        (x[mask] - (nx - 1) / 2) * self.model.pixel_size_nm,
                        (y[mask] - (ny - 1) / 2) * self.model.pixel_size_nm,
                        (z[mask] - (nz - 1) / 2) * self.model.z_step_nm,
                        spec=spec,
                    )
            if self.model.show_polarization:
                segments = self.model.polarization_segments()
                if segments is not None:
                    for i, segment in enumerate(segments):
                        a = np.asarray(segment)
                        implot3d.plot_line(
                            f"Polarization {i}",
                            (a[:, 0] - nx / 2) * self.model.pixel_size_nm,
                            (a[:, 1] - ny / 2) * self.model.pixel_size_nm,
                            (a[:, 2] - nz / 2) * self.model.z_step_nm,
                        )
            implot3d.end_plot()
            im.set_item_tooltip(
                "Drag to rotate the physical PSF volume. Threshold hides dim voxels; gamma changes their brightness. Rendering samples up to 6,000 voxels; export preserves every voxel."
            )

    def slice(self, box):
        _, self.slice_axis = im.combo("Slice plane", self.slice_axis, ["XY", "XZ", "YZ"])
        im.set_item_tooltip("Inspect a central orthogonal section through the PSF.")
        v = self.model.volume
        if v is None:
            return
        plane = (v[v.shape[0] // 2], v[:, v.shape[1] // 2, :], v[:, :, v.shape[2] // 2])[
            self.slice_axis
        ]
        if implot.begin_plot("Central PSF slice", (-1, -1)):
            implot.setup_axes("Pixel", "Pixel")
            implot.plot_heatmap(
                "Intensity", plane.ravel(), *plane.shape, 0, float(v.max()), label_fmt=""
            )
            implot.end_plot()
            im.set_item_tooltip(
                "Central slice of the full computed volume without voxel subsampling."
            )

    def render(self):
        if self.pending:
            snapshot, self.error = self.pending.pop()
            self.busy = False
            if snapshot is not None and snapshot._compute_key() == self.model._compute_key():
                self.model._volume = snapshot.volume
                self.model._key = snapshot._key
        if (
            not self.busy
            and not self.error
            and self.model.is_stale
            and time.monotonic() >= self.deadline
        ):
            self.compute()
        vp = im.get_main_viewport()
        self.docks.draw((0, 0, *vp.size))
        if self.dialog:
            if im.begin("Export PSF"):
                result = self.dialog.draw()
                if result:
                    try:
                        self.model.save(result[0])
                        self.dialog = None
                    except Exception as exc:
                        self.error = str(exc)
                elif result is False:
                    self.dialog = None
            im.end()
        if self.help_window.open:
            self.help_window.draw((0, 0, *vp.size))
        if self.tour.active:
            self.tour.draw(*vp.size)


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return PSFApp()
