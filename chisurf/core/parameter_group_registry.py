"""Process-global registry of parameter groups that live *outside* ``chisurf.fits``.

The Global View shows every :class:`~chisurf.core.fitting.parameter.FittingParameter`
so a user can view, edit and cross-link parameters. Most parameters belong to a
:class:`~chisurf.core.fitting.fit.Fit` reachable through ``chisurf.fits``, but some
live in a working model held by a plugin (e.g. the FCS Filter Calculator's
``LifetimeModel`` or the FRET-Line tool's model). Those groups are not in
``chisurf.fits`` and no fit index points at them.

This module lets such a plugin *register* its working group so the Global View can
enumerate it alongside the fits. Registered groups are ordinary
:class:`~chisurf.core.fitting.parameter.FittingParameterGroup` instances, so their
parameters already carry a ``unique_identifier`` and are resolvable process-wide via
:meth:`chisurf.core.base.Base.find_by_uuid` — which is what makes them fully linkable
to fit parameters through the same RPC path.

The store is keyed by a stable ``owner_id`` (a plugin-chosen string). Re-registering
the same ``owner_id`` *replaces* the previous group: a plugin that rebuilds its model
on every recompute keeps one stable slot. Groups are held weakly, so a group that is
garbage-collected drops out on its own; unregistering also breaks any parameter links
into or out of the group so no dangling follower is left pointing at a dead master.

See Also
--------
chisurf.core.base.Base.find_by_uuid : Global UUID lookup used to resolve parameters.
"""

from __future__ import annotations

import weakref
from typing import Any, Callable, List, Optional, Tuple

from chisurf import logging

__all__ = [
    "register_parameter_group",
    "unregister_parameter_group",
    "iter_registered_parameter_groups",
    "get_registered_parameter_group",
    "break_links",
    "subscribe",
    "unsubscribe",
]


#: owner_id -> (weakref to group, label). Kept module-global so both the GUI (in
#: process) and the in-process server dispatch can enumerate the same registry.
_REGISTRY: "dict[str, Tuple[weakref.ReferenceType, str]]" = {}

#: Change-notification callbacks invoked (with no arguments) after any mutation.
_SUBSCRIBERS: "List[Callable[[], None]]" = []


def _notify() -> None:
    """Invoke every change subscriber, swallowing individual failures."""
    for cb in list(_SUBSCRIBERS):
        try:
            cb()
        except Exception:
            logging.exception("parameter_group_registry: change subscriber failed")


def subscribe(callback: Callable[[], None]) -> Callable[[], None]:
    """Register a zero-argument callback fired after any registry mutation.

    Parameters
    ----------
    callback : callable
        Invoked (with no arguments) whenever a group is registered or
        unregistered. The same callable is only added once.

    Returns
    -------
    callable
        The registered ``callback`` (for convenience / later
        :func:`unsubscribe`).
    """
    if callback not in _SUBSCRIBERS:
        _SUBSCRIBERS.append(callback)
    return callback


def unsubscribe(callback: Callable[[], None]) -> None:
    """Remove a previously :func:`subscribe`-d change callback.

    Parameters
    ----------
    callback : callable
        The callback to remove. A callback that is not currently registered is
        ignored.
    """
    try:
        _SUBSCRIBERS.remove(callback)
    except ValueError:
        pass


def register_parameter_group(group: Any, *, owner_id: str, label: str) -> None:
    """Register (or replace) an out-of-fit parameter group for the Global View.

    Parameters
    ----------
    group : FittingParameterGroup
        The parameter group to expose. Held by a weak reference; the caller must
        keep its own strong reference for as long as the group should stay
        visible.
    owner_id : str
        Stable identifier for the owning tool/plugin. Registering an ``owner_id``
        that is already present *replaces* the previous group (the previous
        group's dangling links are broken first).
    label : str
        Human-readable label shown in the Global View's *Owner* column.

    Raises
    ------
    ValueError
        If ``owner_id`` is empty.
    """
    if not owner_id:
        raise ValueError("owner_id must be a non-empty string")
    # Replacing an existing owner: break links against the old group first.
    if owner_id in _REGISTRY:
        _break_group_links(_deref(owner_id))
    _REGISTRY[owner_id] = (weakref.ref(group), str(label))
    _notify()


def unregister_parameter_group(owner_id: str) -> None:
    """Remove a registered group and break any links into/out of it.

    Parameters
    ----------
    owner_id : str
        The identifier passed to :func:`register_parameter_group`. Unknown ids
        are ignored.
    """
    entry = _REGISTRY.pop(owner_id, None)
    if entry is None:
        return
    group = entry[0]()
    if group is not None:
        _break_group_links(group)
    _notify()


def get_registered_parameter_group(owner_id: str) -> Optional[Any]:
    """Return the live group registered under ``owner_id``, or ``None``.

    Parameters
    ----------
    owner_id : str
        The identifier passed to :func:`register_parameter_group`.

    Returns
    -------
    FittingParameterGroup or None
        The live group, or ``None`` if the id is unknown or the group has been
        garbage-collected (in which case the stale entry is pruned).
    """
    entry = _REGISTRY.get(owner_id)
    if entry is None:
        return None
    group = entry[0]()
    if group is None:
        _REGISTRY.pop(owner_id, None)
    return group


def iter_registered_parameter_groups() -> List[Tuple[str, str, Any]]:
    """Return the live registered groups as ``(owner_id, label, group)`` tuples.

    Entries whose group has been garbage-collected are pruned in passing, so the
    returned list only contains live groups.

    Returns
    -------
    list of (str, str, FittingParameterGroup)
        One tuple per live registered group, in insertion order.
    """
    result: List[Tuple[str, str, Any]] = []
    dead: List[str] = []
    for owner_id, (ref, label) in _REGISTRY.items():
        group = ref()
        if group is None:
            dead.append(owner_id)
            continue
        result.append((owner_id, label, group))
    for owner_id in dead:
        _REGISTRY.pop(owner_id, None)
    return result


def _deref(owner_id: str) -> Optional[Any]:
    """Return the live group for ``owner_id`` without pruning or notifying."""
    entry = _REGISTRY.get(owner_id)
    return entry[0]() if entry is not None else None


def _break_group_links(group: Any) -> None:
    """Sever every link into or out of ``group`` (see :func:`break_links`).

    Parameters
    ----------
    group : FittingParameterGroup or None
        The group being removed. ``None`` is a no-op.
    """
    if group is None:
        return
    try:
        own_params = list(getattr(group, "parameters_all", []) or [])
    except Exception:
        own_params = []
    break_links(own_params, exclude_group=group)


def break_links(parameters: Any, exclude_group: Any = None) -> None:
    """Sever parameter links so removing ``parameters`` leaves no dangling followers.

    Both directions are handled: a parameter being removed that follows some
    master is unlinked, and any follower pointing *at* one of them is unlinked
    — a follower whose master is gone would otherwise read a value nothing
    updates any more. Failures are swallowed so teardown stays best-effort.

    Parameters
    ----------
    parameters : iterable of Parameter
        The parameters going away (a whole group, or the rows of one component
        a host is deleting).
    exclude_group : FittingParameterGroup, optional
        A registered group not to scan for followers — the one the parameters
        belong to, whose own links this call has already cleared.
    """
    own_params = list(parameters or [])
    own_ids = {id(p) for p in own_params}

    # Outbound: params in the group that follow some master -> unlink.
    for p in own_params:
        try:
            if getattr(p, "is_linked", False):
                p.link = None
        except Exception:
            logging.exception("parameter_group_registry: failed to clear outbound link")

    # Inbound: external followers whose master is one of our params -> unlink.
    import chisurf as _cs

    def _all_followers():
        for fit in list(getattr(_cs, "fits", []) or []):
            for local in ([fit] + list(getattr(fit, "grouped_fits", []) or [])):
                model = getattr(local, "model", None)
                for p in getattr(model, "parameters_all", []) or []:
                    yield p
        for _oid, _label, g in iter_registered_parameter_groups():
            if exclude_group is not None and g is exclude_group:
                continue
            for p in getattr(g, "parameters_all", []) or []:
                yield p

    for follower in _all_followers():
        try:
            master = getattr(follower, "link", None)
            if master is not None and id(master) in own_ids:
                follower.link = None
        except Exception:
            logging.exception("parameter_group_registry: failed to clear inbound link")
