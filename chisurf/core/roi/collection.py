"""An ordered, named collection of regions — the thing a GUI actually edits.

A single :class:`~chisurf.core.roi.roi.ROI` answers "is this inside?". What a
user works with is a *list* of them: several named regions, some switched off
for the moment, one or two inverted, combined into the selection that drives the
analysis. Every tool that offered more than one region grew its own version of
that list, and they disagreed:

* the CLSM tool kept a ``{name: ROI}`` dict with add/apply/remove/save/load and
  no way to combine two regions, although the core supports ``&``/``|``/``~``;
* ndX kept a ``DataSelection`` hierarchy whose members carry exactly
  ``name`` + ``enabled`` + ``invert`` and are combined by implicit AND, with the
  **opposite mask convention** (``True`` = excluded) and a save/load that
  silently dropped every selection that was not a rectangle;
* the molecule-MLE and pixel-MLE tools accepted several regions from a file and
  quietly unioned them, with no way to see or change that.

This module is the one type behind all three: an ordered list of
:class:`RegionEntry` — a region, a name, an ``enabled`` flag and an ``invert``
flag — plus the rule for reducing them to one region. It is Qt-free on purpose;
the widget in :mod:`chisurf.gui.widgets.roi` edits it, and a headless script or
an RPC service uses the same object with no GUI in sight.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

import numpy as np

from .roi import ROI, CompositeROI, as_roi, roi_from_dict

#: How the enabled members are reduced to a single region.
COMBINE_OPS = ("and", "or", "xor")


@dataclasses.dataclass
class RegionEntry:
    """One region in a collection, with the state a UI needs to show for it.

    Attributes
    ----------
    roi : ROI
        The region itself.
    enabled : bool
        Whether it takes part in the combination. A disabled entry is kept, not
        deleted — switching a region off to see what it was doing is the most
        common thing a user does with a list of them.
    invert : bool
        Whether the region contributes its *complement*. This is ndX's
        per-selection "invert" and the core's ``~`` operator; keeping it as a
        flag rather than wrapping the region means the underlying geometry is
        still there to edit after the user toggles it.
    """

    roi: ROI
    enabled: bool = True
    invert: bool = False

    @property
    def name(self) -> str:
        """The region's name (stored on the region itself, not duplicated)."""
        return self.roi.name

    @name.setter
    def name(self, value: str) -> None:
        self.roi.name = str(value)

    def effective(self) -> ROI:
        """Return the region as it contributes: inverted when :attr:`invert`."""
        return ~self.roi if self.invert else self.roi

    def to_dict(self) -> dict[str, Any]:
        """Serialise the entry, region included."""
        return {
            "roi": self.roi.to_dict(),
            "enabled": bool(self.enabled),
            "invert": bool(self.invert),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RegionEntry:
        """Rebuild an entry from :meth:`to_dict`."""
        return cls(
            roi=roi_from_dict(data["roi"]),
            enabled=bool(data.get("enabled", True)),
            invert=bool(data.get("invert", False)),
        )


class RegionCollection:
    """An ordered, named list of regions that reduces to one region.

    The collection is a sequence: iterate it, index it, ``len`` it. Names are
    unique — adding a region whose name is taken gets a numbered suffix, because
    two rows reading ``cell`` in a list is a worse outcome than ``cell (2)``.

    Parameters
    ----------
    entries : iterable of RegionEntry or ROI, optional
        Initial contents. Bare regions are wrapped in enabled, non-inverted
        entries.
    combine : {"and", "or", "xor"}, optional
        How enabled members are reduced. ``"and"`` — the intersection — is the
        default because that is what stacking gates means: each one narrows the
        selection further. ``"or"`` is the right choice for a set of separately
        drawn objects (three cells, five beads).
    name : str, optional
        Label for the combined region.

    Examples
    --------
    >>> from chisurf.core.roi import RectangleROI, RegionCollection
    >>> c = RegionCollection(combine="or")
    >>> c.add(RectangleROI(0, 0, 10, 10, name="left"))
    'left'
    >>> c.add(RectangleROI(20, 20, 30, 30, name="right"))
    'right'
    >>> len(c)
    2
    >>> import numpy as np
    >>> c.combined().contains(np.array([[5.0, 5.0], [25.0, 25.0], [15.0, 15.0]]))
    array([ True,  True, False])

    Switching one off changes the answer without losing it:

    >>> c.set_enabled('right', False)
    >>> c.combined().contains(np.array([[25.0, 25.0]]))
    array([False])
    >>> len(c)
    2
    """

    def __init__(
        self,
        entries: Iterable[Any] | None = None,
        combine: str = "and",
        name: str = "",
    ) -> None:
        """Initialize the collection."""
        self.combine = combine
        self.name = str(name)
        self._entries: list[RegionEntry] = []
        for item in entries or []:
            if isinstance(item, RegionEntry):
                self._append(item)
            else:
                self.add(item)

    # --- sequence protocol -------------------------------------------------
    def __len__(self) -> int:
        """Return the number of regions, enabled or not."""
        return len(self._entries)

    def __iter__(self) -> Iterator[RegionEntry]:
        """Iterate the entries in order."""
        return iter(self._entries)

    def __getitem__(self, key: Any) -> RegionEntry:
        """Return an entry by position or by name."""
        if isinstance(key, str):
            entry = self.get(key)
            if entry is None:
                raise KeyError(key)
            return entry
        return self._entries[key]

    def __contains__(self, name: object) -> bool:
        """Whether a region of this name is present."""
        return any(e.name == name for e in self._entries)

    @property
    def combine(self) -> str:
        """How enabled members are reduced — one of :data:`COMBINE_OPS`."""
        return self._combine

    @combine.setter
    def combine(self, value: str) -> None:
        """Set the reduction, rejecting an operation the core cannot apply."""
        op = str(value).lower()
        if op not in COMBINE_OPS:
            raise ValueError(f"unknown combine {value!r}; expected one of {list(COMBINE_OPS)}")
        self._combine = op

    @property
    def names(self) -> list[str]:
        """The region names, in order."""
        return [e.name for e in self._entries]

    # --- editing -----------------------------------------------------------
    def _unique(self, name: str) -> str:
        """Return *name*, suffixed if it is taken."""
        base = name or "region"
        if base not in self:
            return base
        index = 2
        while f"{base} ({index})" in self:
            index += 1
        return f"{base} ({index})"

    def _append(self, entry: RegionEntry) -> str:
        entry.name = self._unique(entry.name)
        self._entries.append(entry)
        return entry.name

    def add(self, region: Any, name: str = "", **flags: Any) -> str:
        """Add a region and return the name it was stored under.

        Parameters
        ----------
        region : RegionEntry or ROI or dict or numpy.ndarray
            Anything :func:`~chisurf.core.roi.roi.as_roi` accepts, so a bare
            mask or a serialised region can be added directly. An entry from
            another collection is taken with its flags, so collections can be
            merged without unpacking them at every call site.
        name : str, optional
            Overrides the region's own name.
        **flags
            ``enabled`` and/or ``invert``.

        Returns
        -------
        str
            The stored name, which differs from the requested one when that was
            already taken.
        """
        if isinstance(region, RegionEntry):
            entry = RegionEntry(
                roi=region.roi,
                enabled=flags.get("enabled", region.enabled),
                invert=flags.get("invert", region.invert),
            )
            if name:
                entry.name = str(name)
            return self._append(entry)
        roi = as_roi(region)
        if roi is None:
            raise ValueError("cannot add an empty region")
        if name:
            roi.name = str(name)
        return self._append(RegionEntry(roi=roi, **flags))

    def extend(self, regions: Iterable[Any]) -> list[str]:
        """Add several regions, returning the names they were stored under."""
        return [self.add(r) for r in regions]

    def get(self, name: str) -> RegionEntry | None:
        """Return the entry of this name, or ``None``."""
        return next((e for e in self._entries if e.name == name), None)

    def roi(self, name: str) -> ROI | None:
        """Return the region of this name, or ``None``."""
        entry = self.get(name)
        return entry.roi if entry is not None else None

    def remove(self, name: str) -> bool:
        """Remove a region by name; return whether it was there."""
        entry = self.get(name)
        if entry is None:
            return False
        self._entries.remove(entry)
        return True

    def clear(self) -> None:
        """Remove every region."""
        self._entries.clear()

    def rename(self, name: str, new_name: str) -> str:
        """Rename a region, returning the name actually used."""
        entry = self.get(name)
        if entry is None:
            raise KeyError(name)
        if new_name == name:
            return name
        self._entries.remove(entry)
        entry.name = self._unique(str(new_name))
        self._entries.append(entry)
        return entry.name

    def move(self, name: str, index: int) -> None:
        """Move a region to a new position in the order."""
        entry = self[name]
        self._entries.remove(entry)
        self._entries.insert(max(0, min(index, len(self._entries))), entry)

    def set_enabled(self, name: str, enabled: bool) -> None:
        """Switch a region on or off without removing it."""
        self[name].enabled = bool(enabled)

    def set_invert(self, name: str, invert: bool) -> None:
        """Make a region contribute its complement, or stop doing so."""
        self[name].invert = bool(invert)

    # --- the combined region ------------------------------------------------
    @property
    def enabled(self) -> list[RegionEntry]:
        """The entries currently taking part."""
        return [e for e in self._entries if e.enabled]

    def combined(self) -> ROI | None:
        """Return the single region the enabled members reduce to.

        Returns
        -------
        ROI or None
            ``None`` when nothing is enabled — which is *not* the same as "the
            whole frame". A caller that wants "no restriction" must treat
            ``None`` that way itself; returning an all-true region here would
            make an empty collection indistinguishable from one whose regions
            the user deliberately switched off.
        """
        parts = [e.effective() for e in self.enabled]
        if not parts:
            return None
        if len(parts) == 1:
            single = parts[0]
            if self.name and not single.name:
                single.name = self.name
            return single
        return CompositeROI(self._combine, parts, name=self.name)

    def to_mask(self, shape: Sequence[int], extent=None, image=None) -> np.ndarray:
        """Rasterise the combined region; all-true when nothing is enabled.

        This is the "which pixels?" convenience: unlike :meth:`combined` it has
        to answer with an array, and an analysis handed an empty collection runs
        on everything.
        """
        roi = self.combined()
        if roi is None:
            return np.ones(tuple(shape[:2]), dtype=bool)
        return roi.to_mask(shape, extent, image)

    def contains(self, points: np.ndarray) -> np.ndarray:
        """Gate scattered points; all-true when nothing is enabled."""
        roi = self.combined()
        points = np.atleast_2d(np.asarray(points, dtype=float))
        if roi is None:
            return np.ones(len(points), dtype=bool)
        return roi.contains(points)

    def excluded(self, points: np.ndarray) -> np.ndarray:
        """Return the *exclusion* mask — ``True`` where a point is filtered out.

        ndX's selection layer works in this convention throughout
        (``DataSelection.get_mask`` returns what to hide), and silently
        disagreeing with it is how a gate ends up inverted three call sites
        later. Naming both directions is cheaper than remembering which one a
        function meant.
        """
        return ~self.contains(points)

    # --- measuring ----------------------------------------------------------
    def properties(self, shape: Sequence[int], extent=None, image=None) -> list[Any]:
        """Measure every region, in order, against the same frame.

        Returns
        -------
        list of RegionProperties
            One per region — including disabled ones, because the list a user
            reads is the list they edit.
        """
        return [e.roi.properties(shape, extent, image=image) for e in self._entries]

    # --- serialisation ------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Serialise the whole collection, flags and order included."""
        return {
            "name": self.name,
            "combine": self._combine,
            "entries": [e.to_dict() for e in self._entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RegionCollection:
        """Rebuild a collection from :meth:`to_dict`.

        Also accepts a bare list of serialised regions, so a plain regions file
        loads as a collection with everything enabled.
        """
        if isinstance(data, (list, tuple)):
            return cls(entries=[roi_from_dict(d) for d in data])
        collection = cls(combine=data.get("combine", "and"), name=data.get("name", ""))
        for entry in data.get("entries", []):
            collection._append(RegionEntry.from_dict(entry))
        return collection

    def save(self, path: str) -> str:
        """Write the collection to a JSON file.

        Parameters
        ----------
        path : str
            Destination; ``.json`` is expected.

        Returns
        -------
        str
            The path written.
        """
        import json

        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"chisurf_regions": 2, **self.to_dict()}, handle, indent=1)
        return path

    @classmethod
    def load(cls, path: str) -> RegionCollection:
        """Read a collection from a file.

        Accepts a collection written by :meth:`save`, a plain regions file
        written by :func:`~chisurf.core.roi.io.save_rois`, a mask image or a
        label image — the last two through the shared loader, so a segmentation
        arrives as one entry per object rather than one merged blob.
        """
        import json
        import pathlib

        if pathlib.Path(path).suffix.lower() == ".json":
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict) and "entries" in data:
                return cls.from_dict(data)

        from .io import load_regions

        return cls(entries=load_regions(path), combine="or")

    def __repr__(self) -> str:
        """Return a short description naming the regions."""
        parts = ", ".join(
            f"{'' if e.enabled else '-'}{'~' if e.invert else ''}{e.name}" for e in self._entries
        )
        return f"RegionCollection({self._combine}: {parts})"


__all__ = ["RegionCollection", "RegionEntry", "COMBINE_OPS"]
