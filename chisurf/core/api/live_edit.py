"""Qt-free writes to live in-process parameter and fit objects.

GUI code must not poke ``param.value = ...`` or ``fit.update()`` itself: those
edits go through this one seam.  A parameter edit here is the *local echo* of an
edit (the controller also sends it to the backend through the fitting client and
records it for undo); the seam keeps the semantics of a write in one place so
the GUI layer holds no knowledge of how a parameter or fit mutates.
"""

from __future__ import annotations

from typing import Any

_FIELDS = ("value", "fixed", "bounds", "bounds_on", "link")


def edit_parameter(parameter: Any, **fields: Any) -> None:
    """Write fields of a live parameter object, in the order given.

    Parameters
    ----------
    parameter : object
        A fitting parameter (or any object carrying the same attributes, e.g.
        a host's own constants).
    **fields
        Any of ``value``, ``fixed``, ``bounds``, ``bounds_on``, ``link``.
        ``link=None`` unlinks.

    Raises
    ------
    TypeError
        For a field name that is not one of the above.
    """
    for name, content in fields.items():
        if name not in _FIELDS:
            raise TypeError(f"edit_parameter: unknown field {name!r}")
        setattr(parameter, name, content)


def restore_parameter_value(parameter: Any, value: Any) -> None:
    """Set a value on a parameter even if it is fixed, keeping it fixed.

    Used when replaying saved state: a fixed parameter must take its saved
    value but stay fixed afterwards.
    """
    was_fixed = bool(getattr(parameter, "fixed", False))
    parameter.fixed = False
    parameter.value = value
    parameter.fixed = was_fixed


def update_fit(fit: Any) -> None:
    """Recompute a fit (group or member) from its current inputs.

    ``fit.update()`` publishes ``fit.updated`` on the event bus, which is how a
    window showing the fit learns to redraw.
    """
    fit.update()


def set_fit_range(fit: Any, xmin: int, xmax: int, *, update: bool = False) -> None:
    """Set a fit's ``fit_range`` to ``(xmin, xmax)``, optionally recomputing it."""
    fit.fit_range = (xmin, xmax)
    if update:
        fit.update()


def set_parameter_array(parameter: Any, values: Any) -> None:
    """Write the whole array of a vector-valued parameter (its port value)."""
    parameter._port.value = values


def run_fit(fit: Any) -> Any:
    """Run a fit's optimiser and return what ``fit.run()`` returns."""
    return fit.run()


def set_current_fit(fit: Any) -> None:
    """Point the session's current fit at *fit* (no-op when no session exists)."""
    import chisurf as cs

    session = getattr(cs, "cs", None)
    if session is not None:
        session.current_fit = fit


def add_dataset(dataset: Any) -> None:
    """Append *dataset* to the session's imported datasets."""
    from chisurf.core.api import dataset_container

    dataset_container().append(dataset)


def move_dataset(dataset: Any, new_index: int) -> None:
    """Move *dataset* to position *new_index* in the session's imported datasets."""
    from chisurf.core.api import dataset_container

    container = dataset_container()
    container.pop(container.index(dataset))
    container.insert(new_index, dataset)
