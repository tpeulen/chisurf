from __future__ import annotations

import abc
from typing import Any, Optional

from .scene import Scene


class Renderer:
    """Abstract interface for chimol rendering backends.

    This class deliberately avoids :class:`abc.ABC` as a metaclass so that a
    renderer can inherit from a toolkit's widget class without a metaclass
    conflict. The methods still behave like abstract ones, raising
    :class:`NotImplementedError` by default.

    **The interface names no toolkit.** It used to be typed in Qt's terms --
    ``parent: QtWidgets.QWidget``, ``widget() -> QtWidgets.QWidget`` -- which
    described only one of the three hosts that now implement it: the Qt plugin,
    the toolkit-free desktop window, and a browser canvas. An interface that
    can only be spelled in one host's vocabulary is one the other hosts are
    implementing by accident.
    """

    def __init__(self, parent: Optional[Any] = None) -> None:
        self._parent = parent

    def widget(self) -> Any:
        """Return the toolkit object to embed, where the host has one.

        Returns
        -------
        object
            A widget on a toolkit host. Hosts without a toolkit own a window
            beside the renderer rather than a widget inside it, and answer with
            themselves or with ``None``.
        """
        raise NotImplementedError

    def set_scene(self, scene: Optional[Scene]) -> None:
        """Upload a new scene description to the renderer."""

        raise NotImplementedError

    def clear(self) -> None:
        """Clear any previously rendered geometry."""

        # Optional hook; concrete renderers may override.
        return None

    def configure_grid(self, size: float, spacing: float) -> None:
        """Define the logical grid dimensions for the renderer."""

        raise NotImplementedError

    def set_background_color(self, color) -> None:
        """Set the renderer's background color (Qt-compatible value)."""

        raise NotImplementedError

    def set_grid_visible(self, visible: bool) -> None:
        """Toggle visibility of the ground grid / reference plane."""

        raise NotImplementedError

    def fit_to_radius(self, radius: float) -> None:
        """Adjust camera distance to comfortably fit the given radius."""

        raise NotImplementedError

    def reset_view(self, distance: float, elevation: float, azimuth: float) -> None:
        """Reset the camera to the provided spherical coordinates."""

        raise NotImplementedError

    def configure_camera(
        self,
        *,
        near_clip: float,
        far_clip: float,
        min_near_clip: float,
        max_near_clip: float,
        clip_wheel_scale: float,
    ) -> None:
        """Configure camera clipping planes and interaction parameters."""

        # Optional hook for renderers that expose clip controls.
        return None
