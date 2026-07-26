"""Show a message box at most once per session.

Use :func:`show_warning_once` to avoid raising the same dialog several times
when it is triggered from multiple call sites during initialization (e.g.
several widgets that independently check for a missing file).

The box itself is :class:`~chisurf.gui.dialogs.ChiSurfMessageBox`, so the
warning is logged even when it is not shown and never blocks a headless run.
"""

from chisurf.gui import dialogs

_shown_warnings: set[str] = set()


def show_warning_once(
    key: str,
    title: str,
    text: str,
    informative_text: str = "",
    details: str = "",
    kind: str = "warning",
) -> None:
    """Show a message box only once per session for a given *key*.

    Parameters
    ----------
    key : str
        Unique identifier for this warning (e.g. ``"missing_detector_setups"``).
        Subsequent calls with the same key are silently ignored.
    title : str
        Window title of the message box.
    text : str
        Main message text.
    informative_text : str, optional
        Additional descriptive text.
    details : str, optional
        Expandable details text.
    kind : str, optional
        ``"warning"`` (default), ``"information"`` or ``"critical"``.
    """
    if key in _shown_warnings:
        return
    _shown_warnings.add(key)

    report = getattr(dialogs.ChiSurfMessageBox, kind, dialogs.ChiSurfMessageBox.warning)
    report(None, title, text, informative=informative_text or None, detail=details or None)


def mark_warning_shown(key: str) -> None:
    """Manually mark a warning key as already shown.

    Use this when you need a box this helper cannot build (extra buttons, a
    tick box — see :meth:`~chisurf.gui.dialogs.ChiSurfMessageBox.choice`) but
    still want the once-per-session guarantee.
    """
    _shown_warnings.add(key)


def was_warning_shown(key: str) -> bool:
    """Return True if *key* has already been shown this session."""
    return key in _shown_warnings


def reset_warnings() -> None:
    """Clear all previously-shown warning keys (useful for testing)."""
    _shown_warnings.clear()
