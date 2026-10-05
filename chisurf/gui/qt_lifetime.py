"""Whether a Qt wrapper's C++ object still exists, for any Qt binding.

``qtpy`` does not re-export ``sip`` everywhere (the pixi environment's qtpy has
no ``qtpy.sip``) and a top-level ``sip`` module is not installed with PyQt5's
wheels, so the usual ``from qtpy import sip`` / ``import sip`` chain silently
ends in ``sip = None`` on exactly the machines that never see it locally. This
asks the binding that is actually loaded.
"""

from __future__ import annotations

from typing import Any


def is_deleted(widget: Any) -> bool:
    """Return whether *widget*'s underlying C/C++ object has been destroyed.

    Parameters
    ----------
    widget : object
        A Qt wrapper (``QObject`` subclass) or ``None``.

    Returns
    -------
    bool
        ``True`` for ``None`` and for a wrapper whose C++ object is gone.
    """
    if widget is None:
        return True
    try:  # PyQt (sip)
        from PyQt5 import sip  # type: ignore

        return bool(sip.isdeleted(widget))
    except Exception:
        pass
    try:  # PySide (shiboken)
        import shiboken6  # type: ignore

        return not shiboken6.isValid(widget)
    except Exception:
        pass
    try:  # last resort: touch a cheap method
        widget.objectName()
        return False
    except RuntimeError:
        return True
    except Exception:
        return False
