"""Native PSF calculator: the optics form, the 3-D volume, a central slice and the export of the volume."""

from __future__ import annotations

import json
import pathlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from emtk import im, implot, implot3d
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget

from ..core import PSFModel
from .panel import PSFPanel

HERE = Path(__file__).parent
SPEC = json.loads((HERE / "psf_emtk.view.json").read_text(encoding="utf-8"))
#: Quiet period after the last edit before the volume is recomputed (the Qt tool's debounce), seconds.
DEBOUNCE = 0.25
#: The 3-D view draws at most this many voxels (the export keeps every one).
MAX_VOXELS = 6000
SETTINGS = ("na", "n_immersion", "wavelength_nm", "model", "polarization", "angle_deg", "nxy", "nz", "pixel_size_nm",
            "z_step_nm", "quality", "threshold", "gamma", "colormap", "show_polarization")


class PSFApp(TourTarget, ImApp):
    """The PSF window: parameters left, the volume and a central slice right."""

    def __init__(self, model=None):
        self.model = model or PSFModel()
        self.item_rects: dict = {}
        self.busy = False
        self.error = ""
        self.status = ""
        self.deadline = time.monotonic()
        self.slice_plane = "XY"
        self.dialog = None
        self.dialog_suffix = ".npy"
        self.file_window = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="psf")
        self._lock = threading.Lock()
        self._result = None
        self._context = None
        self.help_window = EmTkHelpWindow(title="PSF calculator - Help", resource=HERE / "help.md", owner=self,
                                          on_start_guide=lambda: self.tour.start())
        self.tour = EmTkGuidedTour(steps=HERE / "guide.json", get_target_rect=lambda k: self.item_rects.get(k), owner=self,
                                   wait_for_controls=True)
        self.panel = PSFPanel(self)
        self.forms = {n: FormState(on_used=self.tour.notify_used) for n in ("toolbar", "parameters", "result", "slice")}
        self.docks = DockManager(Split("h", 0.38, Region("controls"), Split("v", 0.62, Region("volume"), Region("slice"))), name="psf")
        self.docks.add_window("controls", "Parameters", self._draw_controls, dock="controls", closable=False)
        self.docks.add_window("volume", "3-D PSF", self._draw_volume, dock="volume", closable=False)
        self.docks.add_window("slice", "Orthogonal Slice", self._draw_slice, dock="slice", closable=False)
        self.native_layouts = {"main": self.docks}
        super().__init__(self._render, continuous=False)

    # -- computing ------------------------------------------------------------------------------------------- #
    def schedule(self) -> None:
        """Recompute once the edits stop."""
        self.error = ""
        self.deadline = time.monotonic() + DEBOUNCE

    def compute(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.error = ""
        import copy

        snapshot = copy.copy(self.model)
        try:
            self._context = im.get_current_context()
        except RuntimeError:
            self._context = None

        def run():
            try:
                snapshot.compute()
                result = (snapshot, "")
            except Exception as exc:  # noqa: BLE001 - shown on the status line
                result = (None, str(exc))
            with self._lock:
                self._result = result
            if self._context is not None:
                self._context.request_frame()

        self._executor.submit(run)

    def _poll(self) -> None:
        with self._lock:
            result, self._result = self._result, None
        if result is None:
            return
        snapshot, self.error = result
        self.busy = False
        if snapshot is not None and snapshot._compute_key() == self.model._compute_key():
            self.model._volume = snapshot.volume
            self.model._key = snapshot._key
        if self.error:
            self.error = "Error: " + self.error

    def animating(self) -> bool:
        """Frames while the volume is being computed or an edit waits for its debounce."""
        if self.busy or (self.model.is_stale and not self.error and self.model.volume is None) or (self.model.is_stale and not self.error):
            return True
        return super().animating()

    # -- windows ------------------------------------------------------------------------------------------- #
    def _form(self, name: str, spec: dict) -> None:
        state = self.forms[name]
        state.rects.clear()
        draw_form(spec, self.panel, state, titles=False)
        self.item_rects.update(state.rects)

    def _draw_controls(self, box) -> None:
        self._form("toolbar", SPEC["toolbar"])
        if "export_npy" in self.item_rects:
            self.item_rects["Export"] = self.item_rects["export_npy"]  # the guide's name for the export buttons
        # One line is always reserved, so the fields below do not jump when a computation starts or ends.
        if self.busy:
            im.text_disabled("Computing the volume ...")
        elif self.error:
            im.push_style_color(im_Col.TEXT, (255, 115, 100, 255))
            im.text_wrapped(self.error)
            im.pop_style_color(1)
        elif self.status:
            im.text_wrapped(self.status)
        else:
            im.text_disabled(" ")
        self._form("parameters", SPEC["parameters"])
        if self.model.volume is None:
            im.text_wrapped("Not computed yet." if not self.error else "No volume: see the message above.")
        else:
            self._form("result", SPEC["result"])
        self.remember("parameters", tuple(box))

    def _draw_volume(self, box) -> None:
        volume = self.model.volume
        if volume is None:
            im.text_wrapped("Waiting for the first PSF calculation." if not self.error else "No volume to show.")
            return
        flags = implot3d.FLAGS_NO_LEGEND
        if implot3d.begin_plot("PSF volume", (-1, -1), flags):
            implot3d.setup_axes("x [nm]", "y [nm]", "z [nm]")
            model = self.model
            nz, ny, nx = volume.shape
            peak = max(float(volume.max()), 1e-30)
            z, y, x = np.nonzero(volume >= float(model.threshold) * peak)
            stride = max(1, (len(x) + MAX_VOXELS - 1) // MAX_VOXELS)
            x, y, z = x[::stride], y[::stride], z[::stride]
            intensity = (volume[z, y, x] / peak) ** model.gamma
            from matplotlib import colormaps

            cmap = colormaps[model.colormap]
            for k in range(12):
                mask = (intensity >= k / 12) & (intensity < (k + 1) / 12 if k < 11 else intensity <= 1)
                if mask.any():
                    spec = implot3d.Spec(marker_size=2, marker_fill_color=cmap((k + 0.5) / 12))
                    implot3d.plot_scatter(f"Intensity {k}##psf", (x[mask] - (nx - 1) / 2) * model.pixel_size_nm,
                                          (y[mask] - (ny - 1) / 2) * model.pixel_size_nm, (z[mask] - (nz - 1) / 2) * model.z_step_nm, spec=spec)
            if model.show_polarization and model.model == "vectorial":
                segments = model.polarization_segments()
                if segments is not None:
                    for i, segment in enumerate(segments):
                        a = np.asarray(segment)
                        implot3d.plot_line(f"Polarization {i}", (a[:, 0] - (nx - 1) / 2) * model.pixel_size_nm,
                                           (a[:, 1] - (ny - 1) / 2) * model.pixel_size_nm, (a[:, 2] - (nz - 1) / 2) * model.z_step_nm)
            implot3d.end_plot()
            im.set_item_tooltip("Drag to rotate the physical PSF volume. Threshold hides dim voxels; gamma changes their brightness. "
                                "The view draws up to 6,000 voxels; the export keeps every voxel.")
        self.remember("volume", tuple(box))

    def _draw_slice(self, box) -> None:
        self._form("slice", SPEC["slice"])
        volume = self.model.volume
        if volume is None:
            return
        nz, ny, nx = volume.shape
        px, dz = float(self.model.pixel_size_nm), float(self.model.z_step_nm)
        axis = self.slice_plane
        if axis == "XY":
            plane, (u, v), labels = volume[nz // 2], (nx * px, ny * px), ("x [nm]", "y [nm]")
        elif axis == "XZ":
            plane, (u, v), labels = volume[:, ny // 2, :], (nx * px, nz * dz), ("x [nm]", "z [nm]")
        else:
            plane, (u, v), labels = volume[:, :, nx // 2], (ny * px, nz * dz), ("y [nm]", "z [nm]")
        plane = np.asarray(plane)[::-1]  # the heatmap puts row 0 on top: flip so y and z grow upwards
        if implot.begin_plot(f"Central PSF slice##{axis}", (-1, -1), implot.FLAGS_EQUAL):
            implot.setup_axes(*labels)
            implot.setup_axes_limits(-u / 2, u / 2, -v / 2, v / 2, implot.COND_ONCE)  # frame the section once per plane
            implot.setup_legend(0, implot.LEGEND_FLAGS_NO_BUTTONS if hasattr(implot, "LEGEND_FLAGS_NO_BUTTONS") else 0)
            implot.plot_heatmap("Intensity##slice", plane.ravel(), *plane.shape, 0.0, float(volume.max()), label_fmt="",
                                bounds_min=(-u / 2, -v / 2), bounds_max=(u / 2, v / 2),
                                spec=implot.PlotSpec(flags=implot.ITEM_FLAGS_NO_LEGEND))
            implot.end_plot()
            im.set_item_tooltip("The central section of the full computed volume, without voxel subsampling.")
        self.remember("slice", tuple(box))

    # -- export ----------------------------------------------------------------------------------------------- #
    def begin_export(self, suffix: str) -> None:
        if self.model.volume is None:
            self.error = "Error: The PSF has not been computed yet -- wait for the view to fill in."
            return
        self.dialog_suffix = suffix
        title = f"Export PSF as {suffix}"
        filters = "NumPy array (*.npy)" if suffix == ".npy" else "TIFF stack (*.tif *.tiff)"
        self.dialog = FileDialog(title, mode="save", filename=self.model.export_basename() + suffix, filters=filters)
        self.file_window = DialogWindow(title, size=(560, 420), key=title)
        self.file_window.show()

    def _draw_dialog(self, box) -> None:
        if self.dialog is None:
            return
        close = self.file_window.begin(box)
        chosen = self.dialog.draw()
        self.file_window.end()
        if close or chosen is False:
            self.dialog = None
        elif chosen:
            path = pathlib.Path(chosen[0])
            self.dialog = None
            if not path.suffix:
                path = path.with_suffix(self.dialog_suffix)  # a bare name would give a file neither NumPy nor ImageJ opens
            try:
                written = self.model.save(path)
                self.status = f"Exported to {written}"
                self.error = ""
            except Exception as exc:  # noqa: BLE001
                self.error = f"Error: Export failed: {exc}"

    # -- one frame ------------------------------------------------------------------------------------------ #
    def _render(self) -> None:
        self._poll()
        if not self.busy and not self.error and self.model.is_stale and time.monotonic() >= self.deadline:
            self.compute()
        vp = im.get_main_viewport()
        box = (0.0, 0.0, float(vp.size[0]), float(vp.size[1]))
        self.docks.draw(box)
        self._draw_dialog(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    # -- persistence ----------------------------------------------------------------------------------------- #
    def export_settings(self) -> dict:
        data = {name: getattr(self.model, name) for name in SETTINGS}
        data["slice_plane"] = self.slice_plane
        return data

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`; unusable entries are ignored and numbers are clamped to the field's range."""
        if not isinstance(settings, dict):
            return
        fields = {s["attr"]: s for p in SPEC["parameters"]["sections"] for s in p["sections"] if "attr" in s}
        for name in SETTINGS:
            if name not in settings:
                continue
            value, current, spec = settings[name], getattr(self.model, name), fields.get(name, {})
            if isinstance(current, bool):
                if isinstance(value, bool):
                    setattr(self.model, name, value)
            elif isinstance(current, (int, float)):
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
                    continue
                lo, hi = spec.get("minimum"), spec.get("maximum")
                value = min(max(value, lo if lo is not None else value), hi if hi is not None else value)
                setattr(self.model, name, int(value) if isinstance(current, int) else float(value))
            elif isinstance(current, str) and isinstance(value, str) and value in (spec.get("options") or [value]):
                setattr(self.model, name, value)
        if settings.get("slice_plane") in ("XY", "XZ", "YZ"):
            self.slice_plane = settings["slice_plane"]
        self.schedule()

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


from emtk.im_core import Col as im_Col  # noqa: E402


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return PSFApp()
