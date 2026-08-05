"""Toolbar controls for the Chimol viewer."""

from __future__ import annotations

from typing import Any, Optional

from qtpy import QtWidgets, QtCore


# ── Emoji-enhanced default button labels ──────────────────────────────
_BUTTON_DEFAULTS: dict[str, dict[str, Any]] = {
    "open": {
        "text": "\U0001f4c2 Open",
        "tool_tip": "Open structure file",
    },
    "plane": {
        "text": "\u2708\ufe0f Plane",
        "tool_tip": "Toggle reference plane",
        "checkable": True,
    },
    "surface": {
        "text": "\U0001f310 Surf",
        "tool_tip": "Toggle surface representation",
        "checkable": True,
    },
    "display_cfg": {
        "text": "\u2699\ufe0f Cfg",
        "tool_tip": "Open Chimol display configuration",
    },
    "mouse_mode": {
        "text": "\U0001f5b1\ufe0f PyMOL",
        "tool_tip": "Toggle PyMOL/Chimol mouse interaction mode (rotate + pan)",
        "checkable": True,
        "checked": True,
    },
    "color": {
        "text": "\U0001f3a8 AA",
        "tool_tip": "Color amino acids by residue type",
        "checkable": True,
    },
    "color_ss": {
        "text": "\U0001f52c SS",
        "tool_tip": "Color by secondary structure (helix/strand/coil)",
        "checkable": True,
    },
    "color_seq": {
        "text": "\U0001f308 Seq",
        "tool_tip": "Color by sequence position (gradient)",
        "checkable": True,
    },
    "info": {
        "text": "\u2139\ufe0f Info",
        "tool_tip": "Toggle system info panel",
        "checkable": True,
        # Off by default. The panel covers a corner of the viewport with what
        # is mostly already on screen -- the object panel names the structure
        # and the sequence strip shows its residues -- so it earns its space
        # only when asked for. PyMOL shows nothing over the scene by default
        # either. `MolView._info_visible` already started False; this button
        # was overriding it at startup.
        "checked": False,
    },
}


class ControlsToolbar(QtCore.QObject):
    """Toolbar controls for the Chimol viewer.

    Creates a QToolBar with labelled tool buttons organised into logical
    groups separated by separators.
    """

    def __init__(
        self,
        parent: QtWidgets.QMainWindow,
        *,
        button_overrides: Optional[dict[str, dict[str, Any]]] = None,
    ) -> None:
        super().__init__(parent)
        overrides = dict(button_overrides or {})

        def _cfg(key: str) -> dict[str, Any]:
            base = dict(_BUTTON_DEFAULTS.get(key, {}))
            ovr = overrides.get(key, {})
            base.update(ovr)
            return base

        self._toolbar = QtWidgets.QToolBar("View Controls", parent)
        self._toolbar.setObjectName("ChimolToolBar")
        self._toolbar.setIconSize(QtCore.QSize(16, 16))
        self._toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)

        # ── File / open ───────────────────────────────────────────────
        self.button_open = self._add_button("open", _cfg("open"))
        self._toolbar.addSeparator()

        # ── Display group ─────────────────────────────────────────────
        self.button_plane = self._add_button("plane", _cfg("plane"))
        self.button_surface = self._add_button("surface", _cfg("surface"))
        self.button_display_cfg = self._add_button("display_cfg", _cfg("display_cfg"))
        self.button_mouse_mode = self._add_button("mouse_mode", _cfg("mouse_mode"))
        self._toolbar.addSeparator()

        # ── Colour group ──────────────────────────────────────────────
        self.button_color = self._add_button("color", _cfg("color"))
        self.button_color_ss = self._add_button("color_ss", _cfg("color_ss"))
        self.button_color_sequence = self._add_button("color_seq", _cfg("color_seq"))
        self._toolbar.addSeparator()

        # ── Info ──────────────────────────────────────────────────────
        self.button_info = self._add_button("info", _cfg("info"))

    # ── public helpers ────────────────────────────────────────────────

    @property
    def toolbar(self) -> QtWidgets.QToolBar:
        return self._toolbar

    # ── internal helpers ──────────────────────────────────────────────

    def _add_button(
        self,
        key: str,
        cfg: dict[str, Any],
    ) -> QtWidgets.QToolButton:
        """Build a QToolButton from *cfg* and append it to the toolbar."""
        btn = QtWidgets.QToolButton(self._toolbar)
        btn.setText(str(cfg.get("text", key)))
        tip = cfg.get("tool_tip")
        if tip:
            btn.setToolTip(str(tip))
        checkable = bool(cfg.get("checkable", False))
        btn.setCheckable(checkable)
        if checkable:
            btn.setChecked(bool(cfg.get("checked", False)))
        obj_name = cfg.get("object_name")
        if obj_name:
            btn.setObjectName(str(obj_name))

        # Apply arbitrary setter calls from config
        setters = cfg.get("setters")
        if isinstance(setters, dict):
            for method_name, value in setters.items():
                method = getattr(btn, method_name, None)
                if callable(method):
                    try:
                        if isinstance(value, (list, tuple)):
                            method(*value)
                        else:
                            method(value)
                    except Exception:
                        continue

        self._toolbar.addWidget(btn)
        return btn
