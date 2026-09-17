"""Every AutoForm is restorable from JSON.

An AutoForm is generated from a view spec that says, for each control, which
attribute of the model it binds to. That is already a complete description of
where the form's state lives — so reading it back out, and putting it back in,
needs no per-plugin code. This module does it once for every form there is.

The point is not convenience. A tool whose settings cannot be written down is a
tool whose results cannot be reproduced: an analysis folder can hold the numbers
that came out while having no record of what was asked for, and the only way to
repeat it is to remember. Restorability belongs to the form framework, not to
whichever plugin author thought of it.

**What is captured.** Every section carrying an ``attr`` — values, choices,
toggles, toggle rows — read from ``model.<target>.<attr>`` or ``model.<attr>``,
recursively through panels, dock areas and wizard steps. Sections that bind an
*action* rather than an attribute are skipped: they are commands, not state.
Parameter groups, tables and plots are skipped too — they hold results or are
owned by a model that serialises itself.

**What is deliberately lenient.** Applying a state ignores keys that no longer
exist, and keeps going when one field rejects its value. A settings file written
by an older version must restore the fields it still shares rather than failing
whole, which is the behaviour that makes saved settings worth keeping at all.
Every skip is reported in the returned summary, so a caller that cares can tell
the user precisely what did not survive.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from chisurf import logging

__all__ = [
    "StateResult",
    "iter_bound_sections",
    "collect_state",
    "apply_state",
    "save_state",
    "load_state",
]

#: Section attributes that hold nested sections.
_CHILD_FIELDS = ("sections", "steps")


@dataclass
class StateResult:
    """What happened when a stored state was applied.

    Attributes
    ----------
    applied : list of str
        Keys written to the model.
    unknown : list of str
        Keys in the file that the form has no control for — typically a settings
        file from a version that had a field this one does not.
    failed : dict
        ``{key: reason}`` for keys the model refused.
    """

    applied: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """True when every key in the file was applied."""
        return not self.unknown and not self.failed

    def summary(self) -> str:
        """One line describing the outcome, suitable for a status bar."""
        parts = [f"{len(self.applied)} setting(s) restored"]
        if self.unknown:
            parts.append(f"{len(self.unknown)} unknown")
        if self.failed:
            parts.append(f"{len(self.failed)} rejected")
        return ", ".join(parts)


def _key(section: Any) -> str | None:
    """The state key for a section, or ``None`` when it holds no state."""
    attr = getattr(section, "attr", None)
    if not attr:
        return None
    # An action-bound control is a command, not a stored value: replaying it on
    # load would re-run the action rather than restore a setting.
    if getattr(section, "set_action", ""):
        return None
    target = getattr(section, "target", None)
    return f"{target}.{attr}" if target else attr


def iter_bound_sections(sections: Iterable[Any]) -> Iterable[Any]:
    """Yield every section that binds a model attribute, depth first.

    Recurses through the containers that hold other sections (panels, dock
    areas, wizards and their steps), because a form's state is not only what is
    on the first page.
    """
    for section in sections or ():
        if _key(section) is not None:
            yield section
        for name in _CHILD_FIELDS:
            children = getattr(section, name, None)
            if children:
                yield from iter_bound_sections(children)


def _resolve_owner(model: Any, target: str | None) -> Any:
    """Return the object an ``attr`` lives on, or ``None`` when unreachable."""
    if not target:
        return model
    owner = model
    for part in str(target).split("."):
        owner = getattr(owner, part, None)
        if owner is None:
            return None
    return owner


def _jsonable(value: Any) -> Any:
    """Coerce a model value into something JSON can hold.

    numpy scalars and arrays turn up routinely in these models, and a settings
    file that cannot be written because of one of them is worse than one that
    stores it as a list.
    """
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    for attribute in ("tolist", "item"):
        method = getattr(value, attribute, None)
        if callable(method):
            try:
                return _jsonable(method())
            except Exception:
                pass
    if isinstance(value, pathlib.Path):
        return str(value)
    return str(value)


def collect_state(form: Any) -> dict[str, Any]:
    """Read the current value of every bound control on *form*.

    Parameters
    ----------
    form : AutoForm or view model
        A built form, or the model itself when there is no widget (headless) or
        when the widget is rebuilt on mode changes and the model is the stabler
        handle.

    Returns
    -------
    dict
        ``{"<target>.<attr>": value}``, JSON-safe.
    """
    model = _model_of(form)
    spec = _spec_of(form)
    if model is None or spec is None:
        return {}

    state: dict[str, Any] = {}
    for section in iter_bound_sections(getattr(spec, "sections", ())):
        key = _key(section)
        owner = _resolve_owner(model, getattr(section, "target", None))
        if owner is None:
            continue
        attr = section.attr
        if not hasattr(owner, attr):
            continue
        try:
            state[key] = _jsonable(getattr(owner, attr))
        except Exception as exc:  # pragma: no cover - defensive
            logging.debug("could not read %s: %s", key, exc)
    return state


def apply_state(form: Any, state: dict[str, Any], *, sync: bool = True) -> StateResult:
    """Write *state* back onto the form's model and refresh the widgets.

    Lenient by design: unknown keys are collected rather than raised, and one
    field refusing its value does not abandon the rest. A settings file from an
    older version should restore what it still shares.

    Parameters
    ----------
    form : AutoForm
        The form to restore.
    state : dict
        A mapping produced by :func:`collect_state`.
    sync : bool
        Refresh the widgets from the model afterwards.

    Returns
    -------
    StateResult
        What was applied, ignored and refused.
    """
    result = StateResult()
    model = _model_of(form)
    spec = _spec_of(form)
    if model is None or spec is None:
        result.unknown = sorted(state or {})
        return result

    known = {}
    for section in iter_bound_sections(getattr(spec, "sections", ())):
        known[_key(section)] = section

    for key, value in (state or {}).items():
        section = known.get(key)
        if section is None:
            result.unknown.append(key)
            continue
        owner = _resolve_owner(model, getattr(section, "target", None))
        if owner is None:
            result.failed[key] = "target not reachable on the model"
            continue
        try:
            setattr(owner, section.attr, value)
            result.applied.append(key)
        except Exception as exc:
            result.failed[key] = str(exc)

    if sync:
        # A bare model has no widgets to refresh, which is not a failure.
        refresh = getattr(form, "sync_fields", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:  # pragma: no cover - a form may not be built yet
                logging.debug("could not refresh the form after restoring", exc_info=True)
    return result


def save_state(form: Any, path: pathlib.Path | str, **extra: Any) -> pathlib.Path:
    """Write the form's state to a JSON file.

    Parameters
    ----------
    form : AutoForm
        The form to capture.
    path : path-like
        Destination; parent directories are created.
    **extra
        Additional top-level keys (e.g. a version, a title).

    Returns
    -------
    pathlib.Path
        The written path.
    """
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": "chisurf-autoform-state",
        "version": 1,
        "state": collect_state(form),
        **extra,
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


def load_state(form: Any, path: pathlib.Path | str) -> StateResult:
    """Restore a form from a JSON file written by :func:`save_state`.

    Also accepts a bare ``{key: value}`` mapping, so a state embedded in some
    other document — an analysis manifest, a project file — can be handed
    straight in without being rewrapped.
    """
    source = pathlib.Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        result = StateResult()
        result.failed["<file>"] = str(exc)
        return result
    if isinstance(payload, dict) and isinstance(payload.get("state"), dict):
        payload = payload["state"]
    if not isinstance(payload, dict):
        result = StateResult()
        result.failed["<file>"] = "not a state mapping"
        return result
    return apply_state(form, payload)


def _model_of(form: Any) -> Any:
    """The view model behind *form*, which may itself be the model.

    Callers hold whichever is stabler for them. A form that is rebuilt when its
    mode changes — the photon filter does exactly that — makes the widget a
    moving target, while the model persists; a headless caller has no widget at
    all. Both are accepted so neither has to reach for the other.
    """
    model = getattr(form, "model", None)
    if model is not None:
        return model
    # No ``.model``: this is the model, provided it can describe itself.
    if hasattr(form, "view_spec") or hasattr(form, "spec"):
        return form
    return None


def _spec_of(form: Any) -> Any:
    """The view spec behind a form or a model.

    ``AutoForm.rebuild`` reads it as ``model.view_spec()``, so that is the first
    place to look; the attribute forms are accepted too because view models are
    also constructed directly in tests and in headless callers.
    """
    candidates = []
    model = _model_of(form)
    if model is not None:
        candidates.append(getattr(model, "view_spec", None))
        candidates.append(getattr(model, "spec", None))
    for attribute in ("spec", "view_spec", "_spec"):
        candidates.append(getattr(form, attribute, None))

    for candidate in candidates:
        if candidate is None:
            continue
        if callable(candidate) and not hasattr(candidate, "sections"):
            try:
                candidate = candidate()
            except Exception:  # pragma: no cover - a model may need arguments
                continue
        if candidate is not None and hasattr(candidate, "sections"):
            return candidate
    return None
