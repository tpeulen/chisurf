"""Shared tool-button styling for consistent plugin toolbars.

Promotes the colour-coded Burst-Variance-Analysis toolbar scheme to a single
reusable helper so every tool builds action buttons that look and behave the
same. Each semantic *kind* (``run`` / ``folder`` / ``save`` / ``clear`` /
``settings`` / ``help`` / ``toggle``) has one accent; all share a common base
(rounded, bold, dim-on-disabled) and a matching transparent toolbar.

Usage::

    from chisurf.gui.widgets.tool_buttons import styled_tool_button, TOOLBAR_STYLE

    toolbar.setStyleSheet(TOOLBAR_STYLE)
    run = styled_tool_button("▶  Run", kind="run", tooltip="Run the analysis")

This keeps the button language identical across the Burst Analysis workflow
(BVA, 2CDE, MLE, H2MM, …) instead of each panel inventing its own.
"""

from __future__ import annotations

from qtpy import QtCore, QtWidgets

#: Per-kind accent colours (background / border / hover / pressed / checked).
BTN_STYLES: dict[str, str] = {
    "folder": """
QToolButton { background-color: #2a4a7a; border: 1px solid #4a7aba; }
QToolButton:hover { background-color: #3a5a9a; border-color: #6a9ada; }
QToolButton:pressed { background-color: #1a3a6a; }
""",
    "run": """
QToolButton { background-color: #2a6a3a; border: 1px solid #4a9a5a; }
QToolButton:hover { background-color: #3a8a4a; border-color: #6aba7a; }
QToolButton:pressed { background-color: #1a5a2a; }
""",
    "toggle": """
QToolButton { background-color: #5a3a6a; border: 1px solid #8a5a9a; }
QToolButton:hover { background-color: #7a4a8a; border-color: #aa7aba; }
QToolButton:pressed { background-color: #4a2a5a; }
QToolButton:checked { background-color: #7a5a3a; border-color: #aa8a5a; }
""",
    "save": """
QToolButton { background-color: #6a5a2a; border: 1px solid #9a8a4a; }
QToolButton:hover { background-color: #8a7a3a; border-color: #baaa5a; }
QToolButton:pressed { background-color: #5a4a1a; }
""",
    "clear": """
QToolButton { background-color: #6a2a2a; border: 1px solid #9a4a4a; }
QToolButton:hover { background-color: #8a3a3a; border-color: #ba5a5a; }
QToolButton:pressed { background-color: #5a1a1a; }
""",
    "settings": """
QToolButton { background-color: #4a4a6a; border: 1px solid #6a6a9a; }
QToolButton:hover { background-color: #5a5a8a; border-color: #8a8aba; }
QToolButton:pressed { background-color: #3a3a5a; }
""",
    "help": """
QToolButton { background-color: #4a6a4a; border: 1px solid #6a8a6a; }
QToolButton:hover { background-color: #5a8a5a; border-color: #8aba7a; }
QToolButton:pressed { background-color: #3a5a3a; }
""",
    #: Neutral default for buttons without a stronger semantic role.
    "default": """
QToolButton { background-color: #40404a; border: 1px solid #5a5a66; }
QToolButton:hover { background-color: #50505c; border-color: #70707c; }
QToolButton:pressed { background-color: #303038; }
QToolButton:checked { background-color: #5a4a3a; border-color: #8a6a4a; }
""",
}

#: Base rules applied to every styled tool button (before the per-kind accent).
TOOLBAR_BUTTON_BASE = """
QToolButton {
    border-radius: 5px;
    padding: 5px 10px;
    margin: 0px;
    font-weight: bold;
    font-size: 12px;
    color: #e0e0e0;
}
QToolButton:disabled {
    color: #666;
}
"""

#: Transparent toolbar chrome so the styled buttons read as one row.
TOOLBAR_STYLE = """
QToolBar {
    background-color: transparent;
    border: none;
    padding: 3px 4px;
    spacing: 6px;
}
QToolBar QLabel {
    margin: 0px 3px;
}
"""


def button_style(kind: str = "default") -> str:
    """Return the combined base + per-kind stylesheet for a tool button."""
    return TOOLBAR_BUTTON_BASE + BTN_STYLES.get(kind, BTN_STYLES["default"])


def apply_tool_button_style(button: QtWidgets.QAbstractButton, kind: str = "default") -> None:
    """Apply the shared style of *kind* to an existing button."""
    button.setStyleSheet(button_style(kind))


def styled_tool_button(
    text: str = "",
    *,
    kind: str = "default",
    tooltip: str | None = None,
    checkable: bool = False,
    parent: QtWidgets.QWidget | None = None,
) -> QtWidgets.QToolButton:
    """Create a consistently-styled :class:`QToolButton`.

    Parameters
    ----------
    text
        Button caption (emoji-icon prefix encouraged, e.g. ``"▶  Run"``).
    kind
        Semantic accent key from :data:`BTN_STYLES` (``run``, ``folder``, …).
    tooltip
        Optional hover tooltip (keep captions short, detail in the tooltip).
    checkable
        Whether the button toggles.
    parent
        Optional Qt parent.
    """
    btn = QtWidgets.QToolButton(parent)
    if text:
        btn.setText(text)
    btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
    btn.setStyleSheet(button_style(kind))
    if tooltip:
        btn.setToolTip(tooltip)
    if checkable:
        btn.setCheckable(True)
    return btn
