"""Drop guards: let a file-drop zone object, transform, or ask before commit.

Every drop zone in ChiSurf used to go straight from ``dropEvent`` to
committing the raw dropped path. That is the wrong default in more than one
place, and differently wrong each time -- a dropped vendor photon file should
probably become a `.pto` (see the ``tttr_to_pto`` guard, registered by
:mod:`chisurf.plugins.core.tttr_to_pto.gui.guard`), a dropped legacy file
might want a rename surfaced, and so on. This module is the general
mechanism; it knows nothing about any of those cases.

The shape mirrors the existing AutoForm section registry
(:mod:`chisurf.gui.autoform.sections.registry`,
``register_section``/``get_section_factory``) on purpose: one more registry
rather than a new idiom.

A drop zone opts in **by name**, in its own view-spec/constructor options
(``guards``). ``apply_drop_guards`` with no names is a no-op that shows
nothing and returns the paths unchanged -- the pattern is opt-in per drop
zone, never a blanket hook.
"""

from __future__ import annotations

import abc
import logging
from collections.abc import Sequence
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["DropGuard", "register_drop_guard", "get_drop_guard", "apply_drop_guards"]

#: name -> a DropGuard instance, a DropGuard subclass, or a zero-arg factory.
_REGISTRY: dict[str, Any] = {}

#: Whether the built-in guards (shipped as part of ChiSurf, not third-party
#: plugins) have been imported yet. Deferred so importing this module never
#: pulls in Qt dialogs or `.pto` machinery -- only the first real use does.
_builtins_loaded = False


class DropGuard(abc.ABC):
    """One opinion about a dropped path, applied before it is committed.

    A guard is cheap to ask "do you care" (:meth:`applies`) and, only for the
    paths it accepted, gets to decide what actually gets committed
    (:meth:`resolve`) -- a converted path, the original unchanged, or the path
    dropped from the list entirely.
    """

    @abc.abstractmethod
    def applies(self, path: str) -> bool:
        """Return whether this guard cares about *path* at all.

        Cheap: a suffix check or a fast header peek, never a full parse. Called
        for every dropped path, including ones the drop zone's own extension
        filter already narrowed down.
        """

    @abc.abstractmethod
    def resolve(self, parent: Any, paths: list[str]) -> list[str]:
        """Return the paths to actually commit, in place of *paths*.

        Parameters
        ----------
        parent : QWidget or None
            Dialog parent, for a guard that asks the user something.
        paths : list of str
            Only the paths this guard's :meth:`applies` accepted, in the order
            they were dropped.

        Returns
        -------
        list of str
            Replacement paths -- a converted path, an unchanged path, or fewer
            entries than were passed in when a guard declines a path outright.
            Owns its own dialog, if any; free to ask a yes/no, a three-way
            choice, or nothing at all (e.g. a persisted "always do X").
        """


def register_drop_guard(name: str):
    """Register a :class:`DropGuard` under *name*, as a decorator.

    The decorated object may be a :class:`DropGuard` instance, a subclass (a
    zero-arg factory by virtue of being a class), or a plain zero-arg callable
    returning one -- mirroring ``register_section``'s shape exactly.
    """

    def _decorator(factory):
        _REGISTRY[name] = factory
        return factory

    return _decorator


def get_drop_guard(name: str) -> DropGuard | None:
    """Return the guard registered under *name*, instantiating a factory."""
    _ensure_builtins()
    entry = _REGISTRY.get(name)
    if entry is None:
        return None
    if isinstance(entry, DropGuard):
        return entry
    try:
        return entry()
    except Exception:
        logger.debug("drop guard %r could not be instantiated", name, exc_info=True)
        return None


def _ensure_builtins() -> None:
    """Import the guards ChiSurf ships itself, once, on first real use.

    Kept as an import rather than eager registration so a drop zone that never
    names a guard never pays for it, and so this module stays free of any
    knowledge of what a built-in guard does. Third-party/plugin guards
    register themselves however their own plugin gets imported (e.g. from
    their ``gui/tool.py`` entrypoint) and are unaffected by this.
    """
    global _builtins_loaded
    if _builtins_loaded:
        return
    _builtins_loaded = True
    try:
        import chisurf.plugins.core.tttr_to_pto.gui.guard  # noqa: F401
    except Exception:
        logger.debug("built-in tttr_to_pto drop guard unavailable", exc_info=True)


def apply_drop_guards(
    parent: Any, paths: Sequence[str], guard_names: Sequence[str] = ()
) -> list[str]:
    """Run the named guards over *paths*, in order, and return the result.

    Parameters
    ----------
    parent : QWidget or None
        Dialog parent, passed through to each guard's ``resolve``.
    paths : sequence of str
        Paths as dropped (already folder-expanded, if the drop zone does
        that).
    guard_names : sequence of str
        Guards to run, in order. Defaults to ``()`` -- a drop zone that names
        no guard gets *exactly* today's behaviour: this call becomes a no-op
        that returns *paths* unchanged and never shows anything. This is what
        makes the pattern opt-in per drop zone rather than a hidden global
        hook.

    Returns
    -------
    list of str
        The final paths to commit. A guard only ever sees (and can only ever
        transform or drop) the subset of *paths* its own :meth:`DropGuard.applies`
        accepted; paths no named guard cares about pass through untouched, in
        their original relative order.
    """
    result = list(paths)
    for name in guard_names:
        guard = get_drop_guard(name)
        if guard is None:
            logger.debug("apply_drop_guards: no guard registered as %r", name)
            continue
        indices = [i for i, p in enumerate(result) if _safe_applies(guard, p)]
        if not indices:
            continue
        accepted = [result[i] for i in indices]
        try:
            resolved = list(guard.resolve(parent, accepted))
        except Exception:
            logger.exception("drop guard %r failed to resolve %r", name, accepted)
            continue
        index_set = set(indices)
        rebuilt: list[str] = []
        spliced = False
        for i, p in enumerate(result):
            if i in index_set:
                if not spliced:
                    rebuilt.extend(resolved)
                    spliced = True
                continue
            rebuilt.append(p)
        result = rebuilt
    return result


def _safe_applies(guard: DropGuard, path: str) -> bool:
    try:
        return bool(guard.applies(path))
    except Exception:
        logger.debug("drop guard applies() failed for %r", path, exc_info=True)
        return False
