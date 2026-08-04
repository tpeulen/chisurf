"""The ``?`` and **Guide** buttons, for *any* tool window.

Two questions a scientific tool has to answer, and they are not the same one:

``?``
    what does this control *mean*. Long-form help, behind a small button so it
    does not eat panel space (the house rule).
**Guide**
    which control do I touch *first*. A dense panel of well-documented settings
    is still unusable without that; the guided tour points at one real widget at
    a time and waits for the user to press it.

Both used to live on :class:`~chisurf.gui.widgets.tools.chisurf_dock_tool.ChisurfDockTool`,
which meant a tool could only have them by inheriting a base class it may have
no other use for — the ~30 tools built on a plain ``QMainWindow``/``QWidget`` or
on :class:`~chisurf.gui.widgets.navigation.NavigationPanelTool` had no seam at
all. They live here now, as a mixin plus a free function, so *every* tool can
have them however it is built.

Three ways in, in order of how little you have to write:

**Nothing at all.** Mix :class:`HelpGuideMixin` into the window class and call
:meth:`~HelpGuideMixin.ensure_help_toolbar` (``NavigationPanelTool`` and
``ChisurfDockTool`` already do). It looks for ``help.md`` and ``guide.json``
beside the tool's own module and adds whichever it finds. A plugin gets both
buttons by shipping two files and changing no code.

**One call.** A tool that builds its own toolbar calls
:meth:`~HelpGuideMixin.add_toolbar_help`, which right-aligns the ``?`` and adds
**Guide** beside it when a tour exists.

**A free function.** :func:`attach_help_and_guide` does the same for a window
that cannot take the mixin — an already-built ``QDialog``, or a widget tree
assembled from a ``.ui`` file.

Resource resolution
-------------------
A relative ``help.md``/``guide.json`` is looked for, in order, next to

1. the model's view spec (``model._view_json``) — an AutoForm tool,
2. the model's module directory,
3. **the tool class's own module directory** — which is what makes this work for
   a tool with no model at all, since ``gui/tool.py`` sits beside ``gui/help.md``.

That third base is why a plain ``QMainWindow`` plugin needs no ``resource``
argument: the files are already where the class is.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any

from qtpy import QtWidgets

__all__ = [
    "HelpGuideMixin",
    "attach_help_and_guide",
    "promote_to_toolbar",
    "resolve_tool_resource",
]

#: Default file names looked for beside a tool's module.
HELP_RESOURCE = "help.md"
GUIDE_RESOURCE = "guide.json"


def resolve_tool_resource(
    resource: str,
    model: Any = None,
    owner: Any = None,
) -> pathlib.Path | None:
    """Resolve a tool resource path to an existing file.

    Parameters
    ----------
    resource : str
        Absolute, CWD-relative, or view-spec-relative path.
    model : object, optional
        Model whose ``_view_json`` (else module directory) anchors a relative
        path.
    owner : object, optional
        The tool instance or class whose module directory is the last anchor
        tried. This is the one that works for a tool with no model.

    Returns
    -------
    pathlib.Path or None
        The existing file, or ``None`` when nothing matched.
    """
    if not resource:
        return None
    path = pathlib.Path(resource)
    if path.is_file():
        return path
    if path.is_absolute():
        return None

    bases: list[pathlib.Path] = []

    def _add_module_dir(obj: Any) -> None:
        if obj is None:
            return
        cls = obj if isinstance(obj, type) else type(obj)
        module_file = getattr(sys.modules.get(getattr(cls, "__module__", ""), None), "__file__", None)
        if module_file:
            bases.append(pathlib.Path(module_file).parent)

    view_json = getattr(model, "_view_json", None)
    if view_json:
        bases.append(pathlib.Path(view_json).parent)
    _add_module_dir(model)
    # The owner's *whole* MRO, not just its class: a tool that subclasses another
    # plugin's tool (the imaging-map family does) should still find the help
    # shipped with the class that actually defines the panel.
    if owner is not None:
        owner_cls = owner if isinstance(owner, type) else type(owner)
        for klass in getattr(owner_cls, "__mro__", (owner_cls,)):
            _add_module_dir(klass)

    for base in bases:
        candidate = base / path
        if candidate.is_file():
            return candidate
    # Some plugins point ``entrypoints.gui`` at the package itself rather than at
    # ``gui/tool.py``, so the anchor lands one level above where the GUI files
    # live. The house convention is that everything describing the GUI sits under
    # ``gui/`` beside the view spec, so look there too rather than making those
    # plugins scatter their help at the package root.
    for base in bases:
        candidate = base / "gui" / path
        if candidate.is_file():
            return candidate
    return None


def promote_to_toolbar(
    form: QtWidgets.QWidget,
    toolbar: QtWidgets.QToolBar,
    actions: list[str] | tuple[str, ...],
) -> list[QtWidgets.QWidget]:
    """Move a form's primary action buttons up into the tool's toolbar.

    A toolbar carrying nothing but ``?`` and **Guide** is a band of chrome, and
    a *Run* button buried three panels down a settings column is the control the
    user needs most and finds last. Both problems have the same fix: the tool's
    **primary actions** belong on the strip.

    Only the ones that make sense. A button scoped to a section — *Add row*,
    *Remove*, *Apply to this field* — reads as nonsense on a window-level bar and
    stays where it is; this takes an explicit list rather than everything it can
    find, so that judgement is made per tool and is visible in the call.

    Buttons are matched on the ``action`` their view spec names, not on their
    label: a label is a translation and a decoration away from changing.

    Parameters
    ----------
    form : QtWidgets.QWidget
        The built ``AutoForm`` (or any widget tree holding the buttons).
    toolbar : QtWidgets.QToolBar
        Destination. Buttons are appended in the order *actions* gives, which is
        usually not the order the form declared them in.
    actions : sequence of str
        The ``action`` names to promote.

    Returns
    -------
    list of QtWidgets.QWidget
        The relocated buttons, in the order they were added.
    """
    found: dict[str, QtWidgets.QWidget] = {}
    for button in form.findChildren(QtWidgets.QAbstractButton):
        action = getattr(button, "_autoform_action", "")
        if action in actions and action not in found:
            found[action] = button

    moved: list[QtWidgets.QWidget] = []
    for action in actions:
        button = found.get(action)
        if button is None:
            continue
        # Remember the row it came from: a button row that has given up all its
        # buttons is a stray gap in the form with a stretch in it.
        row = button.parentWidget()
        toolbar.addWidget(button)  # reparents
        moved.append(button)
        # Hide it only when *nothing* is left — not merely no buttons. A custom
        # section may pair its action with a status label (the FLCS simulator
        # does), and hiding the container took the status line with it: the
        # button moved, and the result it reports disappeared.
        if row is not None and not row.findChildren(QtWidgets.QWidget):
            row.hide()
    return moved


class HelpGuideMixin:
    """Adds the ``?`` and **Guide** buttons to a tool window.

    Mix in *before* the Qt base class::

        class MyTool(HelpGuideMixin, QtWidgets.QMainWindow):
            ...

    The mixin holds no state of its own beyond the two button handles and the
    running tour, and never touches the filesystem until a button is built, so
    mixing it in costs a tool nothing.
    """

    #: Title of the help modal; override per tool for a nicer window title.
    help_title: str = "Help"

    # -- the one-call entry points --------------------------------------------

    def ensure_help_toolbar(
        self,
        *,
        help_resource: str = HELP_RESOURCE,
        guide_resource: str = GUIDE_RESOURCE,
        title: str = "",
        model: Any | None = None,
        toolbar: QtWidgets.QToolBar | None = None,
    ) -> QtWidgets.QToolBar | None:
        """Attach ``?``/**Guide** to *toolbar*, creating a slim one if needed.

        This is the zero-code path: a tool calls it once and gets whichever
        buttons its shipped files justify. A tool with neither ``help.md`` nor
        ``guide.json`` gets **no toolbar at all** rather than an empty strip —
        the buttons must never cost panel space to a tool that has nothing to
        put behind them.

        Parameters
        ----------
        help_resource, guide_resource : str
            File names looked for beside the tool (see the module docstring).
        title : str
            Help-modal title; defaults to :attr:`help_title`, else the window
            title.
        model : object, optional
            Model used to resolve relative resources and a step's ``action``.
        toolbar : QtWidgets.QToolBar, optional
            Existing toolbar to append to. When omitted a slim, non-movable one
            is created on the window (requires a ``QMainWindow``).

        Returns
        -------
        QtWidgets.QToolBar or None
            The toolbar carrying the buttons, or ``None`` when the tool ships
            neither file.
        """
        owner = model if model is not None else getattr(self, "model", None)
        help_path = resolve_tool_resource(help_resource, owner, self)
        guide_path = resolve_tool_resource(guide_resource, owner, self)
        if help_path is None and guide_path is None:
            return None

        if toolbar is None:
            toolbar = self._create_help_toolbar()
            if toolbar is None:
                return None

        if guide_path is not None:
            self.add_toolbar_guide(toolbar, resource=str(guide_path), model=owner)
        if help_path is not None:
            self.add_toolbar_help(
                toolbar,
                resource=str(help_path),
                title=title or getattr(self, "help_title", "") or self.windowTitle() or "Help",
                model=owner,
            )
        return toolbar

    def _create_help_toolbar(self) -> QtWidgets.QToolBar | None:
        """Create the slim top toolbar the buttons live on.

        Kept separate so a window with an unusual layout can override *where*
        the strip goes without reimplementing what goes on it. Returns ``None``
        when the window is not a ``QMainWindow`` — such a tool must pass its own
        container instead, or use :func:`attach_help_and_guide`.
        """
        if not isinstance(self, QtWidgets.QMainWindow):
            return None
        toolbar = QtWidgets.QToolBar("Help", self)
        toolbar.setObjectName("chisurf_help_toolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(toolbar.iconSize().boundedTo(toolbar.iconSize()))
        # A hairline strip: it carries two small buttons and must not read as a
        # band of empty chrome above the tool's own content.
        toolbar.setStyleSheet("QToolBar { border: none; padding: 0px; spacing: 2px; }")
        self.addToolBar(toolbar)
        self._help_toolbar = toolbar
        return toolbar

    # -- toolbar help ----------------------------------------------------------

    def add_toolbar_help(
        self,
        toolbar: QtWidgets.QToolBar,
        *,
        resource: str = "",
        text: str = "",
        title: str = "Help",
        model: Any | None = None,
    ) -> QtWidgets.QWidget:
        """Right-align a ``?`` button in *toolbar* that opens the help modal.

        The house rule is that long help lives behind a small ``?`` button, not
        in an inline text block that eats panel space. This puts that button
        where it belongs — the far right of the tool's own toolbar — reusing the
        same modal the AutoForm ``help`` section uses. Markdown links in that
        help are live: a documentation page opens in the ChiSurf documentation
        browser, a URL or a DOI in the system browser
        (:mod:`chisurf.gui.widgets.tools.doc_links`).

        It also adds a **Guide** button to the left of the ``?`` whenever the
        tool ships a ``guide.json`` beside its view spec, so a tool gets a guided
        tour by writing one file and changing no code — see
        :meth:`add_toolbar_guide`.

        Parameters
        ----------
        toolbar : QtWidgets.QToolBar
            Toolbar to append the spacer + button to.
        resource : str
            Help file (``.md``/``.txt``/``.html``). A *relative* path is resolved
            next to the model's view spec, else beside the tool's own module, so
            a plugin ships it beside its ``view.json``.
        text : str
            Inline help body; wins over ``resource`` when given.
        title : str
            Modal window title.
        model : object, optional
            Model used to resolve a relative ``resource`` (defaults to
            ``self.model``).

        Returns
        -------
        QtWidgets.QWidget
            The button widget added to the toolbar.
        """
        from chisurf.gui.autoform.sections.help_section import HelpButton

        owner = model if model is not None else getattr(self, "model", None)
        # Every tool that has a help button gets a guide button too, provided it
        # ships a tour — so adding one to a tool is a matter of writing
        # ``guide.json`` beside its view spec, with no code change anywhere. That
        # is what makes this a ChiSurf-wide facility rather than a feature of
        # whichever plugin remembered to ask for it.
        if getattr(self, "_guide_button", None) is None:
            self.add_toolbar_guide(toolbar, model=owner)
        self._add_toolbar_right_spacer(toolbar)
        # A relative resource is resolved here rather than left to the button,
        # because the button only knows about the *model* — and a tool with no
        # model at all still ships ``help.md`` beside its own module.
        resolved = resolve_tool_resource(resource, owner, self) if resource else None
        button = HelpButton(
            owner,
            resource=str(resolved) if resolved is not None else resource,
            text=text,
            title=title,
            # NOT ``align="right"``. That makes the button widget add a stretch
            # of its own *inside* itself, which then competes with the toolbar's
            # right-aligning spacer — the two share the slack and strand **Guide**
            # in the middle of the bar with ``?`` at the far end, instead of the
            # adjacent pair the layout is meant to produce. The toolbar spacer
            # already does the right-aligning for both.
            align="none",
        )
        toolbar.addWidget(button)
        self._help_button = button
        return button

    def add_toolbar_guide(
        self,
        toolbar: QtWidgets.QToolBar,
        *,
        resource: str = GUIDE_RESOURCE,
        steps: Any = None,
        label: str = "Guide",
        tooltip: str = "Walk me through this tool, one control at a time",
        model: Any | None = None,
    ) -> QtWidgets.QWidget | None:
        """Add a guide button that walks the user through this tool.

        The companion to :meth:`add_toolbar_help`, and the answer to a different
        question. Help explains what a control *means*; a guide says which
        control to touch **first**, points at it, and waits while the user
        presses it. A dense panel of well-documented settings is still unusable
        if nothing says where to start.

        The button sits immediately left of the ``?``, so the two live together
        at the top right of every tool. Call it before :meth:`add_toolbar_help`;
        the right-aligning stretch is added once per toolbar by whichever runs
        first, so the two buttons stay adjacent instead of being pushed to
        opposite ends by two competing stretches.

        Parameters
        ----------
        toolbar : QtWidgets.QToolBar
            Toolbar to append the button to.
        resource : str
            Tour definition file. A *relative* path is resolved next to the
            model's view spec, else beside the tool's own module. See
            :mod:`chisurf.gui.widgets.tools.guided_tour` for the format.
        steps : sequence, optional
            Ready-made steps, used in preference to *resource*.
        label : str
            Button text. Plain text rather than a glyph on purpose: the compass
            emoji is not in every fallback font and renders as a missing-glyph
            box, which is worse than a word next to the ``?``.
        tooltip : str
            Button tooltip.
        model : object, optional
            Model used to resolve a relative *resource* and a step's ``action``
            (defaults to ``self.model``).

        Returns
        -------
        QtWidgets.QWidget or None
            The button, or ``None`` when no tour could be found — a tool with no
            tour gets no button rather than a button that does nothing.
        """
        from chisurf.gui.widgets.tools.guided_tour import GuidedTour, load_tour

        owner = model if model is not None else getattr(self, "model", None)
        tour_steps = list(steps) if steps else []
        if not tour_steps and resource:
            path = resolve_tool_resource(resource, owner, self)
            if path is not None:
                tour_steps = load_tour(path)
        if not tour_steps:
            return None

        self._add_toolbar_right_spacer(toolbar)
        button = QtWidgets.QToolButton()
        button.setText(str(label))
        button.setToolTip(str(tooltip))
        button.setAutoRaise(True)
        toolbar.addWidget(button)

        host = self.tour_host()

        def _start() -> None:
            tour = getattr(host, "_guided_tour", None)
            if tour is not None:
                tour.stop()
            tour = GuidedTour(host, tour_steps, model=owner)
            # Kept on the *window*, not on this mixin holder: the tour is the
            # window's, and a test or a caller looking for a running tour looks
            # at the widget it is running over.
            host._guided_tour = tour
            tour.start()

        button.clicked.connect(_start)
        self._guide_button = button
        return button

    def tour_host(self) -> QtWidgets.QWidget:
        """Return the widget a tour spotlights over — normally the tool itself.

        Overridden by the holder :func:`attach_help_and_guide` uses, which is not
        a widget: the tour has to run over the real window, and handing it a
        plain Python object raises inside ``QObject.__init__``.
        """
        return self

    @staticmethod
    def _add_toolbar_right_spacer(toolbar: QtWidgets.QToolBar) -> None:
        """Add the expanding spacer that right-aligns the trailing buttons, once.

        Two stretches in one toolbar do not stack — they share the slack, which
        would put the guide button in the middle of the bar instead of beside
        the help button. The flag lives on the toolbar so the rule holds however
        many trailing buttons a tool adds.
        """
        if toolbar.property("_chisurf_right_spacer"):
            return
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )
        toolbar.addWidget(spacer)
        toolbar.setProperty("_chisurf_right_spacer", True)

    def _resolve_tool_resource(self, resource: str, model: Any) -> pathlib.Path | None:
        """Resolve a tool resource path (see :func:`resolve_tool_resource`)."""
        return resolve_tool_resource(resource, model, self)


class _AttachedHelpGuide(HelpGuideMixin):
    """Carries the mixin for a window that cannot inherit it.

    The mixin's state lives here and the *window* is what the tour spotlights,
    so a ``QDialog`` or a ``.ui``-built widget gets the same buttons without
    changing its class.
    """

    def __init__(self, window: QtWidgets.QWidget, model: Any = None) -> None:
        self._window = window
        self.model = model
        self._guide_button = None
        self._help_button = None
        self._guided_tour = None

    def tour_host(self) -> QtWidgets.QWidget:
        """The real window: this holder is not a widget."""
        return self._window

    def __getattr__(self, name: str) -> Any:
        """Fall back to the window for anything this holder does not define."""
        return getattr(self._window, name)


def attach_help_and_guide(
    window: QtWidgets.QWidget,
    toolbar: QtWidgets.QToolBar | QtWidgets.QLayout,
    *,
    help_resource: str = HELP_RESOURCE,
    guide_resource: str = GUIDE_RESOURCE,
    title: str = "",
    model: Any = None,
    owner: Any = None,
) -> tuple[QtWidgets.QWidget | None, QtWidgets.QWidget | None]:
    """Add ``?``/**Guide** to a window that cannot take :class:`HelpGuideMixin`.

    For an already-built ``QDialog``, a ``.ui``-loaded widget tree, or any tool
    whose class you would rather not touch. The buttons behave identically; only
    the way they are attached differs.

    Parameters
    ----------
    window : QtWidgets.QWidget
        The window the tour spotlights and the help modal parents to.
    toolbar : QtWidgets.QToolBar or QtWidgets.QLayout
        Where the buttons go. A ``QToolBar`` gets the usual right-aligned pair; a
        layout gets the two widgets appended.
    help_resource, guide_resource : str
        File names looked for beside *owner* (default: *window*'s class).
    title : str
        Help-modal title; defaults to the window title.
    model : object, optional
        Model used to resolve relative resources and a step's ``action``.
    owner : object, optional
        Anchors relative resource lookup; defaults to *window*.

    Returns
    -------
    tuple
        ``(guide_button, help_button)``, either of which is ``None`` when the
        corresponding file is not shipped.
    """
    helper = _AttachedHelpGuide(window, model)
    anchor = owner if owner is not None else window
    help_path = resolve_tool_resource(help_resource, model, anchor)
    guide_path = resolve_tool_resource(guide_resource, model, anchor)
    if help_path is None and guide_path is None:
        return None, None

    # Keep the helper alive for as long as the window: it owns the running tour,
    # and a garbage-collected helper would take a tour down mid-step.
    window._chisurf_help_guide = helper  # noqa: SLF001 (deliberate attachment)

    def _publish() -> None:
        """Mirror the button handles onto the window itself.

        The mixin leaves ``_guide_button`` / ``_help_button`` on the tool, so a
        test — or a *Help ▸ About* menu item wanting to open the one help modal
        — finds them there. A tool wired through this function is the same kind
        of tool from the outside and must expose the same handles, or every
        caller needs to know which of the two routes attached it.
        """
        window._guide_button = getattr(helper, "_guide_button", None)  # noqa: SLF001
        window._help_button = getattr(helper, "_help_button", None)  # noqa: SLF001

    if isinstance(toolbar, QtWidgets.QToolBar):
        guide = (
            helper.add_toolbar_guide(toolbar, resource=str(guide_path), model=model)
            if guide_path is not None
            else None
        )
        help_button = (
            helper.add_toolbar_help(
                toolbar,
                resource=str(help_path),
                title=title or window.windowTitle() or "Help",
                model=model,
            )
            if help_path is not None
            else None
        )
        _publish()
        return guide, help_button

    # A plain layout: build the same two widgets and append them.
    from chisurf.gui.autoform.sections.help_section import HelpButton
    from chisurf.gui.widgets.tools.guided_tour import GuidedTour, load_tour

    # One stretch, before both buttons, so the pair ends up adjacent at the
    # right — the same reason the toolbar path adds its spacer exactly once.
    if hasattr(toolbar, "addStretch"):
        toolbar.addStretch(1)

    guide = None
    if guide_path is not None:
        steps = load_tour(guide_path)
        if steps:
            guide = QtWidgets.QToolButton()
            guide.setText("Guide")
            guide.setToolTip("Walk me through this tool, one control at a time")
            guide.setAutoRaise(True)

            def _start() -> None:
                tour = getattr(window, "_guided_tour", None)
                if tour is not None:
                    tour.stop()
                tour = GuidedTour(window, steps, model=model)
                window._guided_tour = tour  # noqa: SLF001
                tour.start()

            guide.clicked.connect(_start)
            toolbar.addWidget(guide)
    help_button = None
    if help_path is not None:
        help_button = HelpButton(
            model,
            resource=str(help_path),
            title=title or window.windowTitle() or "Help",
            align="none",
        )
        toolbar.addWidget(help_button)
    helper._guide_button = guide  # noqa: SLF001
    helper._help_button = help_button  # noqa: SLF001
    _publish()
    return guide, help_button
