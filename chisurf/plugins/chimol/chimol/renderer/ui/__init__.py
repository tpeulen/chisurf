"""The in-viewport chrome's drawing layer, and the controls drawn with it.

:mod:`.painter` is the interface the chrome draws against; :mod:`.qt_painter`
is the reference implementation and the before-half of the port. Neither is
imported eagerly -- ``qt_painter`` needs a GUI toolkit, and the point of this
package is that the chrome does not.

The controls
------------
:mod:`.widgets` holds the first nineteen. The rest are a port of Dear ImGui's
widget stack (``junk/imgui``), one module per section of its
``imgui_widgets.cpp`` so a control can be read against the source it came from:

============  ========================================================
:mod:`.text`      ``Text``/``Colored``/``Disabled``/``Wrapped``, ``LabelText``,
                  ``Bullet``, ``BulletText``, ``SeparatorText``, ``TextLink``,
                  ``Value``
:mod:`.buttons`   ``SmallButton``, ``InvisibleButton``, ``ArrowButton``,
                  ``CheckboxFlags``, ``RadioButton``
:mod:`.sliders`   ``SliderInt``, the vertical and angle forms, the N-component
                  rows, and logarithmic scaling
:mod:`.drag`      the drag-to-edit numerics -- the family chimol had none of
:mod:`.inputs`    ``InputFloat``/``Double``/``ScalarN``, hint fields, multiline
:mod:`.color`     ``ColorButton``, the RGB/HSV editors, the SV+hue pickers
:mod:`.combo`     ``ComboBox`` -- the real drop-down list, as distinct from
                  :class:`~.widgets.Combo`, which cycles in place
:mod:`.selection` ``Selectable``, ``CollapsingHeader``, multi- and type-select
:mod:`.menus`     ``MenuItem``, ``Menu``, ``MenuBar``, ``Popup``, ``PopupModal``
:mod:`.tabs`      width-measured, shrinkable, scrollable, reorderable tab bars
:mod:`.tables`    the ``imgui_tables.cpp`` subsystem: sizing policies, resize,
                  reorder, multi-sort, hiding, frozen panes
:mod:`.dragdrop`  drag-and-drop payloads and the hover-delay tooltip
:mod:`.layout`    the cursor -- rows, ``same_line``, indent, groups, columns
:mod:`.style`     the palette and the arithmetic all of them share
============  ========================================================

What every control agrees on
----------------------------
A control is a **retained object**: it keeps its state and its hit test in the
same place as its drawing, so a host that owns neither a widget tree nor a
layout pass can put one on screen by constructing it, drawing it into a box,
and handing it the presses that land in that box::

    control.draw(painter, x, y, w, h)
    control.press(px, py, x, y, w, h)   # -> something the caller can act on
    control.drag(px, py, x, y, w, h)    # if it is draggable
    control.release()                   # if it holds

That is the one paradigm. The reference is immediate-mode around a per-frame
global context; chimol is immediate-mode in *style* and retained in
*implementation*, and there is deliberately no second path. Where the
reference reads that context for something chimol has no feed for -- hover, a
clock, a modifier key, a click count -- the port takes it as an **explicit
argument** rather than growing a global to read it from.

Everything is drawn through :class:`~.painter.Painter`'s six operations, so the
controls run unchanged on desktop quads, on Qt, and in the browser.
"""
from __future__ import annotations

from .painter import (
    ALIGN_CENTER,
    ALIGN_HCENTER,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    ALIGN_VCENTER,
    Colour,
    Painter,
)
from .widgets import (
    Button,
    Checkbox,
    ColorEdit4,
    Combo,
    Histogram,
    InputInt,
    ListBox,
    PlotLines,
    ProgressBar,
    RadioGroup,
    ScrollBar,
    Separator,
    SliderFloat,
    Table,
    Tabs,
    TextInput,
    Toggle,
    Tooltip,
    TreeNode,
    fit_text,
)

__all__ = [
    "ALIGN_CENTER",
    "ALIGN_HCENTER",
    "ALIGN_LEFT",
    "ALIGN_RIGHT",
    "ALIGN_VCENTER",
    "Colour",
    "Painter",
    "Button",
    "Checkbox",
    "ColorEdit4",
    "Combo",
    "Histogram",
    "InputInt",
    "ListBox",
    "PlotLines",
    "ProgressBar",
    "RadioGroup",
    "ScrollBar",
    "Separator",
    "SliderFloat",
    "Table",
    "Tabs",
    "TextInput",
    "Toggle",
    "Tooltip",
    "TreeNode",
    "fit_text",
]

#: The ported families, by module name. Kept as data because it is what the
#: gallery, the documentation generator and the atlas guard all enumerate --
#: three places that would otherwise each keep their own list and each miss a
#: different new module.
CONTROL_MODULES = (
    "widgets",
    "text",
    "combo",
    "buttons",
    "sliders",
    "drag",
    "inputs",
    "color",
    "selection",
    "menus",
    "tabs",
    "tables",
    "dragdrop",
    "layout",
)


def __getattr__(name: str):
    """Resolve a ported control lazily, from whichever family owns it.

    Why lazily, and why not ``from .tables import *`` at the top: importing
    thirteen modules to put one slider on screen costs every host that time,
    and the browser build pays it on load. The families are independent, so a
    name is resolved by asking each in turn and the module is imported only
    when something actually reaches for one of its controls.

    Parameters
    ----------
    name : str
        The attribute being looked up.

    Returns
    -------
    object
        The control class or helper, which is then cached on the module so the
        search happens once per name.

    Raises
    ------
    AttributeError
        If no family exports it.
    """
    import importlib

    for module_name in CONTROL_MODULES:
        module = importlib.import_module(f".{module_name}", __name__)
        if name in getattr(module, "__all__", ()):
            value = getattr(module, name)
            globals()[name] = value
            return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list:
    """List the eagerly-exported names plus every ported control.

    Returns
    -------
    list of str
        Sorted names, so tab-completion in the console sees the whole toolkit
        rather than only the nineteen that are imported eagerly.
    """
    import importlib

    names = set(__all__) | {"CONTROL_MODULES"}
    for module_name in CONTROL_MODULES:
        module = importlib.import_module(f".{module_name}", __name__)
        names.update(getattr(module, "__all__", ()))
    return sorted(names)
