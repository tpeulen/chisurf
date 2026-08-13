"""cmtk -- the chimol toolkit. One name, one package, drawn through one
painter: every in-viewport control chimol has, ported out of the Dear ImGui
ecosystem.

:mod:`.painter` is the interface everything below draws against;
:mod:`.qt_painter` is the reference implementation and the before-half of the
port, :mod:`.quad_painter` the GPU one. Neither is imported eagerly --
``qt_painter`` needs a GUI toolkit, and the point of this package is that the
chrome does not.

The widgets
-----------
:mod:`.widgets` holds the first nineteen. Most of the rest are a port of Dear
ImGui's widget stack (``junk/imgui``), one module per section of its
``imgui_widgets.cpp`` so a control can be read against the source it came
from:

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

Two widget families came from elsewhere in the same ecosystem, and are ported
the same way against their own sources:

==================== ===================================================
:mod:`.text_editor`  a colourising, multi-cursor code editor, from
                     ``junk/ImGuiColorTextEdit``
:mod:`.memory_editor` a hex viewer over RAM or VRAM, from
                     ``junk/imgui_club``'s ``imgui_memory_editor``
==================== ===================================================

Porting another widget is meant to be mechanical rather than heroic: see
:mod:`.control` for the base class that supplies the contract below, and
``build_tools/dev_utils/port_imgui_widget.py`` for the scaffolder that lifts a
C++ widget's enums, palettes, option struct and keyword tables into Python and
writes the module, the test and the gallery page around them.

What every widget agrees on
----------------------------
A widget is a **retained object**: it keeps its state and its hit test in the
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

Beyond widgets: plotting
------------------------
The same painter also carries a port out of the wider Dear ImGui ecosystem
that is not a widget in the sense above: :mod:`.plot` (a port of
`epezent/implot <https://github.com/epezent/implot>`_ -- axes, line and
scatter series, a legend, built through :func:`begin_plot`). It needed one
thing the original nineteen-plus widgets never had: a diagonal edge, which is
why :class:`~.painter.Painter` carries an eighth-ish operation,
:meth:`~.painter.Painter.fill_triangle`, atop the original six. See
``okf/plugins/chimol-cmtk.md`` for the full account and
``okf/prds/prd-104.md`` for the phased scope (implot3d's surfaces/meshes and
the rest of implot's plot types are not ported yet; a view-orientation gizmo
was tried and removed -- also recorded there).

cmtk is the one name for all of this -- not a second "tk" package with a
"cmtk" alias, and not a second renderer: every shape here, widget or plot,
is drawn through the same :class:`~.painter.Painter`.

Everything is drawn through :class:`~.painter.Painter`'s operations, so the
controls run unchanged on desktop quads, on Qt, and in the browser.
"""
from __future__ import annotations

from .axis import Axis, nice_ticks
from .markers import MARKERS, draw_marker
from .painter import (
    ALIGN_CENTER,
    ALIGN_HCENTER,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    ALIGN_VCENTER,
    Colour,
    Painter,
)
from .plot import DEEP_PALETTE, Plot, begin_plot
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
    "Axis",
    "nice_ticks",
    "MARKERS",
    "draw_marker",
    "DEEP_PALETTE",
    "Plot",
    "begin_plot",
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
    "text_editor",
    "memory_editor",
    "control",
    "axis",
    "markers",
    "plot",
)


def __getattr__(name: str):
    """Resolve a ported control lazily, from whichever family owns it.

    Why lazily, and why not ``from .tables import *`` at the top: importing
    twenty-odd modules to put one slider on screen costs every host that time,
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
        rather than only the ones that are imported eagerly.
    """
    import importlib

    names = set(__all__) | {"CONTROL_MODULES"}
    for module_name in CONTROL_MODULES:
        module = importlib.import_module(f".{module_name}", __name__)
        names.update(getattr(module, "__all__", ()))
    return sorted(names)
