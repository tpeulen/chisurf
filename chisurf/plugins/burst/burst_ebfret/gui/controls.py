"""The model behind ``main.view.json``: the main window's controls.

``main.view.json`` declares the controls of ebFRET's main window -- which field,
its label, its range, its description. This object is what those declarations
read and write. It holds nothing: a read comes from the backend's last view, a
write is sent to the backend (``EbfretClient.set``), and the actions are the
window's buttons. That is what keeps the window database- and analysis-free
while the form stays declarative.
"""

from __future__ import annotations

from typing import Any

__all__ = ["MainControls"]


class MainControls:
    """Attributes and actions named by ``main.view.json``.

    Parameters
    ----------
    gui : EbfretGui
        The window, for its client, its last view and its actions.
    """

    def __init__(self, gui: Any) -> None:
        self._gui = gui

    # -- reads come from the last view ------------------------------------ #
    def _control(self, name: str, default: Any) -> Any:
        return self._gui.controls.get(name, default)

    def _series(self, name: str, default: Any) -> Any:
        return (self._gui.view.get("series") or {}).get(name, default)

    def _set(self, name: str, value: Any) -> None:
        self._gui.act(lambda: self._gui.client.set(name, value))

    @property
    def series_value(self) -> int:
        """*Select Series*."""
        return int(self._control("series_value", 0))

    @series_value.setter
    def series_value(self, value: int) -> None:
        self._set("series", int(value))

    @property
    def ensemble_value(self) -> int:
        """*Select States*."""
        return int(self._control("ensemble_value", 2))

    @ensemble_value.setter
    def ensemble_value(self, value: int) -> None:
        self._set("ensemble", int(value))

    @property
    def crop_min(self) -> int | None:
        """*Crop > Min* of the current series."""
        return self._series("crop_min", None)

    @crop_min.setter
    def crop_min(self, value: int) -> None:
        self._set("crop_min", int(value))

    @property
    def crop_max(self) -> int | None:
        """*Crop > Max* of the current series."""
        return self._series("crop_max", None)

    @crop_max.setter
    def crop_max(self, value: int) -> None:
        self._set("crop_max", int(value))

    @property
    def exclude(self) -> bool:
        """*Crop > Exclude* of the current series."""
        return bool(self._series("exclude", False))

    @exclude.setter
    def exclude(self, value: bool) -> None:
        self._set("exclude", bool(value))

    @property
    def min_states(self) -> int:
        """*States > Min*."""
        return int(self._control("min_states", 2))

    @min_states.setter
    def min_states(self, value: int) -> None:
        self._set("min_states", int(value))

    @property
    def max_states(self) -> int:
        """*States > Max*."""
        return int(self._control("max_states", 6))

    @max_states.setter
    def max_states(self, value: int) -> None:
        self._set("max_states", int(value))

    @property
    def run_scope(self) -> str:
        """*Analysis > States*: ``"All"`` or ``"Current"``."""
        return "All" if self._control("run_all", True) else "Current"

    @run_scope.setter
    def run_scope(self, value: str) -> None:
        self._set("run_all", str(value) == "All")

    @property
    def restarts(self) -> int:
        """*Analysis > Restarts*."""
        return int(self._control("restarts", 2))

    @restarts.setter
    def restarts(self, value: int) -> None:
        self._set("restarts", int(value))

    @property
    def run_precision(self) -> float:
        """*Analysis > Precision*."""
        return float(self._control("run_precision", 1e-3))

    @run_precision.setter
    def run_precision(self, value: float) -> None:
        self._set("run_precision", float(value))

    # -- actions ------------------------------------------------------------ #
    def run(self) -> None:
        """*Run*."""
        self._gui.run()

    def stop(self) -> None:
        """*Stop*."""
        self._gui.stop()

    def reset(self) -> None:
        """*Reset*."""
        self._gui.reset()

    # -- the view_form hooks ----------------------------------------------- #
    def enabled(self, name: str) -> bool:
        """What ``set_control.m`` enables and disables.

        Parameters
        ----------
        name : str
            A field or action of ``main.view.json``.

        Returns
        -------
        bool
        """
        data, running = self._gui.has_data, self._gui.running
        c = self._gui.controls
        if name == "run":
            return data and not running
        if name == "reset":
            return data and not running
        if name == "stop":
            return running
        if name in ("crop_min", "crop_max", "exclude"):
            return data
        if name == "series_value":
            return c.get("series_max", 0) > c.get("series_min", 0)
        if name == "ensemble_value":
            return c.get("ensemble_max", 0) > c.get("ensemble_min", 0)
        return True

    def bounds(self, name: str) -> tuple | None:
        """Run-time limits of the two index controls and the crop fields.

        Parameters
        ----------
        name : str
            A field of ``main.view.json``.

        Returns
        -------
        tuple or None
            ``(lo, hi)``, or ``None`` for the spec's own limits.
        """
        c = self._gui.controls
        if name == "series_value":
            return (c.get("series_min", 0), c.get("series_max", 0))
        if name == "ensemble_value":
            return (c.get("ensemble_min", 2), c.get("ensemble_max", 6))
        if name in ("crop_min", "crop_max"):
            return (1, self._series("length", None))
        return None

    # -- table sources ------------------------------------------------------ #
    def series_records(self) -> list[dict]:
        """Rows of the *Series List* table."""
        return self._gui.view.get("series_table") or []

    def state_records(self) -> list[dict]:
        """Rows of the *States Table*."""
        return self._gui.view.get("states_table") or []

    def select_series(self, record: dict | int | None) -> None:
        """A row selected in the *Series List*: show that series."""
        if isinstance(record, dict) and record.get("index"):
            self.series_value = int(record["index"])
        elif isinstance(record, int):
            self.series_value = record + 1
