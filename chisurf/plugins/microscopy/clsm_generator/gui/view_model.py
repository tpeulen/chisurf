"""Qt-free view-model for the CLSM Generator tool.

Loads an intensity image + per-detector lifetime map(s), simulates a CLSM photon
image with
:func:`chisurf.core.fluorescence.imaging.simulate.simulate_clsm_from_maps`, and
exposes the input maps and the reconstructed image for browsing.  No Qt — the
(slow) generation is driven from a worker thread by the tool.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Callable

import numpy as np

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "generator.view.json"


class ClsmGeneratorViewModel:
    """State + logic for the CLSM generator (no Qt)."""

    def __init__(self) -> None:
        self.intensity_path: str = ""
        self.lifetime_paths: list[str] = []
        # Simulation parameters.
        self.pixel_size: float = 0.5
        self.n_micro: int = 256
        self.dt: float = 0.032
        self.brightness_scale: float = 2000.0
        self.n_lifetime_levels: int = 12
        self.n_intensity_levels: int = 8
        self.irf_center: float = 10.0
        self.irf_sigma: float = 1.6
        self.dwell: float = 0.05
        # Loaded inputs + result.
        self._intensity_in: np.ndarray | None = None
        self._lifetime_in: list[np.ndarray] = []
        self._sim = None
        self.current_view: str = "intensity_in"
        self.status_text: str = ""
        self._observers: list[Callable[[str], None]] = []

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored view.json."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    # ── observers ──
    def add_observer(self, cb: Callable[[str], None]) -> None:
        """Register *cb*, called with an event name on every change."""
        self._observers.append(cb)

    def notify(self, event: str = "changed") -> None:
        """Notify observers of a state change."""
        for cb in list(self._observers):
            try:
                cb(event)
            except Exception:
                logger.debug("clsm-generator observer failed", exc_info=True)

    # ── file inputs ──
    @property
    def sel_intensity(self) -> str:
        """Intensity-image path (bound to the file picker; loads on set)."""
        return self.intensity_path

    @sel_intensity.setter
    def sel_intensity(self, value) -> None:
        self.intensity_path = str(value or "")
        self._intensity_in = self._load(self.intensity_path)
        if self._intensity_in is not None:
            self.current_view = "intensity_in"
        self.notify("loaded")

    @property
    def sel_lifetime_files(self) -> list:
        """Per-detector lifetime-map paths (bound to the path_list; loads on set)."""
        return list(self.lifetime_paths)

    @sel_lifetime_files.setter
    def sel_lifetime_files(self, value) -> None:
        self.lifetime_paths = [str(v) for v in (value or [])]
        self._lifetime_in = [m for m in (self._load(p) for p in self.lifetime_paths) if m is not None]
        self.notify("loaded")

    @staticmethod
    def _load(path: str) -> np.ndarray | None:
        if not path:
            return None
        from chisurf.core.fluorescence.imaging.simulate import load_image_map

        try:
            return load_image_map(path)
        except Exception:  # noqa: BLE001 - a bad path just leaves nothing loaded
            logger.debug("could not load %s", path, exc_info=True)
            return None

    # Simulation parameters are plain attributes; AutoForm value sections bind them
    # directly (see generator.view.json), so no property proxies are needed.

    # ── the generate action ──
    def request_generate(self) -> None:
        """Button action: ask the host to run the simulation on a worker thread."""
        self.notify("start_generate")

    def can_generate(self) -> tuple[bool, str]:
        """Return ``(ok, reason)`` describing whether generation is possible."""
        if self._intensity_in is None:
            return False, "Load an intensity image."
        if not self._lifetime_in:
            return False, "Load at least one lifetime map."
        shape = self._intensity_in.shape
        if any(m.shape != shape for m in self._lifetime_in):
            return False, "Lifetime map(s) must match the intensity-image shape."
        return True, ""

    def generate(self) -> None:
        """Simulate the CLSM image from the loaded maps (BLOCKING — worker thread)."""
        from chisurf.core.fluorescence.imaging.simulate import simulate_clsm_from_maps

        ok, reason = self.can_generate()
        if not ok:
            self.status_text = reason
            self.notify("done")
            return
        self.status_text = "Generating CLSM photon image…"
        self.notify("progress")
        try:
            self._sim = simulate_clsm_from_maps(
                self._intensity_in,
                self._lifetime_in if len(self._lifetime_in) > 1 else self._lifetime_in[0],
                pixel_size=self.pixel_size, n_micro=self.n_micro, dt=self.dt,
                brightness_scale=self.brightness_scale,
                n_lifetime_levels=self.n_lifetime_levels,
                n_intensity_levels=self.n_intensity_levels,
                irf_center=self.irf_center, irf_sigma=self.irf_sigma, dwell=self.dwell,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced in the status line
            logger.debug("generation failed", exc_info=True)
            self.status_text = f"Generation failed: {exc}"
            self.notify("done")
            return
        self.current_view = "recon"
        n_ph = int(np.asarray(self._sim.intensity).sum())
        self.status_text = f"Generated {n_ph} photons ({len(self._lifetime_in)} detector(s))."
        self.notify("done")

    # ── save ──
    def request_save(self) -> None:
        """Button action: ask the host for a path and save the photon stream."""
        self.notify("start_save")

    def has_result(self) -> bool:
        """Return True when there is a generated image to save."""
        return self._sim is not None

    def save(self, path: str) -> str:
        """Save the generated photon stream (``.npz`` arrays, else a TTTR file).

        Also writes ``<stem>_intensity.tif`` next to it.
        Returns the written path (empty when there is nothing to save).
        """
        if self._sim is None:
            self.status_text = "Nothing generated yet."
            self.notify("done")
            return ""
        tttr = self._sim.tttr
        p = pathlib.Path(path)
        try:
            if p.suffix.lower() == ".npz":
                arrays = {
                    "macro_times": np.asarray(tttr.macro_times),
                    "micro_times": np.asarray(tttr.micro_times),
                    "routing_channels": np.asarray(tttr.routing_channels),
                }
                event_fn = getattr(tttr, "get_event_type", None)
                if callable(event_fn):
                    arrays["event_types"] = np.asarray(event_fn())
                np.savez(p, **arrays)
            else:
                tttr.write(str(p))
            self._save_intensity_tif(p)
        except Exception as exc:  # noqa: BLE001 - surfaced in the status line
            logger.debug("save failed", exc_info=True)
            self.status_text = f"Save failed: {exc}"
            self.notify("done")
            return ""
        self.status_text = f"Saved photon stream to {p.name}"
        self.notify("saved")
        return str(p)

    def _save_intensity_tif(self, path: pathlib.Path) -> None:
        try:
            from chisurf.core.fio.image import imwrite

            imwrite(
                path.with_name(f"{path.stem}_intensity.tif"),
                np.asarray(self._sim.intensity, dtype=np.float32),
            )
        except Exception:
            logger.debug("intensity TIFF export skipped", exc_info=True)

    # ── image_browser accessors ──
    def view_entries(self) -> list[dict]:
        """Browsable views: input intensity, input lifetime map(s), reconstruction."""
        entries: list[dict] = []
        if self._intensity_in is not None:
            entries.append({"id": "intensity_in", "label": "Intensity (input)"})
        for d in range(len(self._lifetime_in)):
            tag = f" d{d}" if len(self._lifetime_in) > 1 else ""
            entries.append({"id": f"lifetime_in_{d}", "label": f"Lifetime{tag} (input)"})
        if self._sim is not None:
            entries.append({"id": "recon", "label": "Reconstructed intensity"})
        return entries

    def current_view_image(self):
        """Return the 2-D map for the currently-selected view, or None."""
        view = self.current_view or ""
        if view == "intensity_in":
            return None if self._intensity_in is None else np.asarray(self._intensity_in)
        if view == "recon":
            return None if self._sim is None else np.asarray(self._sim.intensity)
        if view.startswith("lifetime_in_"):
            try:
                d = int(view.rsplit("_", 1)[1])
                return np.asarray(self._lifetime_in[d])
            except (ValueError, IndexError):
                return None
        return None

    def info_html(self) -> str:
        """Status/summary text shown above the viewer."""
        if self.status_text:
            return f"<i>{self.status_text}</i>"
        if self._intensity_in is None:
            return (
                "<i>Load an intensity image and one lifetime map per detector "
                "(TIFF or numpy), set the parameters, then press <b>Generate</b>. "
                "The photon image reproduces the input intensity and lifetime.</i>"
            )
        shape = "×".join(str(s) for s in self._intensity_in.shape)
        return f"<i>Intensity {shape}; {len(self._lifetime_in)} lifetime map(s) loaded.</i>"
