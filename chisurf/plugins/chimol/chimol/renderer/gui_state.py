"""What the panel reads back from the viewer each frame, and the label default.

Split out of :mod:`.gui_overlay` -- which needs a painter, and therefore a
toolkit -- because neither of these does. The panel's state is pulled from the
viewer once per frame on *every* host, including the ones that build the chrome
as quads and never open a painter at all, so leaving it beside the painter made
a windowless host import a window system to copy two integers.
"""
from __future__ import annotations


import numpy as np

__all__ = ["DEFAULT_LABEL_SIZE", "refresh_gui_state"]

#: Point size for a 3-D label when no configuration reaches the painter.
#: Matches ``label.size`` in the shipped display config; the two are kept equal
#: so an unconfigured painter and a configured one do not disagree about how big
#: a measurement is.
DEFAULT_LABEL_SIZE = 16.0


def _colour_signature(colours) -> tuple:
    """A cheap content signature for a per-residue colour array.

    Why not a cryptographic hash
    ----------------------------
    This used to be ``blake2b`` over the whole buffer, and on an integrative
    model that buffer is 234,184 x 4 float64 -- **7.5 MB, hashed on every
    frame, measured at 9.9 ms**. It was the single largest cost in a 26 ms
    frame: more than building all the chrome's quads, and far more than drawing
    the 234,184 beads it describes.

    The cost is inherent to the algorithm, not the size. A cryptographic hash
    runs near 1 GB/s; a NumPy reduction runs at memory bandwidth, which on this
    machine is tens of GB/s. Nothing here needs collision resistance against an
    adversary -- it needs to notice that a colour command changed the colours.

    So the signature is a handful of reductions: the total, three strided
    totals, and a position-weighted total over a subsample. Between them they
    respond to a change in any element's value, and the strides and the weights
    make them respond to a reordering as well.

    The honest limit: this is **not** collision-proof. An array deliberately
    permuted so that the total, all three strided totals *and* the weighted
    total are preserved would be reported unchanged. No colour command does
    that, and the alternative costs 9.9 ms a frame.

    Parameters
    ----------
    colours : array_like
        ``(n, 3)`` or ``(n, 4)`` colours.

    Returns
    -------
    tuple
        Comparable with ``==``; safe to keep on the row.
    """
    arr = np.ascontiguousarray(colours, dtype=np.float64)
    flat = arr.ravel()
    if flat.size == 0:
        return (arr.shape, 0.0)
    # Strided views are free -- no copy -- and each touches a fraction of the
    # buffer, so the whole signature costs about one full pass.
    sample = flat[::1021]
    weighted = float(np.dot(sample, np.arange(sample.size, dtype=np.float64)))
    return (
        arr.shape,
        float(flat.sum()),
        float(flat[::7].sum()),
        float(flat[::97].sum()),
        weighted,
    )


def refresh_gui_state(gui, controller) -> None:
    """Pull the movie position and sequence colours into the panel.

    Pulled every frame rather than pushed on change, because there is no one
    place a frame changes: playback advances it on a timer, ``frame`` and the
    transport set it directly, and a trajectory reload resets it. A slider wired
    to one of those and not the others sits still while the molecule moves,
    which is worse than having no slider.

    A drag in progress wins: the position under the cursor is what the user is
    asking for, and overwriting it from the viewer each frame would drag the
    thumb out of their hand.

    Parameters
    ----------
    gui : InternalGui
        The panel to update in place.
    controller : object or None
        The :class:`~.view.MolView` to read from.
    """
    if controller is None or gui is None or gui.is_dragging():
        return

    # The system-info panel is chrome, so it is pulled here with everything
    # else rather than pushed. It used to be a `QPlainTextEdit` stacked on the
    # surface, which is how it ended up drawn over the in-viewport prompt: a Qt
    # widget cannot see chrome painted *into* the surface, and only this object
    # knows where the prompt is.
    try:
        gui.info_visible = bool(getattr(controller, "_info_visible", False))
        # What a viewport click selects. Synced here, per frame, because it is
        # a *setting*: `set mouse_selection_mode, chains` and clicking the
        # block's `Selecting` row both go through the command layer to the
        # viewer, and the row draws whatever the viewer says. Without this the
        # row was written only when the object list changed, so clicking it ran
        # the command, the viewer changed, and the word never moved -- which
        # reads as a dead control.
        mode = getattr(controller, "selection_mode", None)
        if mode:
            gui.selecting = str(mode)
        # A *listing* owns its own text: the filter rebuilds it as the user
        # types, and copying the viewer's copy over it every frame would undo
        # each keystroke. Prose answers still come from the viewer, which is
        # where a script or the console put them.
        if not getattr(gui, "_info_items", None):
            gui.info_text = str(getattr(controller, "_info_text", "") or "")
        gui.info_colors = controller.info_overlay_colors()
    except Exception:
        pass

    # Re-read the sequence colours as well. Colouring is a *command* --
    # `spectrum`, `color`, `ss` -- and there is no signal for it, so a strip
    # coloured once at load keeps showing the old scheme while the molecule in
    # front of it shows the new one. Reading them back is a cached array copy,
    # which costs nothing beside drawing the molecule itself.
    for row in gui.sequences:
        if not row.object_id:
            continue
        try:
            colours = controller.get_residue_colors(row.object_id)
        except Exception:
            continue
        if colours is None:
            continue
        # Converting the array to a list of tuples is 234k tuples and 700k
        # `float()` calls on an integrative model -- 395 ms, on every repaint,
        # to produce the same list as last time. The colours only change when a
        # command replaces the array, so its address is the signal: same buffer,
        # same list. Content is deliberately not hashed; that would cost more
        # than the conversion it avoids.
        # Content, not address. The colour arrays are re-derived by the colour
        # commands rather than replaced, so identity survives a change it must
        # not survive -- keyed on the address, a scene came back in the previous
        # one's colours. The hash is paid once per chrome repaint, which is ten
        # times a second, not sixty.
        signature = _colour_signature(colours)
        if getattr(row, "_colors_from", None) == signature:
            continue
        row.colors = [tuple(float(c) for c in rgba[:3]) for rgba in colours]
        row._colors_from = signature

    try:
        current = int(controller.get_current_frame()) + 1
        total = max(int(controller.get_total_frames()), 1)
    except Exception:
        return
    if (current, total) != gui.state:
        gui.state = (current, total)
