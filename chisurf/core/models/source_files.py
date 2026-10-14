"""A model's source files, and applying an edit of them to a live fit (Qt-free).

A fit window's *Code* face shows the source of the fit's model and its
``view.json`` and lets the user edit and apply them. What may be opened and
written is exactly :func:`model_source_files` -- the model's folder -- and
:func:`apply_model_code` saves an edit (to a timestamped copy in the settings
folder when the installation is read only) and, for the model's own module,
re-executes it so the open fit computes with the edited code.
"""

from __future__ import annotations

import datetime
import inspect
import os
import pathlib
import sys
from typing import Any

__all__ = ["apply_model_code", "compute_model_class", "model_source_files"]


def compute_model_class(model: Any) -> type | None:
    """The most-derived class of *model* that is a ChiSurf model and not a Qt widget."""
    if model is None:
        return None
    from chisurf.core.models.model import Model

    for cls in type(model).__mro__:
        if not issubclass(cls, Model):
            continue
        if any(base.__module__.startswith(("PyQt", "PySide", "qtpy")) for base in cls.__mro__):
            continue
        return cls
    return type(model)


def _view_spec_path(cls: type) -> str | None:
    for owner in cls.__mro__:
        spec_file = owner.__dict__.get("view_spec_file")
        if spec_file:
            try:
                folder = pathlib.Path(inspect.getsourcefile(owner) or "").parent
            except TypeError:
                return None
            path = folder / spec_file
            return str(path) if path.exists() else None
    return None


def model_source_files(model: Any) -> dict[str, Any]:
    """The files the Code face offers for *model*.

    Returns
    -------
    dict
        ``source`` (the module defining the model class), ``view_spec`` (its
        ``view.json`` or ``None``) and ``files`` (every ``*.py`` and
        ``*.view.json`` of that folder, the allow-list of what may be written).
    """
    cls = compute_model_class(model)
    if cls is None:
        return {"source": None, "view_spec": None, "files": []}
    try:
        source = inspect.getsourcefile(cls)
    except TypeError:
        source = None
    if not source:
        return {"source": None, "view_spec": None, "files": []}
    folder = pathlib.Path(source).parent
    files = [str(p) for p in sorted(folder.glob("*.py"))]
    files += [str(p) for p in sorted(folder.glob("*.view.json"))]
    return {"source": str(source), "view_spec": _view_spec_path(cls), "files": files}


def apply_model_code(fit: Any, path: str, code: str) -> dict[str, Any]:
    """Save *code* to *path* and, for the model's own module, apply it to *fit*.

    Parameters
    ----------
    fit : Fit
        The fit whose model the file belongs to.
    path : str
        One of :func:`model_source_files` ``["files"]``; anything else is refused.
    code : str
        The new text.

    Returns
    -------
    dict
        ``saved`` (where it was written), ``applied`` (whether the model was
        re-executed) and ``message`` for a status line.
    """
    model = getattr(fit, "model", None)
    files = model_source_files(model)
    path = str(path)
    if path not in files["files"]:
        raise ValueError(f"{path!r} is not a file of this fit's model")
    cls = compute_model_class(model)
    if cls is None:  # unreachable: a model-less fit lists no files, so the check above raised
        raise ValueError("this fit has no model")
    is_source = path == files["source"]
    target = path
    if not os.access(path, os.W_OK):
        from chisurf.core.settings.path_utils import get_path

        folder = get_path("settings") / "models"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if is_source:
            # The name ``inject_user_models()`` looks for, so the edit is applied at the next start too.
            name = f"{cls.__module__}__override__{stamp}.py"
        else:
            name = f"{pathlib.Path(path).stem}_{stamp}{pathlib.Path(path).suffix}"
        target = str(folder / name)
    pathlib.Path(target).write_text(code, encoding="utf-8")
    if not is_source:
        return {"saved": target, "applied": False, "message": f"Saved {target}"}
    module = sys.modules.get(cls.__module__)
    if module is None:
        return {"saved": target, "applied": False, "message": f"Saved {target}"}
    exec(compile(code, path, "exec"), module.__dict__)  # noqa: S102 - the user's own model edit
    new_class = getattr(module, cls.__name__, None)
    if new_class is not None and type(model) is cls:
        model.__class__ = new_class
    update = getattr(fit, "update", None)
    if callable(update):
        update()
    return {"saved": target, "applied": True, "message": f"Saved {target}; model code applied."}
