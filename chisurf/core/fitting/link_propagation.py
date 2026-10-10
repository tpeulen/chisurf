"""Push an edit through cross-fit parameter links.

A linked parameter is *pulled*: a follower reads its master's port whenever its
own model evaluates, so editing a master recomputes the fit that owns it and
leaves every fit that follows it holding the prediction of the old value until
something updates that fit too. This module is the push: given the fit an edit
recomputed, it finds every other fit whose parameters reach that fit's
parameters through a link -- directly, through a chain of links, or through an
output parameter of a fit that is itself refreshed -- and updates each of them
exactly once, masters before the followers that read them.

It is called where an edit is turned into a recomputation (the ``fit.update``
service and action, the API's local paths and the GUI's no-transport fallback),
not from :meth:`Fit.update` itself: a fit run, a scan and a sampler update a fit
thousands of times, and none of those is an edit a follower has to see.

Nothing here imports Qt.
"""

from __future__ import annotations

import typing

__all__ = ["link_followers", "refresh_link_followers"]


def _members(fit: typing.Any) -> list:
    """The local fits of *fit*: a group's members, otherwise the fit itself."""
    members = getattr(fit, "grouped_fits", None)
    return list(members) if members else [fit]


def _parameters(member: typing.Any) -> list:
    try:
        return list(getattr(getattr(member, "model", None), "parameters_all", None) or [])
    except Exception:  # noqa: BLE001 -- a model that cannot list its parameters follows nothing
        return []


def _link_chain(parameter: typing.Any) -> typing.Iterator[typing.Any]:
    """The parameters *parameter* follows, nearest first; stops on a cycle."""
    seen = {id(parameter)}
    current = getattr(parameter, "link", None)
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = getattr(current, "link", None)


def link_followers(fits: typing.Sequence[typing.Any], source: typing.Any) -> list:
    """The local fits that must be recomputed after *source* was.

    Parameters
    ----------
    fits : sequence
        The session's fits (a :class:`~chisurf.core.fitting.fit.FitGroup` counts
        by its members).
    source : Fit or FitGroup
        The fit an edit just recomputed. When it is a group, all its members
        count as recomputed.

    Returns
    -------
    list
        Every local fit, other than *source*'s own, with a parameter whose link
        chain reaches a parameter of *source* or of another fit in the result --
        each once, ordered so a fit comes after every fit in the result it
        follows. A cycle of links among the followers is broken in discovery
        order rather than refused.
    """
    done = {id(m) for m in _members(source)}
    owner_of: dict[int, typing.Any] = {}
    candidates: list = []
    for fit in list(fits or []) + [source]:
        for member in _members(fit):
            for parameter in _parameters(member):
                owner_of.setdefault(id(parameter), member)
            if id(member) not in done and all(member is not c for c in candidates):
                candidates.append(member)

    # Which local fits each candidate reads through its links.
    reads: dict[int, set] = {}
    for member in candidates:
        masters = set()
        for parameter in _parameters(member):
            for master in _link_chain(parameter):
                owner = owner_of.get(id(master))
                if owner is not None and owner is not member:
                    masters.add(id(owner))
        reads[id(member)] = masters

    # Everything reachable from the source, breadth first.
    reached = set(done)
    found: list = []
    grew = True
    while grew:
        grew = False
        for member in candidates:
            if id(member) in reached or not (reads[id(member)] & reached):
                continue
            reached.add(id(member))
            found.append(member)
            grew = True

    # Masters before followers; what a cycle leaves is taken in discovery order.
    pending = {id(m) for m in found}
    ordered: list = []
    while pending:
        ready = [m for m in found if id(m) in pending and not (reads[id(m)] & (pending - {id(m)}))]
        if not ready:
            ready = [next(m for m in found if id(m) in pending)]
        for member in ready:
            pending.discard(id(member))
            ordered.append(member)
    return ordered


def refresh_link_followers(fits: typing.Sequence[typing.Any], source: typing.Any) -> list:
    """Update every fit that follows *source* through a link, once each.

    Call after *source* itself was updated. Each follower's
    :meth:`~chisurf.core.fitting.fit.Fit.update` publishes ``fit.updated``, which
    is how a window showing it learns to redraw.

    Returns
    -------
    list
        The local fits that were updated, in update order.
    """
    import chisurf.logging

    refreshed = []
    for member in link_followers(fits, source):
        try:
            member.update()
        except Exception as e:  # noqa: BLE001 -- one broken follower must not stop the rest
            chisurf.logging.error(
                f"Could not refresh linked fit '{getattr(member, 'name', member)}': {e}"
            )
            continue
        refreshed.append(member)
    return refreshed
