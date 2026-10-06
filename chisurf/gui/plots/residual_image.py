from __future__ import annotations

import json
import pathlib

import numpy as np

import chisurf as cs
import chisurf.core.fitting
from chisurf.core.roi import RectangleROI
from chisurf.gui import chiplot as cp
from chisurf.gui.plots import plotbase

#: Colormaps offered for the image; a diverging map first, for signed residuals.
COLORMAPS = ("RdBu", "bwr", "viridis", "plasma", "inferno", "magma", "cividis")


def _resolve_accessor(accessor):
    """Return a callable for an accessor that may be given as a string.

    A view spec names its accessor as ``"module:function"`` — it is JSON, so it
    cannot hold a callable. Nothing between the spec and this plot turned that
    string into a function, so the string was called directly, the ``TypeError``
    was swallowed, and every ``residual2d`` panel configured from a view spec
    rendered blank. Resolving it here fixes them all at once.

    Parameters
    ----------
    accessor : callable or str or None
        A callable, ``"package.module:function"``, or ``"package.module.function"``.

    Returns
    -------
    callable or None
    """
    if accessor is None or callable(accessor):
        return accessor
    text = str(accessor)
    module_name, _, attribute = (
        text.partition(":") if ":" in text else text.rpartition(".")[::2] + ("",)
    )
    if ":" not in text:
        module_name, _, attribute = text.rpartition(".")
    try:
        import importlib

        module = importlib.import_module(module_name)
        return getattr(module, attribute)
    except Exception as exc:  # pragma: no cover - reported, not hidden
        cs.logging.warning("cannot resolve the 2D residual accessor %r: %s", text, exc)
        return None


class Residual2DPlot(plotbase.Plot):
    """Generic 2D residual image plot using a model-provided accessor.

    The accessor is responsible for computing the 2D residual matrix and the
    corresponding x/y axes so this plot remains model-agnostic.

    Expected signature:

        accessor(fit_group: cs.core.fitting.fit.FitGroup, **kwargs)
            -> (image_2d, x_axis, y_axis)
    """

    name = "Residuals 2D"
    settings_view = "residual_image.settings.view.json"

    def __init__(
        self,
        fit: cs.core.fitting.fit.FitGroup,
        *args,
        accessor=None,
        accessor_kwargs: dict | None = None,
        sources: dict | None = None,
        frame_kw: str | None = None,
        max_frames_accessor=None,
        frame_label: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(fit=fit, *args, **kwargs)
        # Used by some fit widgets (e.g. RICS) to synchronize the 1D fit range
        # with a 2D selection: FitSubWindow connects ``regionChanged`` of any
        # page to the fit controller, as it does for LinePlot.
        self.regionChanged = plotbase.Hook()

        # The settings (the *Plot settings* dock draws them from the spec).
        self._vmin, self._vmax = -1.0, 1.0
        self._xmin = self._xmax = self._ymin = self._ymax = 0
        self._x_bounds: tuple[int, int] = (-int(1e9), int(1e9))
        self._y_bounds: tuple[int, int] = (-int(1e9), int(1e9))
        self._colormap = COLORMAPS[0]
        self._frame_index = 0
        self._n_frames = 0

        self._accessor = accessor
        self._accessor_kwargs = {} if accessor_kwargs is None else dict(accessor_kwargs)

        # Optional support for multiple named image sources (e.g. residual,
        # data, model, intensity). When provided, the plot controller exposes
        # a selector and this plot switches between the configured accessors.
        self._sources: dict[str, tuple[callable, dict]] | None = None
        self._current_source_key: str | None = None

        if sources:
            src_map: dict[str, tuple[callable, dict]] = {}
            for key, spec in sources.items():
                if isinstance(spec, tuple) and len(spec) == 2:
                    fn, kw = spec
                elif isinstance(spec, dict):
                    fn = spec.get("accessor")
                    kw = spec.get("accessor_kwargs", {})
                else:
                    continue
                if fn is None:
                    continue
                src_map[str(key)] = (fn, dict(kw or {}))
            if src_map:
                self._sources = src_map
                self._current_source_key = next(iter(src_map.keys()))
                fn, kw = src_map[self._current_source_key]
                self._accessor = fn
                self._accessor_kwargs = dict(kw or {})

        # Optional configuration for frame-aware accessors (image stacks).
        # If *frame_kw* is not None, the current frame index from the
        # controller will be injected into accessor_kwargs[frame_kw] before
        # calling the accessor, but only if that key already exists in the
        # kwargs for the current source.
        self._frame_kw = frame_kw
        self._max_frames_accessor = max_frames_accessor

        self._image: np.ndarray | None = None
        self._x: np.ndarray | None = None
        self._y: np.ndarray | None = None

        self._plot_widget = self.add_panel()
        self._plot_widget.set_aspect_locked(False)

        # The image handle is created on the first computed frame: chiplot's
        # ``image`` verb draws data, it does not reserve an empty item.
        self._image_item = None

        try:
            self._quality_text = self._plot_widget.text(
                "",
                (0, 0),
                color="#FF0",
                border="w",
                fill=(0, 0, 255, 100),
                anchor=(0, 0),
                draggable=True,
                anchored=True,
            )
        except Exception:
            self._quality_text = None

        self._quality_text_initialized = False

        # Optional rectangular ROI used to define a 2D selection that can be
        # mapped back to a 1D fit-range (flattened lag index), analogous to
        # the LinearRegionItem in LinePlot. Created lazily on first image.
        self._roi = None
        self._roi_sync_in_progress = False
        self._roi_initialized = False

        # The frame axis may be named by the caller: an image stack indexes
        # frames, a correlation carpet frame lags ("Frame lag Δ").
        spec = json.loads(
            pathlib.Path(__file__).with_name(self.settings_view).read_text(encoding="utf-8")
        )
        if frame_label:
            for section in spec["sections"]:
                for child in section.get("sections", ()):
                    if child.get("attr") == "frame_index":
                        child["label"] = str(frame_label)
        self._settings_spec = spec

        if self._max_frames_accessor is not None:
            try:
                n_frames = int(self._max_frames_accessor(self.fit))
            except Exception:
                n_frames = 0
            self.set_frame_range(n_frames)

    # ------------------------------------------------------------------
    # Settings (drawn in the *Plot settings* dock from the view spec)
    # ------------------------------------------------------------------

    @property
    def vmin(self) -> float:
        """Value at the low end of the colormap."""
        return self._vmin

    @vmin.setter
    def vmin(self, value: float) -> None:
        self._vmin = float(value)
        self.apply_levels_from_controller()

    @property
    def vmax(self) -> float:
        """Value at the high end of the colormap."""
        return self._vmax

    @vmax.setter
    def vmax(self, value: float) -> None:
        self._vmax = float(value)
        self.apply_levels_from_controller()

    def _range_setter(name):  # noqa: N805 - a property factory, not a method
        def getter(self) -> int:
            return getattr(self, "_" + name)

        def setter(self, value: int) -> None:
            setattr(self, "_" + name, int(value))
            self.apply_ranges_from_controller()

        return property(getter, setter, doc=f"The shown range's {name} (axis units).")

    xmin = _range_setter("xmin")
    xmax = _range_setter("xmax")
    ymin = _range_setter("ymin")
    ymax = _range_setter("ymax")
    del _range_setter

    def bounds(self, name: str):
        """Run-time limits of a settings field (emtk's form asks its model)."""
        if name in ("xmin", "xmax"):
            return self._x_bounds
        if name in ("ymin", "ymax"):
            return self._y_bounds
        if name == "frame_index":
            return (0, max(self._n_frames - 1, 0))
        return None

    def colormaps(self) -> list[str]:
        """The colormaps offered."""
        return list(COLORMAPS)

    @property
    def colormap(self) -> str:
        """The image's colormap."""
        return self._colormap

    @colormap.setter
    def colormap(self, value: str) -> None:
        self._colormap = str(value)
        self.apply_cmap_from_controller()

    @property
    def has_sources(self) -> bool:
        """Whether the model offers more than one image (a source selector)."""
        return bool(self._sources)

    def source_names(self) -> list[str]:
        """The image sources the model offers."""
        return list(self._sources or ())

    @property
    def image_source(self) -> str:
        """The shown image source."""
        return self._current_source_key or ""

    @image_source.setter
    def image_source(self, value: str) -> None:
        if self._sources is None or str(value) not in self._sources:
            return
        self._current_source_key = str(value)
        self.update()

    @property
    def has_frames(self) -> bool:
        """Whether the image is a stack (a frame selector)."""
        return self._n_frames > 1

    def set_frame_range(self, n_frames: int | None) -> None:
        """Set how many frames the stack has; the index is clamped into it."""
        self._n_frames = 0 if n_frames is None or n_frames <= 1 else int(n_frames)
        self._frame_index = min(max(self._frame_index, 0), max(self._n_frames - 1, 0))

    @property
    def frame_index(self) -> int:
        """The shown frame of an image stack."""
        return self._frame_index

    @frame_index.setter
    def frame_index(self, value: int) -> None:
        self._frame_index = min(max(int(value), 0), max(self._n_frames - 1, 0))
        if self._frame_kw is not None:
            self.update()

    def get_settings_state(self) -> dict:
        """The settings, for the project file."""
        return {
            "vmin": self._vmin,
            "vmax": self._vmax,
            "xmin": self._xmin,
            "xmax": self._xmax,
            "ymin": self._ymin,
            "ymax": self._ymax,
            "colormap": self._colormap,
            "image_source": self.image_source,
            "frame_index": self._frame_index,
        }

    def set_settings_state(self, state: dict) -> None:
        """Restore :meth:`get_settings_state`."""
        if not isinstance(state, dict):
            return
        for key in ("vmin", "vmax", "colormap", "xmin", "xmax", "ymin", "ymax"):
            if key in state:
                setattr(self, "_" + key, state[key])
        if state.get("frame_index") is not None:
            self._frame_index = int(state["frame_index"])
        if state.get("image_source"):
            self.image_source = state["image_source"]

    def _compute_image(self) -> None:
        if self._accessor is None:
            return
        # Refresh accessor / kwargs from currently selected source, if any.
        if self._sources is not None and self._current_source_key in self._sources:
            fn, kw = self._sources[self._current_source_key]
            self._accessor = fn
            self._accessor_kwargs = dict(kw or {})

        # Inject current frame index for frame-aware sources when requested.
        if (
            self._frame_kw
            and isinstance(self._accessor_kwargs, dict)
            and self._frame_kw in self._accessor_kwargs
        ):
            self._accessor_kwargs[self._frame_kw] = int(self._frame_index)

        # Update frame range dynamically from the accessor if configured.
        if self._max_frames_accessor is not None:
            try:
                n_frames = int(self._max_frames_accessor(self.fit))
            except Exception:
                n_frames = 0
            self.set_frame_range(n_frames)

        accessor = _resolve_accessor(self._accessor)
        if accessor is None:
            return
        try:
            img, x, y = accessor(self.fit, **self._accessor_kwargs)
        except Exception as exc:
            # Reported once rather than swallowed. A failing accessor used to leave
            # the panel simply *empty*, which reads as "this model has no 2D
            # residual" rather than as an error — and a view spec naming an
            # accessor that cannot be called is a mistake worth seeing.
            if not getattr(self, "_accessor_failed", False):
                self._accessor_failed = True
                cs.logging.warning("the 2D residual accessor %r failed: %s", self._accessor, exc)
            return

        if img is None:
            return
        arr = np.asarray(img, dtype=float)
        if arr.ndim != 2:
            return

        self._image = arr
        self._x = np.asarray(x) if x is not None else np.arange(arr.shape[1], dtype=float)
        self._y = np.asarray(y) if y is not None else np.arange(arr.shape[0], dtype=float)

        if self._image_item is None:
            # ``col-major`` keeps the pre-chiplot orientation: this plot drew on
            # a bare pyqtgraph ImageItem, whose default axis order is col-major.
            self._image_item = self._plot_widget.image(self._image, axis_order="col-major")
        else:
            self._image_item.set_image(self._image)

        # Place the image in *axis* coordinates. The accessor returns two axis
        # vectors and the view is ranged to them, but the image itself stayed at
        # pixel indices — so an accessor reporting real units (a proximity ratio
        # from 0 to 1, nanoseconds from 0 to 7) drew its 41x41 pixels off the side
        # of a view showing 0..1, and the panel came out blank. Every model that
        # supplies axis vectors was affected, not just one.
        try:
            if (
                self._x is not None
                and self._x.size > 1
                and self._y is not None
                and self._y.size > 1
            ):
                x0, x1 = float(self._x.min()), float(self._x.max())
                y0, y1 = float(self._y.min()), float(self._y.max())
                # The vectors are bin *centres*, so the image spans half a bin more
                # on each side; without that the outer bins are drawn half outside.
                dx = (x1 - x0) / max(self._x.size - 1, 1)
                dy = (y1 - y0) / max(self._y.size - 1, 1)
                self._image_item.set_rect(
                    x0 - 0.5 * dx,
                    y0 - 0.5 * dy,
                    (x1 - x0) + dx,
                    (y1 - y0) + dy,
                )
        except Exception:
            pass

        # The levels the image is drawn with are settled below, once the
        # controller has been given this frame's data-driven defaults.

        # Initialize ROI once to cover the full image in axis coordinates.
        if not getattr(self, "_roi_initialized", False):
            roi = self._ensure_roi()
            if roi is not None:
                try:
                    self._roi_sync_in_progress = True
                    xmin = float(self._x.min()) if self._x is not None and self._x.size > 0 else 0.0
                    xmax = (
                        float(self._x.max())
                        if self._x is not None and self._x.size > 0
                        else float(self._image.shape[1] - 1)
                    )
                    ymin = float(self._y.min()) if self._y is not None and self._y.size > 0 else 0.0
                    ymax = (
                        float(self._y.max())
                        if self._y is not None and self._y.size > 0
                        else float(self._image.shape[0] - 1)
                    )
                    roi.set_pos(xmin, ymin)
                    roi.set_size(xmax - xmin, ymax - ymin)
                finally:
                    self._roi_sync_in_progress = False
                self._roi_initialized = True

        finite = np.isfinite(self._image)
        if np.any(finite):
            # Choose a symmetric range around zero based on |residuals| to
            # visualize positive and negative deviations in a balanced way.
            abs_vals = np.abs(self._image[finite])
            try:
                level = float(np.percentile(abs_vals, 99.0))
            except Exception:
                level = float(abs_vals.max()) if abs_vals.size > 0 else 1.0
            if not np.isfinite(level) or level <= 0.0:
                level = 1.0
            vmin = -level
            vmax = level
        else:
            vmin, vmax = -1.0, 1.0

        self._set_initial_ranges(vmin, vmax)
        self.apply_levels_from_controller()
        self.apply_ranges_from_controller()
        self.apply_cmap_from_controller()

        try:
            fit_obj = getattr(self.fit, "selected_fit", self.fit)
            chi2r = float(getattr(fit_obj, "chi2r", float("nan")))
            dw = float(getattr(fit_obj, "durbin_watson", float("nan")))
            if self._quality_text is not None and np.isfinite(chi2r) and np.isfinite(dw):
                if not getattr(self, "_quality_text_initialized", False):
                    try:
                        if self._x is not None and self._x.size > 0:
                            xmin = float(self._x.min())
                            xmax = float(self._x.max())
                        else:
                            xmin = 0.0
                            xmax = float(self._image.shape[1] - 1)
                        if self._y is not None and self._y.size > 0:
                            ymin = float(self._y.min())
                            ymax = float(self._y.max())
                        else:
                            ymin = 0.0
                            ymax = float(self._image.shape[0] - 1)
                        x_pos = xmin + 0.7 * (xmax - xmin)
                        y_pos = ymin + 0.9 * (ymax - ymin)
                        self._quality_text.set_position(x_pos, y_pos)
                    except Exception:
                        pass
                    else:
                        self._quality_text_initialized = True
                # The label was created yellow; setting the text keeps that
                # colour, so the metrics no longer carry their own markup.
                self._quality_text.text = f"Χ²={chi2r:.4f}\nDW={dw:.4f}"
        except Exception:
            pass

    def _set_initial_ranges(self, vmin: float, vmax: float) -> None:
        """This frame's data-driven levels and the full axis ranges (and their limits)."""
        if self._x is not None and self._x.size > 0:
            x_min, x_max = sorted((int(np.nanmin(self._x)), int(np.nanmax(self._x))))
            self._x_bounds = (x_min, x_max)
            self._xmin, self._xmax = x_min, x_max
        if self._y is not None and self._y.size > 0:
            y_min, y_max = sorted((int(np.nanmin(self._y)), int(np.nanmax(self._y))))
            self._y_bounds = (y_min, y_max)
            self._ymin, self._ymax = y_min, y_max
        self._vmin, self._vmax = float(vmin), float(vmax)

    def auto_contrast(self) -> None:
        """Reset vmin/vmax to data-driven levels and apply them.

        For residual-like images (with both positive and negative values) a
        symmetric range around zero is chosen based on a high percentile of
        ``|image|``. For non-negative images the full [min, max] range is
        used. Spin boxes in the controller are updated accordingly.
        """
        if self._image is None:
            return

        import numpy as np

        finite = np.isfinite(self._image)
        if not np.any(finite):
            return

        img = self._image[finite]

        has_neg = bool(np.any(img < 0))
        has_pos = bool(np.any(img > 0))

        if has_neg and has_pos:
            # Likely a residual image: choose a symmetric window around zero
            # based on the 99th percentile of absolute values.
            try:
                level = float(np.percentile(np.abs(img), 99.0))
            except Exception:
                level = float(np.max(np.abs(img))) if img.size > 0 else 1.0
            if not np.isfinite(level) or level <= 0.0:
                level = 1.0
            vmin, vmax = -level, level
        else:
            # Purely non-negative or non-positive image: use full data range.
            try:
                vmin = float(img.min())
                vmax = float(img.max())
            except Exception:
                return
            if not (np.isfinite(vmin) and np.isfinite(vmax)) or vmax <= vmin:
                return

        self._vmin, self._vmax = vmin, vmax
        self.apply_levels_from_controller()

    def apply_levels_from_controller(self) -> None:
        if self._image is None or self._image_item is None:
            return
        vmin, vmax = self._vmin, self._vmax
        if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
            finite = np.isfinite(self._image)
            if not np.any(finite):
                return
            vmin = float(self._image[finite].min())
            vmax = float(self._image[finite].max())
        self._image_item.set_levels(vmin, vmax)

    def apply_ranges_from_controller(self) -> None:
        if self._x is None or self._y is None:
            return
        xmin, xmax, ymin, ymax = self._xmin, self._xmax, self._ymin, self._ymax
        if xmax <= xmin:
            xmin, xmax = float(self._x.min()), float(self._x.max())
        if ymax <= ymin:
            ymin, ymax = float(self._y.min()), float(self._y.max())
        self._plot_widget.set_xlim(xmin, xmax, padding=0.0)
        self._plot_widget.set_ylim(ymin, ymax, padding=0.0)

    def apply_cmap_from_controller(self) -> None:
        if self._image_item is None:
            return
        # An unresolvable name yields no lookup table, which is the grayscale
        # ramp the plot fell back to before.
        self._image_item.set_colormap(self._colormap)

    # ------------------------------------------------------------------
    # ROI → 1D fit-range mapping
    # ------------------------------------------------------------------

    def _ensure_roi(self):
        """Create the rectangular ROI on first use and attach callbacks."""
        if self._roi is not None:
            return self._roi
        try:
            roi = self._plot_widget.add_roi(
                kind="rect",
                pos=(0.0, 0.0),
                size=(1.0, 1.0),
                pen=cp.to_pen("y", width=1),
                rotatable=False,
            )
        except Exception:
            return None

        try:
            roi.z = 10
            roi.on_change(self._on_roi_changed, final=False)
        except Exception:
            pass

        self._roi = roi
        return self._roi

    def _on_roi_changed(self) -> None:
        """Update 1D fit range when the 2D ROI is moved or resized.

        The 2D residual image is defined on a regular grid; for RICS this
        grid corresponds to the lag indices used to flatten the ICS map into
        the 1D data vector (row-major order). We therefore map the ROI's
        integer (y, x) bounds to a contiguous [xmin, xmax] index interval
        covering the selected rectangle and propagate it to cs.current_fit.
        """
        if getattr(self, "_roi_sync_in_progress", False):
            return
        if self._image is None:
            return

        roi = getattr(self, "_roi", None)
        if roi is None:
            return

        try:
            x0, y0 = roi.pos
            w, h = roi.size
        except Exception:
            return

        ny, nx = int(self._image.shape[0]), int(self._image.shape[1])
        if ny <= 0 or nx <= 0:
            return

        # Enforce symmetry of the ROI around the image center so that the
        # 2D selection corresponds to a symmetric lag window. This mimics
        # two line selectors acting symmetrically about the central pixel.
        cx = 0.5 * float(nx - 1)
        cy = 0.5 * float(ny - 1)

        left = x0
        right = x0 + w
        top = y0
        bottom = y0 + h

        # Compute half-width/height as the maximum distance from center to
        # either ROI edge along each axis.
        dx = max(abs(cx - left), abs(right - cx), 0.5)
        dy = max(abs(cy - top), abs(bottom - cy), 0.5)

        x0_sym = cx - dx
        x1_sym = cx + dx
        y0_sym = cy - dy
        y1_sym = cy + dy

        # Clamp symmetric bounds to valid pixel coordinates.
        x0_sym = max(0.0, min(x0_sym, float(nx - 1)))
        x1_sym = max(0.0, min(x1_sym, float(nx - 1)))
        y0_sym = max(0.0, min(y0_sym, float(ny - 1)))
        y1_sym = max(0.0, min(y1_sym, float(ny - 1)))

        # Ensure at least one pixel in each direction.
        if x1_sym <= x0_sym:
            x1_sym = min(float(nx - 1), x0_sym + 1.0)
        if y1_sym <= y0_sym:
            y1_sym = min(float(ny - 1), y0_sym + 1.0)

        # Snap ROI geometry back to the symmetric bounds.
        try:
            self._roi_sync_in_progress = True
            roi.set_pos(x0_sym, y0_sym)
            roi.set_size(x1_sym - x0_sym, y1_sym - y0_sym)
        finally:
            self._roi_sync_in_progress = False

        try:
            ix0 = int(np.floor(x0_sym))
            iy0 = int(np.floor(y0_sym))
            ix1 = int(np.ceil(x1_sym))
            iy1 = int(np.ceil(y1_sym))
        except Exception:
            return

        # Clamp ROI bounds to valid pixel indices
        ix0 = max(0, min(ix0, nx - 1))
        iy0 = max(0, min(iy0, ny - 1))
        ix1 = max(ix0 + 1, min(ix1, nx))
        iy1 = max(iy0 + 1, min(iy1, ny))

        # The 1-D data vector is this map flattened row-major, so the selected
        # pixels *are* a set of data indices — the shared region says which.
        selected = RectangleROI.from_slices((iy0, iy1), (ix0, ix1)).to_indices((ny, nx))
        if selected.size == 0:
            return
        xmin_idx, xmax_idx = int(selected[0]), int(selected[-1])

        # Propagate to the current fit's range using the same mechanism as
        # LinePlot so downstream widgets and macros stay in sync.
        try:
            cs.core.actions.dispatch(
                name="fit.range.set",
                payload={
                    "xmin": int(xmin_idx),
                    "xmax": int(xmax_idx),
                    "fit_index": getattr(self.fit, "fit_idx", 0),
                },
            )
        except Exception:
            pass

        # Notify listeners (e.g. FittingControllerWidget) so their range
        # spinboxes can mirror the ROI-selected fit range.
        try:
            self.regionChanged.emit(int(xmin_idx), int(xmax_idx))
        except Exception:
            pass

    def update(self, *args, **kwargs) -> None:
        super().update(*args, **kwargs)
        self._compute_image()

    def update_all(self, *args, **kwargs) -> None:
        self.update(*args, **kwargs)
