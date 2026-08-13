"""The structure hierarchy, drawn inside the viewport.

The Qt panel is a `QTreeView` over a model with per-node check boxes, a filter
and a search box. This is the same tree drawn through the chrome's six painter
operations, so it runs on the desktop and in the browser from one
implementation — and it reads the **same `HierarchyNode` tree**, not a copy.

It carries the **search box** too. That was left out at first as "a
keyboard-focus problem of its own", and it is one -- but the chrome already
solves it for the prompt, so the answer was to generalise that rather than to
do without: :class:`~chimol.cmtk.text_field.TextField` holds the string
and the caret, and `InternalGui` owns *which* field has focus, because a key
arrives at the panel and something has to say where it goes.

Filtering matches a node when the node **or any descendant** matches, so a hit
deep in the tree is reachable rather than orphaned -- which is what the Qt
panel's `QSortFilterProxyModel` did, and the reason the filter sits between the
model and the view there: what is *typed* never touches what is *switched off*.
"""
from __future__ import annotations

import logging
from typing import Optional

from .internal_gui import GuiWindow
from ..cmtk.painter import ALIGN_LEFT, ALIGN_VCENTER
from ..cmtk.text_field import TextField

logger = logging.getLogger(__name__)

__all__ = ["HierarchyWindow"]

_TEXT = (230, 230, 230)
_DIM = (150, 150, 150)
_OFF = (120, 120, 120)
_BOX = (200, 200, 206)
_HIT = (66, 150, 250, 200)
_FIELD_BG = (30, 30, 36, 255)
_FIELD_EDGE = (110, 110, 128, 160)
_CARET = (0, 224, 0)

_ROW = 16.0
#: The scroll bar's width, and its two colours.
_BAR_W = 6.0
_TRACK = (255, 255, 255, 26)
_THUMB = (150, 150, 160, 190)
_PAD = 6.0
#: Indent per level, in pixels.
_INDENT = 12.0
#: Levels open when nothing has been clicked: the object and its chains.
_OPEN_DEPTH = 1
#: The disclosure arrow and the check box each get a square this wide.
_GLYPH = 12.0


class HierarchyWindow:
    """A structure's node tree, as a viewport window.

    Parameters
    ----------
    viewer : MolView
        Read for the tree and told which rows are hidden.
    on_change : callable, optional
        Called after a visibility change, so the host can re-apply it.
    """

    def __init__(self, viewer, on_change=None) -> None:
        self.viewer = viewer
        self.on_change = on_change
        #: Nodes the user has collapsed, and nodes the user has opened, both by
        #: id(). Two sets rather than one, because the *default* is depth-based:
        #: everything below `_OPEN_DEPTH` starts shut. That is what makes the
        #: panel usable on a nuclear pore -- fully expanded, its tree flattens
        #: to 200 000 rows and the walk cost 327 ms on **every repaint**, so the
        #: viewport stuttered while the camera moved. Shut, the first draw
        #: touches the object and its chains and nothing else.
        self._collapsed: set[int] = set()
        self._expanded: set[int] = set()
        #: Nodes switched off, by id().
        self._hidden: set[int] = set()
        self._scroll = 0
        self._rows: list = []          # (node, depth, rect) laid out while drawing
        self.search = TextField(on_change=self._on_search, placeholder="search…")
        self._search_rect: Optional[_Box] = None
        self._gui = None               # set when the window is added, for focus
        #: The flattened tree, and the state it was flattened for. Rebuilding
        #: it per frame is what made the NPC unusable: the walk is over every
        #: node, and `draw` runs on every repaint -- so a tree with a quarter of
        #: a million nodes was re-walked while the camera moved.
        self._flat: list = []
        self._flat_key: tuple = ()
        #: The synthesised object → chain → residue tree, for structures that
        #: carry no RMF hierarchy, and the object it was built for.
        self._tree = None
        self._tree_key: tuple = ()
        self._bar: Optional[_Box] = None
        self._bar_drag: Optional[tuple] = None

    # ------------------------------------------------------------------ #
    def attach(self, gui) -> None:
        """Remember the panel that owns keyboard focus."""
        self._gui = gui

    def window(self, **kwargs) -> GuiWindow:
        """A :class:`GuiWindow` wired to this panel."""
        options = dict(
            key="hierarchy", title="Hierarchy", x=24.0, y=120.0, w=300.0, h=260.0,
        )
        options.update(kwargs)
        return GuiWindow(
            body=self.draw,
            on_press=self.press,
            on_drag=self.drag,
            on_release=self.release,
            **options,
        )

    # ------------------------------------------------------------------ #
    _tree_object_id = None

    def _root(self):
        """The active object's tree.

        An RMF carries one; a PDB does not, and the panel used to answer *"No
        hierarchy"* for every ordinary structure -- which also meant the search
        box was never drawn, so "the filter does not work" was literally true:
        there was nothing to type into. So a structure without an RMF tree gets
        one built from its atom table, object → chain → residue, which is the
        tree PyMOL's own panel shows.
        """
        try:
            objects = getattr(self.viewer, "_objects", {}) or {}
            active = self.viewer.get_active_object_id()
            entry = objects.get(active)
            root = getattr(getattr(entry, "state", None), "rmf_hierarchy", None)
            if root is not None:
                self._tree_object_id = active
                return root
            for other_id, other in objects.items():
                root = getattr(getattr(other, "state", None), "rmf_hierarchy", None)
                if root is not None:
                    # The tree belongs to *this* object -- remembering that is
                    # the fix for "disabling in the hierarchy does nothing":
                    # the panel could show one object's tree (a map was
                    # active, the structure held the hierarchy) while the
                    # hiding was applied to the active object, so the switch
                    # flipped and the picture never changed.
                    self._tree_object_id = other_id
                    return root
            self._tree_object_id = active
            tree = self._chain_tree(active, entry)
            if tree is not None:
                return tree
            # The active object has no atoms (a map): fall back to the first
            # object that has some, and hide on *that* object.
            for other_id, other in objects.items():
                tree = self._chain_tree(other_id, other)
                if tree is not None:
                    self._tree_object_id = other_id
                    return tree
            return None
        except Exception:
            logger.debug("hierarchy: no tree to read", exc_info=True)
        return None

    def _chain_tree(self, object_id, entry):
        """object → chain → residue, built from an atom table. Cached.

        Cached on ``(object, atom count)``: the walk is over every atom, and
        `draw` runs on every repaint.
        """
        atoms = getattr(getattr(entry, "state", None), "atoms", None)
        if atoms is None or not len(atoms):
            return None
        names = atoms.dtype.names or ()
        key = (str(object_id), int(len(atoms)))
        if key == self._tree_key:
            return self._tree
        import numpy as np

        chain_of = (
            np.asarray(atoms["chain"]).astype(str) if "chain" in names
            else np.full(len(atoms), "", dtype=object)
        )
        res_id = (
            np.asarray(atoms["res_id"]).astype(np.int64) if "res_id" in names
            else np.zeros(len(atoms), dtype=np.int64)
        )
        res_name = (
            np.asarray(atoms["res_name"]).astype(str) if "res_name" in names
            else np.full(len(atoms), "", dtype=object)
        )

        # The *display* name, not the internal id: the object list says
        # `1rtd` and a tree rooted at `obj2` reads as a different structure.
        label = str(getattr(entry, "name", "") or object_id or "object")
        root = _Node(label, "object")
        for chain in sorted(set(chain_of.tolist())):
            in_chain = np.flatnonzero(chain_of == chain)
            node = _Node(chain or "(no chain)", "chain")
            node.atom_indices = in_chain.tolist()
            # `return_index` over an already-grouped column: the residues come
            # out in the order they appear in the file, which is the order the
            # sequence strip shows them in.
            ids = res_id[in_chain]
            _, first = np.unique(ids, return_index=True)
            for start in sorted(first.tolist()):
                rid = int(ids[start])
                rows = in_chain[ids == rid]
                leaf = _Node(f"{res_name[rows[0]]}{rid}", "residue")
                leaf.atom_indices = rows.tolist()
                node.children.append(leaf)
            root.children.append(node)

        self._tree, self._tree_key = root, key
        return root

    def _matches(self, node) -> bool:
        """Whether *node* or any descendant matches the search.

        The subtree, not the node: a match on a residue is useless if the chain
        above it is filtered away, and that is the rule the Qt panel's proxy
        model implemented.

        Iterative, not recursive: a residue-level tree is deep enough to hit
        Python's recursion limit, and a `RecursionError` inside a paint is a
        filter that "does not work" with nothing said about why.
        """
        needle = self.search.text.strip().lower()
        if not needle:
            return True
        stack = [node]
        while stack:
            current = stack.pop()
            if needle in str(getattr(current, "name", "") or "").lower():
                return True
            stack.extend(getattr(current, "children", None) or ())
        return False

    def _visible_nodes(self, root) -> list:
        """``(node, depth)`` for every row a collapsed, filtered tree shows.

        Cached on ``(root, needle, collapsed)``: those are the only things that
        change it, and the walk is over every node in the tree.
        """
        # `self._tree_key` rather than `id(root)` alone: a replaced tree is
        # freed, and CPython hands the same address to its successor -- which
        # would serve the old object's rows for the new one.
        key = (id(root), self._tree_key, self.search.text.strip().lower(),
               tuple(sorted(self._collapsed)), tuple(sorted(self._expanded)))
        if key == self._flat_key:
            return self._flat
        self._flat = self._walk(root)
        self._flat_key = key
        return self._flat

    def _walk(self, root) -> list:
        out: list = []
        filtering = bool(self.search.text.strip())

        def walk(node, depth: int, under_match: bool) -> None:
            hit = under_match or self._name_matches(node)
            if filtering and not (hit or self._matches(node)):
                return
            out.append((node, depth))
            # A filter opens the tree: a hit three levels down is not findable
            # if its ancestors are still folded, and re-folding by hand is the
            # opposite of searching.
            if not filtering and not self._is_open(node, depth):
                return
            for child in getattr(node, "children", None) or ():
                # Everything under a match is shown, not just the parts that
                # match again -- searching for a chain and getting the chain
                # with no residues in it is not the chain.
                walk(child, depth + 1, hit)

        walk(root, 0, False)
        return out

    def _is_open(self, node, depth: int) -> bool:
        """Whether *node*'s children are shown."""
        key = id(node)
        if key in self._expanded:
            return True
        if key in self._collapsed:
            return False
        return depth < _OPEN_DEPTH

    def _name_matches(self, node) -> bool:
        """Whether this node's own name matches the search."""
        needle = self.search.text.strip().lower()
        if not needle:
            return True
        return needle in str(getattr(node, "name", "") or "").lower()

    def _on_search(self, _text: str) -> None:
        """A new needle starts at the top of the results."""
        self._scroll = 0

    # ------------------------------------------------------------------ #
    def draw(self, p, rect) -> None:
        """Paint the tree, and remember where each row landed."""
        self._rows = []
        self._bar = None
        # The search box is drawn **before** the tree is looked up, so an empty
        # viewer still shows a panel you can type in rather than one sentence.
        top = self._draw_search(p, rect)
        root = self._root()
        if root is None:
            p.text(rect.x + _PAD, top, rect.w - 2 * _PAD, _ROW,
                   ALIGN_VCENTER | ALIGN_LEFT, "Nothing loaded.", _DIM)
            return

        nodes = self._visible_nodes(root)
        capacity = max(int((rect.y + rect.h - top - _PAD) // _ROW), 1)
        self._scroll = min(max(self._scroll, 0), max(len(nodes) - capacity, 0))
        text_w = self._draw_scrollbar(p, rect, top, len(nodes), capacity)

        for index, (node, depth) in enumerate(
            nodes[self._scroll: self._scroll + capacity]
        ):
            y = top + index * _ROW
            x = rect.x + _PAD + depth * _INDENT
            has_children = bool(getattr(node, "children", None))
            hidden = id(node) in self._hidden

            if has_children:
                p.text(x, y, _GLYPH, _ROW, ALIGN_VCENTER | ALIGN_LEFT,
                       "▾" if self._is_open(node, depth) else "▸", _DIM)
            # The check box, drawn rather than glyphed: a box and a tick read at
            # this size where a ☑ does not.
            box_x = x + _GLYPH
            p.stroke_rect(box_x + 2.0, y + 3.0, 9.0, 9.0, _BOX)
            if not hidden:
                p.fill_rect(box_x + 4.0, y + 5.0, 5.0, 5.0, _BOX)

            label = str(getattr(node, "name", "") or "")
            kind = str(getattr(node, "node_type", "") or "")
            if kind and kind not in label:
                label = f"{label}  ({kind})"
            p.text(
                box_x + _GLYPH + 4.0, y,
                max(text_w - (box_x - rect.x) - _GLYPH - _PAD, 1.0), _ROW,
                ALIGN_VCENTER | ALIGN_LEFT, label, _OFF if hidden else _TEXT,
            )
            self._rows.append((node, depth, _Box(rect.x, y, text_w, _ROW), x))

    # ------------------------------------------------------------------ #
    def _draw_search(self, p, rect) -> float:
        """Draw the search field; returns the y the rows start at."""
        box = _Box(rect.x + _PAD, rect.y + _PAD, rect.w - 2 * _PAD, _ROW + 2.0)
        self._search_rect = box
        focused = (
            self._gui is not None and self._gui.focused_field is self.search
        )
        p.stroke_rect(box.x, box.y, box.w, box.h, _FIELD_EDGE, fill=_FIELD_BG)
        text = self.search.text or ("" if focused else self.search.placeholder)
        p.text(box.x + 4.0, box.y, box.w - 8.0, box.h,
               ALIGN_VCENTER | ALIGN_LEFT, text,
               _TEXT if self.search.text else _DIM)
        if focused:
            # Measured from the text before it, so the caret sits between two
            # characters rather than at a guessed column.
            try:
                offset = float(p.text_width(self.search.text[: self.search.cursor]))
            except Exception:
                offset = 0.0
            p.fill_rect(box.x + 4.0 + offset, box.y + 2.0, 1.5, box.h - 4.0, _CARET)
        return box.y + box.h + 4.0

    def _draw_scrollbar(self, p, rect, top: float, total: int, capacity: int) -> float:
        """Draw the scroll bar. Returns the width the rows may use.

        A panel with a thousand rows and no bar says nothing about how much of
        it you are looking at, and the wheel is not discoverable -- so the bar
        is drawn whenever the tree is taller than the window, and it is
        draggable, because that is what a bar that only reports is missing.
        """
        if total <= capacity:
            return rect.w - 2 * _PAD
        track_x = rect.x + rect.w - _PAD - _BAR_W
        track_y = top
        track_h = max(rect.y + rect.h - _PAD - top, 1.0)
        p.fill_rect(track_x, track_y, _BAR_W, track_h, _TRACK)

        span = max(capacity / float(total), 0.0)
        thumb_h = max(track_h * span, 14.0)
        travel = max(track_h - thumb_h, 0.0)
        offset = travel * (self._scroll / float(max(total - capacity, 1)))
        p.fill_rect(track_x, track_y + offset, _BAR_W, thumb_h, _THUMB)

        self._bar = _Box(track_x - 2.0, track_y, _BAR_W + 4.0, track_h)
        self._bar_span = (total, capacity, track_y, track_h, thumb_h)
        return rect.w - 2 * _PAD - _BAR_W - 4.0

    def _scroll_to(self, y: float) -> bool:
        """Put the thumb's centre at *y*."""
        span = getattr(self, "_bar_span", None)
        if span is None:
            return False
        total, capacity, track_y, track_h, thumb_h = span
        travel = max(track_h - thumb_h, 1.0)
        fraction = (y - track_y - thumb_h / 2.0) / travel
        target = int(round(fraction * max(total - capacity, 0)))
        target = min(max(target, 0), max(total - capacity, 0))
        if target == self._scroll:
            return False
        self._scroll = target
        return True

    def drag(self, x: float, y: float, rect) -> bool:
        """Continue a scroll-bar drag."""
        if self._bar_drag is None:
            return False
        return self._scroll_to(y)

    def release(self) -> None:
        """End a scroll-bar drag."""
        self._bar_drag = None

    def press(self, x: float, y: float, rect) -> bool:
        """Expand/collapse on the arrow, switch on the box, focus the search.

        Returns whether the press starts a drag -- only the scroll bar does.
        """
        if self._bar is not None and self._bar.contains(x, y):
            self._bar_drag = (x, y)
            self._scroll_to(y)
            return True
        if self._search_rect is not None and self._search_rect.contains(x, y):
            if self._gui is not None:
                self._gui.focus_field(self.search)
            return False
        # A press anywhere else in the panel gives the caret back, so typing
        # after clicking a row reaches the shortcuts and not the search box.
        if self._gui is not None and self._gui.focused_field is self.search:
            self._gui.focus_field(None)
        for node, depth, row, indent in self._rows:
            if not row.contains(x, y):
                continue
            if x < indent + _GLYPH and getattr(node, "children", None):
                key = id(node)
                if self._is_open(node, depth):
                    self._collapsed.add(key)
                    self._expanded.discard(key)
                else:
                    self._expanded.add(key)
                    self._collapsed.discard(key)
                return False
            if x < indent + 2 * _GLYPH:
                self._toggle(node)
                return False
            return False
        return False

    def scroll(self, steps: int) -> bool:
        """Wheel over the panel."""
        before = self._scroll
        self._scroll = max(self._scroll - int(steps), 0)
        return self._scroll != before

    # ------------------------------------------------------------------ #
    def _toggle(self, node) -> None:
        """Switch a node and its descendants, then re-apply to the viewer.

        A subtree, not a row: switching off a chain has to take its residues
        with it, which is what the Qt panel's tri-state check boxes expressed.
        """
        turning_off = id(node) not in self._hidden

        def walk(current) -> None:
            key = id(current)
            if turning_off:
                self._hidden.add(key)
            else:
                self._hidden.discard(key)
            for child in getattr(current, "children", None) or ():
                walk(child)

        walk(node)
        self._apply()

    def _apply(self) -> None:
        """Hide exactly the coordinate rows the switched-off nodes cover."""
        rows: set[int] = set()
        root = self._root()
        if root is not None:
            stack = [root]
            while stack:
                node = stack.pop()
                if id(node) in self._hidden:
                    rows.update(int(i) for i in getattr(node, "atom_indices", ()) or ())
                stack.extend(getattr(node, "children", None) or ())
        if self.on_change is not None:
            try:
                self.on_change(sorted(rows),
                               getattr(self, "_tree_object_id", None))
            except Exception:
                logger.debug("hierarchy: could not apply visibility", exc_info=True)


class _Node:
    """A node of the tree synthesised for a structure with no RMF hierarchy.

    The same three attributes `HierarchyNode` exposes and this panel reads, so
    one drawing path serves both.
    """

    __slots__ = ("name", "node_type", "children", "atom_indices")

    def __init__(self, name: str, node_type: str) -> None:
        self.name = str(name)
        self.node_type = str(node_type)
        self.children: list = []
        self.atom_indices: list = []


class _Box:
    """A rectangle with ``contains``."""

    __slots__ = ("x", "y", "w", "h")

    def __init__(self, x: float, y: float, w: float, h: float) -> None:
        self.x, self.y, self.w, self.h = float(x), float(y), float(w), float(h)

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x <= self.x + self.w and self.y <= y <= self.y + self.h
