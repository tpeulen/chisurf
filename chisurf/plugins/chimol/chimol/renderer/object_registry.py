"""The object list, in one place, with a revision every view can read.

Why this exists
---------------
Everything on screen is a view of one list: the object panel, the sequence
strip, the density controls, the hierarchy tree, the Qt window's own list, and
the browser's. That list was a bare ``OrderedDict`` on the viewer, mutated by
six of the viewer's own methods and by two other modules reaching in --
and it **announced nothing**.

So every view was kept in step by whoever happened to remember. The loader
called the host, which refreshed the panel; nothing else did. The visible
result was a density map that never appeared in the object list, because
``add_volume`` creates an object and no code path from there to the panel
existed. Which in turn made the map unselectable, which made the density panel
unable to switch to it -- three symptoms of one missing signal.

Push or pull
------------
Pull. The registry does not dispatch to its consumers; consumers **read it**,
and compare :attr:`revision` to decide whether to re-read anything expensive.

That is deliberate and it is this codebase's established shape -- the same one
:meth:`~chimol.renderer.view.MolView.field_revision` already uses for per-object
state, for the same reason. Dispatching would mean every view registering a
callback, staying registered exactly as long as it is alive, and tolerating
being called mid-mutation from whichever thread got there. Every view here
already repaints on a clock; asking them to compare an integer first costs
nothing and cannot be got wrong.

The mapping is the seam
-----------------------
This is a ``MutableMapping``, so ``registry[oid] = entry``, ``registry.pop(oid)``
and ``registry.clear()`` all bump the revision. That matters more than it
looks: two modules outside the viewer mutate the object list directly
(``cmd/interactions.py`` dropping a mutagenesis preview, ``renderer/session.py``
clearing before a load), and making the *mapping protocol* the choke point
means those are correct without having to find them. A registry with named
methods and a plain dict underneath would have left both silent.
"""
from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Iterator, MutableMapping
from dataclasses import dataclass
from typing import Any

__all__ = ["Change", "ObjectRegistry"]

#: How many changes are remembered. A ring, because the history is for
#: *reading back* -- an undo stack, a provenance record, a panel that wants to
#: update the two rows that moved rather than rebuild forty -- and none of
#: those needs the whole session. Unbounded, a long session would grow a list
#: nobody reads to the end of.
DEFAULT_HISTORY = 512


@dataclass(frozen=True)
class Change:
    """One mutation of the object list.

    Attributes
    ----------
    revision : int
        The registry's revision *after* this change, so a consumer that holds
        revision *r* takes every change with ``revision > r``.
    kind : {"add", "replace", "remove", "reorder", "touch"}
        What happened. ``touch`` is a change to an entry rather than to the
        mapping -- a rename, a visibility switch -- which the mapping cannot
        see and the owner therefore reports.
    object_id : str
        Which object, empty for a change to the list as a whole.
    detail : str
        A word for whoever is reading: which field was touched, or the new
        order's length. Deliberately a string: this is a log, not an API.
    payload : object
        What is needed to *undo* this change, and nothing else: the entry that
        was removed, the entry an addition replaced, the order that a reorder
        replaced. ``None`` for a change that cannot be inverted -- a visibility
        touch, whose old value the registry never saw.
    label : str
        One line for a human reading the list. Built here so the panel, the log
        and an undo prompt say the same words.
    """

    revision: int
    kind: str
    object_id: str = ""
    detail: str = ""
    payload: Any = None
    label: str = ""

    @property
    def undoable(self) -> bool:
        """Whether :meth:`ObjectRegistry.undo` can invert this one."""
        return self.kind in ("add", "remove", "replace", "reorder")


def _name_of(entry: Any, fallback: str) -> str:
    """What to call an entry in a line a person reads."""
    name = str(getattr(entry, "name", "") or "")
    return name or str(fallback)


class ObjectRegistry(MutableMapping):
    """An ordered map of object id to entry, counting its own changes.

    Attributes
    ----------
    revision : int
        Bumped by every mutation -- an addition, a removal, a reorder, a
        rename, a visibility change. Monotonic, and never reset: a view holds
        the last value it acted on and re-reads when the two differ.
    """

    __slots__ = ("_entries", "_history", "_recording", "_redo", "_undo", "revision")

    def __init__(self, entries: dict | None = None, history: int = DEFAULT_HISTORY) -> None:
        self._entries: OrderedDict[str, Any] = OrderedDict(entries or {})
        self.revision = 0
        self._history: deque[Change] = deque(maxlen=max(int(history), 0) or None)
        #: The invertible changes, newest last, and the ones undone from it.
        #: Separate from `_history`, which is everything that happened and is
        #: for *reading*: a visibility touch belongs in the log and cannot be
        #: undone, because the registry never saw the value it replaced.
        self._undo: list[Change] = []
        self._redo: list[Change] = []
        #: False while an undo or a redo is being applied. The inverse must not
        #: be recorded as a new change, or undoing once would push a change
        #: that undoing again would undo -- the classic loop.
        self._recording = True

    # -- the mapping, which is also where the change signal lives ----------
    def __getitem__(self, key: str) -> Any:
        return self._entries[key]

    def __setitem__(self, key: str, value: Any) -> None:
        # A replacement counts: an object rebuilt in place is a different
        # object to every view that draws it.
        replaced = self._entries.get(key)
        kind = "replace" if key in self._entries else "add"
        self._entries[key] = value
        self.touch(kind, str(key), payload=replaced,
                   label=f"{'replace' if kind == 'replace' else 'add'} {_name_of(value, key)}")

    def __delitem__(self, key: str) -> None:
        removed = self._entries[key]
        position = list(self._entries).index(key)
        del self._entries[key]
        # The entry *and* where it was: putting it back at the end would
        # reorder the list, which is a second change nobody asked for.
        self.touch("remove", str(key), payload=(removed, position),
                   label=f"remove {_name_of(removed, key)}")

    def __iter__(self) -> Iterator[str]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: object) -> bool:
        return key in self._entries

    def __repr__(self) -> str:
        return f"ObjectRegistry({list(self._entries)!r}, revision={self.revision})"

    # -- the operations that are not a mapping's -------------------------
    def touch(self, kind: str = "touch", object_id: str = "", detail: str = "",
              payload: Any = None, label: str = "") -> int:
        """Record that the list changed, and return the new revision.

        Public because a caller that mutates an *entry* in place -- renaming
        it, hiding it -- changes what the views draw without touching the
        mapping. Those go through the viewer's own setters, which call this.

        Every mutation lands here, which is what makes a history possible at
        all: one place to record from, rather than a hook at each of the six
        methods and two outside modules that change the list.
        """
        self.revision += 1
        change = Change(
            revision=self.revision, kind=str(kind), object_id=str(object_id),
            detail=str(detail), payload=payload,
            label=str(label or f"{kind} {object_id or detail}".strip()),
        )
        self._history.append(change)
        if self._recording and change.undoable:
            self._undo.append(change)
            # A new change after an undo ends that branch, as every undo stack
            # does: the redos described a future that no longer follows.
            self._redo.clear()
        return self.revision

    # -- the history -------------------------------------------------------
    def history(self) -> tuple:
        """Every remembered change, oldest first."""
        return tuple(self._history)

    def changes_since(self, revision: int) -> tuple:
        """The changes after *revision*, oldest first.

        What a consumer asks instead of rebuilding: a panel holding revision
        *r* can learn that one row was added and one renamed, rather than that
        "something" happened. Returns everything remembered when *revision* is
        older than the ring -- the honest answer being "more than I kept", and
        a caller that cannot use a partial history should rebuild.
        """
        return tuple(c for c in self._history if c.revision > int(revision))

    def forgot_before(self) -> int:
        """The oldest revision still in the history, or 0 when nothing is.

        A consumer compares this with its own revision: if it is behind, the
        history it would get back has holes and a rebuild is the correct move.
        """
        return int(self._history[0].revision - 1) if self._history else 0

    # -- undo and redo -----------------------------------------------------
    def can_undo(self) -> bool:
        """Whether there is an invertible change to take back."""
        return bool(self._undo)

    def can_redo(self) -> bool:
        """Whether an undone change can be put back."""
        return bool(self._redo)

    def undo(self) -> Change | None:
        """Invert the most recent invertible change, and return it.

        Only the list is inverted -- an object comes back where it was, an
        added one goes away again. What was *inside* an object is the
        coordinate ring's business (`renderer/undo.py`), which is a separate
        stack because it is a separate question: "put that object back" and
        "put those atoms back" are not the same act, and PyMOL keeps them
        apart too.
        """
        if not self._undo:
            return None
        change = self._undo.pop()
        self._apply_inverse(change)
        self._redo.append(change)
        return change

    def redo(self) -> Change | None:
        """Re-apply the most recently undone change, and return it."""
        if not self._redo:
            return None
        change = self._redo.pop()
        self._apply_forward(change)
        self._undo.append(change)
        return change

    def _apply_inverse(self, change: Change) -> None:
        """Undo one change, without recording the inverse as a new one."""
        self._recording = False
        try:
            if change.kind == "add":
                self._entries.pop(change.object_id, None)
            elif change.kind == "remove":
                entry, position = change.payload
                self._insert_at(change.object_id, entry, position)
            elif change.kind == "replace":
                self._entries[change.object_id] = change.payload
            elif change.kind == "reorder":
                self._entries = OrderedDict(
                    (oid, self._entries[oid])
                    for oid in change.payload
                    if oid in self._entries
                )
            self.touch("undo", change.object_id, change.kind,
                       label=f"undo {change.label}")
        finally:
            self._recording = True

    def _apply_forward(self, change: Change) -> None:
        """Re-apply one change, without recording it again."""
        self._recording = False
        try:
            if change.kind == "add":
                # The entry itself is not kept for an addition -- there is
                # nothing to keep, the object was made by whoever made it. A
                # redo therefore restores the *slot*, which is what the panel
                # and the scene read; a caller wanting more should not have
                # undone it.
                pass
            elif change.kind == "remove":
                self._entries.pop(change.object_id, None)
            self.touch("redo", change.object_id, change.kind,
                       label=f"redo {change.label}")
        finally:
            self._recording = True

    def _insert_at(self, key: str, value: Any, position: int) -> None:
        """Put *key* back at *position*, rather than at the end."""
        items = list(self._entries.items())
        items.insert(max(0, min(int(position), len(items))), (key, value))
        self._entries = OrderedDict(items)

    def reorder(self, object_ids) -> None:
        """Reorder in place, keeping any ids the caller did not mention.

        In place, and that is the point: rebinding the viewer's attribute to a
        fresh ``OrderedDict`` -- which is what the two reordering methods used
        to do -- throws away the registry, and with it the revision every view
        is comparing against. The next change then looks like the first one.
        """
        wanted = [oid for oid in object_ids if oid in self._entries]
        rest = [oid for oid in self._entries if oid not in wanted]
        ordered = OrderedDict((oid, self._entries[oid]) for oid in wanted + rest)
        if list(ordered) == list(self._entries):
            return
        previous = list(self._entries)
        self._entries = ordered
        self.touch("reorder", "", f"{len(ordered)} entries",
                   payload=previous, label="reorder the list")
