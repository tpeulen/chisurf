"""The PSF as isosurfaces in a chimol view, with chimol's trackball camera.

The volume is handed to chimol as a map (``Viewer.add_volume``) and contoured by marching cubes at three
fractions of the peak: the *threshold* shell (the dim wings), the half-maximum shell and a bright core. Colours come
from the Display colormap at ``fraction ** gamma``. The grid is cropped to the box that holds the threshold shell,
so the camera frames the focus and not the empty margin of a long z-stack.

Left-drag rotates, the wheel zooms, Ctrl+left-drag (or middle-drag) pans; chimol owns all three.
"""

from __future__ import annotations

import logging

import numpy as np

from chisurf.emtk.chimol_view import ChimolView

logger = logging.getLogger(__name__)

#: Fractions of the peak that get a shell besides the threshold, and the opacity of each shell (outermost first).
INNER_FRACTIONS = (0.5, 0.85)
SHELL_ALPHA = {0: 0.4, 1: 0.7}
#: Turns applied after a new volume is framed (chimol's ``turn axis, degrees``).
OBLIQUE_VIEW = ("turn x, -70", "turn y, 25")
#: The dimmest shell is coloured from this point of the colormap up, so it does not vanish into the black background.
COLOUR_FLOOR = 0.45


def shell_levels(threshold: float, gamma: float, colormap, peak: float) -> list[dict]:
    """The contour levels chimol is given: absolute levels, colours from *colormap* at ``fraction ** gamma``."""
    fractions = [float(threshold)] + [f for f in INNER_FRACTIONS if f > float(threshold) + 0.05]
    levels = []
    for index, fraction in enumerate(fractions):
        shade = min(max(fraction, 0.0), 1.0) ** float(gamma)
        r, g, b = (float(c) for c in colormap(COLOUR_FLOOR + (1.0 - COLOUR_FLOOR) * shade)[:3])
        last = index == len(fractions) - 1
        levels.append(
            {
                "level": fraction * peak,
                "color": (r, g, b, 1.0 if last else SHELL_ALPHA.get(index, 0.7)),
                "style": "surface",
            }
        )
    return levels


def crop_box(volume: np.ndarray, threshold: float, pad: int = 2) -> tuple[slice, slice, slice]:
    """The ``(z, y, x)`` box holding every voxel at or above ``threshold * peak``, padded by *pad* voxels."""
    mask = volume >= float(threshold) * max(float(volume.max()), 1e-30)
    box = []
    for axis in range(3):
        other = tuple(a for a in range(3) if a != axis)
        hit = np.nonzero(mask.any(axis=other))[0]
        lo, hi = (int(hit[0]), int(hit[-1])) if len(hit) else (0, volume.shape[axis] - 1)
        box.append(slice(max(lo - pad, 0), min(hi + pad, volume.shape[axis] - 1) + 1))
    return box[0], box[1], box[2]


class PSFVolumeView:
    """A chimol view of the model's volume, rebuilt only when what it draws changes."""

    def __init__(self) -> None:
        # scale_factor 1.0: world units are nanometres here, and chimol's default scale is for Angstrom.
        self.view = ChimolView(
            min_size=(320, 240), viewer_options={"scale_factor": 1.0}, skip_idle_frames=True
        )
        #: what the built volume and its look were drawn from (``None``: nothing built yet)
        self._volume_key: tuple | None = None
        self._look_key: tuple | None = None
        self._object_id = None
        self._grid_shape = None

    @property
    def error(self) -> str:
        """Why chimol could not start (no WebGPU adapter ...); empty while it works."""
        return self.view.error

    def close(self) -> None:
        self.view.close()

    # -- the scene ---------------------------------------------------------------------------------------- #
    def sync(self, model) -> bool:
        """Bring the chimol scene up to date with *model*; ``False`` when chimol is unavailable.

        While chimol is still starting in the background this does nothing and answers ``True``; the frame after it
        has started builds the scene.
        """
        if not self.view.ready():
            if self.view.error:
                return False
            self.view.start()
            return True
        renderer = self.view.app.renderer
        renderer.bare_view = True  # the picture alone: the window around it is emtk's
        volume = model.volume
        if volume is None:
            return True
        volume_key = (
            model._key,
            float(model.threshold),
            float(model.pixel_size_nm),
            float(model.z_step_nm),
            bool(model.show_polarization),
        )
        look_key = (float(model.threshold), float(model.gamma), model.colormap)
        try:
            if volume_key != self._volume_key:
                self._build(model)
                self._volume_key, self._look_key = volume_key, look_key
            elif look_key != self._look_key:
                self._recolour(model)
                self._look_key = look_key
        except Exception as exc:  # noqa: BLE001 - shown in place of the view
            self.view.error = f"{type(exc).__name__}: {exc}"
            logger.warning("PSF 3-D view failed: %s", self.view.error, exc_info=True)
            return False
        return True

    def _colormap(self, model):
        from emtk import colormaps

        return colormaps.get(model.colormap)

    def _build(self, model) -> None:
        from chimol.core.model.volume import VolumeGrid

        viewer = self.view.viewer
        volume = np.asarray(model.volume)
        peak = max(float(volume.max()), 1e-30)
        box = crop_box(volume, model.threshold)
        crop = volume[box]
        step = np.array([model.pixel_size_nm, model.pixel_size_nm, model.z_step_nm], dtype=float)
        shape_xyz = np.array(volume.shape[::-1], dtype=float)
        lo_xyz = np.array([box[2].start, box[1].start, box[0].start], dtype=float)
        origin = (lo_xyz - (shape_xyz - 1) / 2.0) * step  # nm, centred on the volume's middle voxel
        grid = VolumeGrid.from_array(
            np.transpose(crop, (2, 1, 0)), origin=origin, step=step, name="PSF"
        )
        if self._object_id is not None:
            viewer.remove_object(self._object_id)
        viewer.clear_annotations()
        levels = shell_levels(model.threshold, model.gamma, self._colormap(model), peak)
        self._object_id = viewer.add_volume(grid, name="PSF", levels=levels)
        for (
            command
        ) in OBLIQUE_VIEW:  # look at the focus from the side and above, so its length shows
            self.view.app.cmd.do(command)
        if model.show_polarization and model.model == "vectorial":
            self._add_polarization(model, grid, shape_xyz, step)
        self.view.sync_panel()

    def _add_polarization(self, model, grid, shape_xyz, step) -> None:
        """The polarization strokes, on a ring placed at the top of the cropped focus box and sized to it."""
        segments = model.polarization_segments()
        if segments is None:
            return
        low, high = grid.extent()
        centre = (np.asarray(low) + np.asarray(high)) / 2.0
        half_xy = max(float(high[0] - low[0]), float(high[1] - low[1])) / 2.0
        ring_nm = (
            0.38 * min(shape_xyz[0], shape_xyz[1]) * step[0]
        )  # the ring radius polarization_segments draws
        scale = 0.9 * half_xy / max(ring_nm, 1e-9)
        z_ring = float(high[2]) - 0.05 * float(high[2] - low[2])
        mid = (shape_xyz - 1) / 2.0
        viewer = self.view.viewer
        for segment in np.asarray(segments, dtype=float):
            nm = (segment - mid) * step
            points = np.empty_like(nm)
            points[:, 0] = centre[0] + scale * nm[:, 0]
            points[:, 1] = centre[1] + scale * nm[:, 1]
            points[:, 2] = z_ring
            viewer.add_annotation(
                "line", points, color=(0.45, 0.8, 1.0, 1.0), width=2.0, name="polarization"
            )

    def _recolour(self, model) -> None:
        """New threshold-free look (gamma, colormap): re-contour at the new colours without moving the camera."""
        volume = np.asarray(model.volume)
        peak = max(float(volume.max()), 1e-30)
        levels = shell_levels(model.threshold, model.gamma, self._colormap(model), peak)
        self.view.viewer.set_volume_levels(levels, self._object_id)

    # -- one frame ---------------------------------------------------------------------------------------- #
    def draw(self, size=(-1.0, -1.0)) -> bool:
        """Draw the view at the cursor; ``False`` when chimol is unavailable."""
        return self.view.draw(size)
