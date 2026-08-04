"""A guided tour: popup tooltips that walk the user through a tool, step by step.

A help page tells someone what a control means; it does not tell them *where the
control is* or *in what order to touch it*. That gap is where a scientific tool
loses people — the panel is full of correct, well-documented settings and there
is no way to tell which three of them matter first. A tour closes it by pointing
at one widget at a time, saying why it is there, and offering to do the step.

This module is deliberately generic. A tool declares its tour in a JSON file
beside its ``view.json`` and gets the button from
:meth:`~chisurf.gui.widgets.tools.chisurf_dock_tool.ChisurfDockTool.add_toolbar_guide`;
nothing here knows about any particular plugin. The same mechanism is meant to
be attached to every tool in ChiSurf.

A tour file is a list of steps::

    [
      {"title": "Load the demo",
       "text":  "Every other setting depends on this one.",
       "target": {"action": "Load demo"},
       "await":  {"hint": "Press the highlighted button"}},
      {"title": "Read the arrows", "target": {"title": "Flow field"}}
    ]

``target`` locates the widget to point at, by any combination of

``attr``
    the model attribute a field is bound to (``attr`` or ``target`` in the view
    spec) — the usual case;
``key``
    the ``key`` of a ``custom`` section;
``title``
    a section's ``title``;
``action``
    the text of a toolbar action, so a step can point at the button it wants
    pressed. Falls back to matching a plain button's text **or tooltip**, which
    is how the shared icon-only action bars are found — they carry their caption
    in the tooltip;
``name``
    a widget's ``objectName``, matched exactly or by suffix. The shared action
    buttons are named ``toolaction_run``, ``toolaction_add`` …, so ``{"name":
    "run"}`` points at the canonical Run button of any tool built from that
    vocabulary;
``tab``
    the label of a dock tab or ``QTabWidget`` page. ChiSurf tools are built out
    of dock tabs far more often than out of view specs, so this is what a step
    naming "Bursts" or "Summary" needs;
``panel``
    the label of a row in a
    :class:`~chisurf.gui.widgets.navigation.NavigationPanelTool`'s left
    navigation list — matched on a substring, so ``{"panel": "Burst Selection"}``
    finds the row named ``2. Burst Selection``. This is what lets a *hub* tool
    have a real tour: its steps are panels, not fields, and without it every
    step of a nav-shell guide would resolve to nothing and be shown centred —
    the slideshow a tour exists not to be. A waiting step is satisfied when the
    user selects that row.

A step with no resolvable target is shown centred on the window rather than
skipped, because a tour that silently loses steps teaches the wrong workflow.

``await`` makes a step **wait for the user to use the highlighted control**.
Next stays disabled until the target is clicked (or edited), and the bubble says
what to press. This is the difference between a tour and a demo reel: the point
is that someone learns where the buttons are by pressing them, so the tour never
offers to press one on their behalf. ``signal`` overrides the auto-detected one
(``triggered`` for a toolbar action, ``clicked`` for a button, ``valueChanged``
/ ``editingFinished`` for a field); ``hint`` replaces the default prompt.

Leaving is always one click away — ``Close`` ends the tour from any step — so a
waiting step is never a trap.
"""

from __future__ import annotations

import json
import logging
import pathlib
from dataclasses import dataclass, field
from typing import Any

from qtpy import QtCore, QtGui, QtWidgets

logger = logging.getLogger(__name__)

__all__ = ["GuidedTour", "TourStep", "load_tour"]


@dataclass
class TourStep:
    """One stop on a guided tour.

    Attributes
    ----------
    title : str
        Short heading shown in bold at the top of the bubble.
    text : str
        The explanation. Rendered as rich text, so simple markup works.
    target : dict
        How to find the widget to point at; see the module docstring.
    expect : dict
        Optional ``{"signal": ..., "hint": ...}`` (spelled ``await`` in the JSON,
        which is a Python keyword). When present, the step waits for the user to
        use the highlighted control before Next becomes available.
    """

    title: str = ""
    text: str = ""
    target: dict[str, Any] = field(default_factory=dict)
    expect: dict[str, Any] = field(default_factory=dict)
    waits: bool = False


def load_tour(path: str | pathlib.Path) -> list[TourStep]:
    """Read a tour definition from a JSON file.

    Parameters
    ----------
    path : str or pathlib.Path
        The ``.json`` file holding a list of step objects.

    Returns
    -------
    list of TourStep
        The parsed steps; an empty list when the file is missing or malformed,
        because a broken tour must never stop a tool from opening.
    """
    try:
        raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except Exception:
        logger.debug("could not read tour %s", path, exc_info=True)
        return []
    if isinstance(raw, dict):
        raw = raw.get("steps", [])
    steps: list[TourStep] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        # ``await`` may be omitted, ``true`` (wait, nothing to configure),
        # ``false`` (explicitly do not wait — a step that only points at
        # something to read) or a ``{"signal", "hint"}`` mapping. ``false`` used
        # to reach ``dict(False)`` and raise, which took the whole tool down with
        # it on construction, so an authored tour could not opt a step out.
        requested = item.get("await", item.get("expect"))
        if requested is True:
            expect, waits = {}, True
        elif requested is None or requested is False:
            expect, waits = {}, False
        else:
            try:
                expect, waits = dict(requested), True
            except (TypeError, ValueError):
                logger.debug("tour step %r has an unusable 'await'", item.get("title"))
                expect, waits = {}, False
        steps.append(
            TourStep(
                title=str(item.get("title", "")),
                text=str(item.get("text", "")),
                target=dict(item.get("target") or {}),
                expect=expect,
                waits=waits,
            )
        )
    return steps


class _Spotlight(QtWidgets.QWidget):
    """A translucent overlay that dims the window except for one rectangle.

    Highlighting by *dimming everything else* rather than by drawing a border
    is what makes the target findable in a dense panel: the eye goes to the one
    lit region without having to look for a thin outline.
    """

    def __init__(self, parent: QtWidgets.QWidget):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self._rect = QtCore.QRect()

    def set_target_rect(self, rect: QtCore.QRect) -> None:
        """Light up *rect* (in this overlay's coordinates) and repaint."""
        self._rect = QtCore.QRect(rect)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Dim everything around the highlighted rectangle, and outline it.

        The dimming is drawn as **four bands** around the hole rather than as a
        full-cover fill with the hole cleared out. A clear composition writes
        transparent pixels, and a child widget shares its parent's backing
        store, so "transparent" comes out black — the spotlight ended up hiding
        the very control it was pointing at.
        """
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        shade = QtGui.QColor(0, 0, 0, 110)
        full = self.rect()
        hole = self._rect.adjusted(-6, -6, 6, 6) if (
            self._rect.isValid() and not self._rect.isEmpty()
        ) else QtCore.QRect()

        if hole.isEmpty():
            painter.fillRect(full, shade)
        else:
            hole = hole.intersected(full)
            painter.fillRect(QtCore.QRect(full.left(), full.top(),
                                          full.width(), hole.top() - full.top()), shade)
            painter.fillRect(QtCore.QRect(full.left(), hole.bottom() + 1,
                                          full.width(), full.bottom() - hole.bottom()),
                             shade)
            painter.fillRect(QtCore.QRect(full.left(), hole.top(),
                                          hole.left() - full.left(), hole.height()), shade)
            painter.fillRect(QtCore.QRect(hole.right() + 1, hole.top(),
                                          full.right() - hole.right(), hole.height()),
                             shade)
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 190, 60), 2))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRoundedRect(hole.adjusted(1, 1, -1, -1), 6, 6)
        painter.end()


class _Bubble(QtWidgets.QFrame):
    """The popup itself: heading, explanation, step counter and navigation."""

    def __init__(self, parent: QtWidgets.QWidget):
        super().__init__(parent)
        self.setObjectName("tourBubble")
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setAutoFillBackground(True)
        # An explicit opaque background is not optional: the spotlight below
        # punches its hole with a Clear composition, so a bubble that inherits a
        # transparent background is drawn *over the hole* and every word of it
        # ends up mixed with the widgets underneath.
        self.setStyleSheet(
            "#tourBubble {"
            " background-color: palette(base);"
            " color: palette(text);"
            " border: 2px solid #ffbe3c;"
            " border-radius: 8px; }"
        )
        self.setMaximumWidth(420)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        self.title = QtWidgets.QLabel()
        font = self.title.font()
        font.setBold(True)
        self.title.setFont(font)
        self.title.setWordWrap(True)
        layout.addWidget(self.title)

        self.body = QtWidgets.QLabel()
        self.body.setWordWrap(True)
        self.body.setTextFormat(QtCore.Qt.RichText)
        # A step can cross-reference the docs; route those the same way the help
        # modal does rather than letting Qt try to navigate a QLabel.
        self.body.setOpenExternalLinks(False)
        self.body.setTextInteractionFlags(
            QtCore.Qt.TextBrowserInteraction | QtCore.Qt.TextSelectableByMouse
        )
        self.body.linkActivated.connect(self._open_link)
        # The body lives in a scroll area that is invisible until it is needed.
        # A step longer than the window would otherwise either be cut off or push
        # ``Next`` off-screen; with this the text stays complete and reachable
        # however small the tool window is.
        self.body_scroll = QtWidgets.QScrollArea()
        self.body_scroll.setWidget(self.body)
        self.body_scroll.setWidgetResizable(True)
        self.body_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.body_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.body_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.body_scroll.setStyleSheet("QScrollArea { background: transparent; }")
        self.body_scroll.viewport().setAutoFillBackground(False)
        self.body.setAutoFillBackground(False)
        layout.addWidget(self.body_scroll)

        #: Prompt shown while a step waits for the user to use the highlighted
        #: control. It replaces the "let the tour do it" button a demo reel
        #: would have: pressing the real thing is the lesson.
        self.prompt = QtWidgets.QLabel()
        self.prompt.setWordWrap(True)
        self.prompt.setTextFormat(QtCore.Qt.RichText)
        self.prompt.setVisible(False)
        layout.addWidget(self.prompt)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(6)
        self.counter = QtWidgets.QLabel()
        self.counter.setStyleSheet("color: palette(mid);")
        row.addWidget(self.counter)
        row.addStretch(1)
        self.skip_button = QtWidgets.QToolButton()
        self.skip_button.setText("Close")
        self.skip_button.setAutoRaise(True)
        row.addWidget(self.skip_button)
        self.back_button = QtWidgets.QPushButton("◀ Back")
        row.addWidget(self.back_button)
        self.next_button = QtWidgets.QPushButton("Next ▶")
        self.next_button.setDefault(True)
        row.addWidget(self.next_button)
        layout.addLayout(row)

    def fit_to_content(self, available: QtCore.QSize) -> None:
        """Resize to hold the whole step, given the room the window has.

        ``adjustSize()`` alone is not enough. A word-wrapped ``QLabel`` reports a
        ``sizeHint`` that does not know the width it will be wrapped to, so a
        long step came out **silently truncated** — the text stopped mid-sentence
        with the buttons drawn neatly underneath, which reads as a step that was
        written that way rather than as a layout failure. Wrapped text has to be
        measured with :meth:`~QLabel.heightForWidth` *after* the width is fixed.

        If the step still does not fit the window, the body **scrolls** rather
        than being cut: a bubble taller than its host would otherwise push
        ``Next`` off-screen and strand the user.
        """
        margin = 24
        width = min(self.maximumWidth(), max(240, available.width() - margin))
        self.setFixedWidth(width)

        layout = self.layout()
        left, _, right, _ = layout.getContentsMargins()
        text_width = width - left - right
        # ``isVisibleTo`` rather than ``isVisible``: the bubble's own parent may
        # not be shown yet at this point, and ``isVisible`` would then report
        # False for every label — collapsing the bubble to its buttons.
        self.title.setMinimumHeight(self.title.heightForWidth(text_width))
        self.prompt.setMinimumHeight(
            self.prompt.heightForWidth(text_width) if self.prompt.isVisibleTo(self) else 0
        )

        # Measure the body at the width it gets *with* a scroll bar present, not
        # at the bubble's full text width. A vertical scroll bar takes ~15 px, so
        # measuring without it under-reports the wrapped height and the body ends
        # up scrolling even when the window had room to show all of it. Erring
        # narrow is self-correcting: a slightly generous height simply means no
        # scroll bar appears.
        body_width = text_width - self.body_scroll.verticalScrollBar().sizeHint().width()
        body_height = self.body.heightForWidth(max(120, body_width))
        self.body_scroll.setMinimumHeight(body_height)
        self.body_scroll.setMaximumHeight(body_height)
        self.adjustSize()

        limit = available.height() - margin

        # ``heightForWidth`` is only an estimate for rich text — measured against
        # the real layout it under-reports by a line or two, which is enough to
        # leave a scroll bar on a step that had room to be shown whole. So ask
        # the scroll bar what it actually needs and grow into any spare room.
        # Correcting from the measured result rather than trusting the estimate
        # is what makes this independent of Qt's text metrics.
        for _ in range(2):
            self.layout().activate()
            overflow = self.body_scroll.verticalScrollBar().maximum()
            if overflow <= 0 or self.height() >= limit:
                break
            grown = min(body_height + overflow, body_height + (limit - self.height()))
            self.body_scroll.setMinimumHeight(grown)
            self.body_scroll.setMaximumHeight(grown)
            body_height = grown
            self.adjustSize()

        if self.height() > limit:
            # Hand the overflow to the body's scroll area alone, so the title,
            # the prompt and the button row all stay on screen.
            allowed = max(60, body_height - (self.height() - limit))
            self.body_scroll.setMinimumHeight(allowed)
            self.body_scroll.setMaximumHeight(allowed)
            self.adjustSize()

    @staticmethod
    def _open_link(url: str) -> None:
        """Send a link in a step's text to the docs or the system browser."""
        from chisurf.gui.widgets.tools.doc_links import open_link

        open_link(url)


class GuidedTour(QtCore.QObject):
    """Walks a user through a tool, one highlighted widget at a time.

    Parameters
    ----------
    host : QWidget
        The tool window. Its widget tree is searched for step targets, and the
        overlay is parented to it.
    steps : sequence of TourStep
        The tour.
    model : object, optional
        Consulted after *host* when resolving a step's ``action``.

    Notes
    -----
    The tour never blocks: the bubble is a child widget, not a modal dialog, so
    the user can interact with the tool while it is up — which is the point, as
    most steps are asking them to touch the thing being pointed at.
    """

    finished = QtCore.Signal()

    def __init__(self, host: QtWidgets.QWidget, steps, model: Any = None):
        super().__init__(host)
        self._host = host
        self._steps = list(steps)
        self._model = model
        self._index = 0
        self._spotlight: _Spotlight | None = None
        self._bubble: _Bubble | None = None
        #: (signal, slot) currently connected for a waiting step.
        self._waiting: tuple | None = None
        #: Indices whose control the user has already used, so stepping back and
        #: forth does not ask them to press the same button twice.
        self._satisfied: set[int] = set()
        #: Toolbar action behind the current target, when it is one.
        self._action = None
        #: Rectangle *within* the target widget to light, when the target is a
        #: row of a list rather than a widget of its own.
        self._sub_rect: QtCore.QRect | None = None
        #: Navigation row the current step points at, so a waiting step is
        #: satisfied by that row and not by any change of selection.
        self._panel_row: int | None = None
        #: Collapsible panels this tour opened, with the auto-fold setting each
        #: had before, so :meth:`stop` gives them back.
        self._unfolded: list[tuple[QtWidgets.QWidget, bool]] = []

    @property
    def index(self) -> int:
        """Index of the step currently shown."""
        return self._index

    @property
    def steps(self) -> list[TourStep]:
        """The steps this tour will walk through."""
        return list(self._steps)

    # ── lifecycle ──
    def start(self, index: int = 0) -> bool:
        """Show the tour from *index*.

        Returns
        -------
        bool
            Whether the tour started; ``False`` when it has no steps.
        """
        if not self._steps:
            return False
        self._build()
        self._index = max(0, min(int(index), len(self._steps) - 1))
        self._show_step()
        return True

    def stop(self) -> None:
        """Take the overlay down and forget it."""
        self._disconnect()
        self._restore_folding()
        for widget in (self._spotlight, self._bubble):
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._spotlight = None
        self._bubble = None
        self.finished.emit()

    def next(self) -> None:
        """Advance one step, ending the tour after the last one."""
        if self._index + 1 >= len(self._steps):
            self.stop()
            return
        self._index += 1
        self._show_step()

    def back(self) -> None:
        """Go back one step."""
        if self._index > 0:
            self._index -= 1
            self._show_step()

    # ── internals ──
    def _build(self) -> None:
        if self._spotlight is None:
            self._spotlight = _Spotlight(self._host)
        if self._bubble is None:
            self._bubble = _Bubble(self._host)
            self._bubble.next_button.clicked.connect(self.next)
            self._bubble.back_button.clicked.connect(self.back)
            self._bubble.skip_button.clicked.connect(self.stop)
        self._spotlight.setGeometry(self._host.rect())
        self._spotlight.show()
        self._spotlight.raise_()
        self._bubble.show()
        self._bubble.raise_()

    def resolve_target(self, target: dict[str, Any]) -> QtWidgets.QWidget | None:
        """Find the widget a step points at.

        Parameters
        ----------
        target : dict
            Any of ``attr``, ``key``, ``title``, ``action`` or ``panel``; see
            the module docstring.

        Returns
        -------
        QWidget or None
            The widget, or ``None`` when nothing matches.
        """
        attr = str(target.get("attr", "") or "")
        key = str(target.get("key", "") or "")
        title = str(target.get("title", "") or "")
        action = str(target.get("action", "") or "")
        panel = str(target.get("panel", "") or "")
        name = str(target.get("name", "") or "")
        tab = str(target.get("tab", "") or "")
        self._action = None
        # A list *row* is not a widget, so the spotlight needs its rectangle
        # separately; cleared here so a stale one cannot leak into a later step.
        self._sub_rect = None
        self._panel_row = None

        if panel:
            widget = self._resolve_panel(panel)
            if widget is not None:
                return widget
        if tab:
            widget = self._resolve_tab(tab)
            if widget is not None:
                return widget
        if name:
            widget = self._resolve_object_name(name)
            if widget is not None:
                return widget
        if action:
            for toolbar in self._host.findChildren(QtWidgets.QToolBar):
                for act in toolbar.actions():
                    if action.lower() in str(act.text()).lower():
                        widget = toolbar.widgetForAction(act)
                        if widget is not None:
                            self._action = act
                            return widget
            # An action bar built from ``QToolButton``\ s rather than
            # ``QAction``\ s — the shared ``action_button`` vocabulary — puts the
            # caption in the *tooltip*, because the buttons are icon-only. Without
            # this fallback a step pointing at "Process" on such a bar resolved to
            # nothing, which is most of the hand-built tools in the app.
            widget = self._resolve_button(action)
            if widget is not None:
                return widget
        if not (attr or key or title):
            return None
        for widget in self._host.findChildren(QtWidgets.QWidget):
            section = getattr(widget, "_section", None)
            if section is None:
                continue
            if attr:
                # Field sections bind through ``attr``; several section types
                # name the same thing ``target``, and a custom section puts the
                # attribute inside its options.
                bound = (
                    getattr(section, "attr", None)
                    or getattr(section, "target", None)
                    or (getattr(section, "options", None) or {}).get("attr")
                )
                if bound != attr:
                    continue
            if key and str(getattr(section, "key", "") or "") != key:
                continue
            if title and str(getattr(section, "title", "") or "") != title:
                continue
            return widget
        return None

    def _resolve_tab(self, tab: str) -> QtWidgets.QWidget | None:
        """Find the page registered under a tab named *tab* (substring, folded).

        ChiSurf tools are built out of dock tabs far more often than out of view
        specs, so without this a step naming one of them — "Bursts", "Decay
        sources", "Summary" — resolved to nothing. Returns the tab's *page*, so
        :meth:`_reveal` then raises it and the spotlight lands on the content
        rather than on a strip of tab bar.
        """
        needle = tab.strip().casefold()
        for tabs in self._host.findChildren(QtWidgets.QTabWidget):
            for index in range(tabs.count()):
                if needle in str(tabs.tabText(index)).casefold():
                    return tabs.widget(index)
        # ChiSurf ``DockArea`` keeps its own widget→name registry, because a
        # docked page may have been torn out of the tab widget it started in.
        for area in self._host.findChildren(QtWidgets.QWidget):
            registry = getattr(area, "_tab_names", None)
            if not isinstance(registry, dict):
                continue
            for widget, label in registry.items():
                if needle in str(label).casefold():
                    self._restore_hidden_page(area, widget)
                    return widget
        return None

    @staticmethod
    def _select_wizard_step(
        stack: QtWidgets.QStackedWidget, page: QtWidgets.QWidget
    ) -> None:
        """Move a wizard to the step holding *page*, through its nav list.

        The list is the thing that drives the page, the title and the subtitle
        together (``WizardSection.nav_list``), so selecting the row is what makes
        the window self-consistent. Falls back to nothing when the stack is not a
        wizard's — an ordinary ``QStackedWidget`` is handled by the caller.
        """
        index = stack.indexOf(page)
        if index < 0:
            return
        node = stack.parentWidget()
        while node is not None:
            nav = getattr(node, "nav_list", None)
            if isinstance(nav, QtWidgets.QListWidget) and nav.count() == stack.count():
                if nav.currentRow() != index:
                    nav.setCurrentRow(index)
                return
            node = node.parentWidget()

    def _unfold(self, box: QtWidgets.QWidget) -> None:
        """Expand *box* if it is a collapsed panel, and hold it open.

        Holding it open is the part that is easy to miss: a ``CollapsibleBox``
        with ``auto_fold`` folds itself when the pointer *leaves* it, and during
        a tour the pointer is never on it — so a panel opened here would shut
        again a second later, mid-step. Auto-fold is therefore suspended for the
        panels the tour opened and given back in :meth:`stop`.
        """
        expand = getattr(box, "set_expanded", None)
        expanded = getattr(box, "is_expanded", None)
        if not (callable(expand) and callable(expanded)):
            return
        try:
            if expanded():
                return
            self._unfolded.append((box, bool(getattr(box, "auto_fold", False))))
            box.auto_fold = False
            expand(True)
            QtWidgets.QApplication.processEvents()
        except Exception:  # pragma: no cover - a box that disagrees
            logger.debug("could not expand a collapsed panel for a tour step")

    def _restore_folding(self) -> None:
        """Give every panel this tour opened its auto-fold setting back."""
        for box, auto_fold in self._unfolded:
            try:
                box.auto_fold = auto_fold
            except (RuntimeError, AttributeError):
                pass  # the widget went away with its window
        self._unfolded.clear()

    @staticmethod
    def _restore_hidden_page(area: QtWidgets.QWidget, page: QtWidgets.QWidget) -> None:
        """Bring *page* back if the user closed its dock, before pointing at it.

        A ``DockArea`` tab added with ``close_mode="hide"`` keeps its page in the
        registry after the user closes it — so a step naming that tab still
        *resolves*, to a widget that is not on screen and whose geometry is
        whatever it was when it was last laid out. The spotlight then lands on a
        rectangle of unrelated panel and the bubble explains a control nobody can
        see: the same silent degradation as an unresolved target, but past the
        guardrail that checks for one.

        Found on the BVA tour, where the *Channel Definitions* step pointed at a
        stack of settings because that dock had been closed in an earlier
        session and the layout was restored from disk.
        """
        show_tab = getattr(area, "showTab", None)
        index_of = getattr(area, "indexOf", None)
        is_visible = getattr(area, "isTabVisible", None)
        if not (callable(show_tab) and callable(index_of) and callable(is_visible)):
            return
        try:
            index = index_of(page)
            if index >= 0 and not is_visible(index):
                show_tab(index)
                # Let the dock re-lay-out before anyone measures the page. The
                # caller reads its geometry to place the spotlight, and a page
                # that has just been re-parented into a tab stack still carries
                # the rectangle it had when it was closed — so without this the
                # highlight lands on the wrong part of the window and the two
                # pages are drawn over each other.
                QtWidgets.QApplication.processEvents()
        except Exception:  # pragma: no cover - a dock area that disagrees
            logger.debug("could not restore the hidden dock page for a tour step")

    def _resolve_object_name(self, name: str) -> QtWidgets.QWidget | None:
        """Find a widget by ``objectName``, exactly or by suffix.

        The suffix match is what makes this usable: the shared action buttons are
        named ``toolaction_run``, ``toolaction_add`` and so on, so a tour can say
        ``{"name": "run"}`` and point at the canonical Run button of *any* tool
        that uses the shared vocabulary — without the tour having to know how
        that particular tool spelled its bar.
        """
        if not name:
            return None
        # Case-insensitive: the shared prefix is spelled ``toolAction_`` and is
        # very easy to author as ``toolaction_``. A tour that silently pointed at
        # nothing over one capital letter would be the worst kind of near-miss.
        needle = name.strip().casefold()
        exact: QtWidgets.QWidget | None = None
        suffix: QtWidgets.QWidget | None = None
        for widget in self._host.findChildren(QtWidgets.QWidget):
            object_name = str(widget.objectName() or "").casefold()
            if not object_name:
                continue
            if object_name == needle:
                exact = exact or widget
            elif object_name.endswith(needle):
                suffix = suffix or widget
        return exact or suffix

    def _resolve_button(self, caption: str) -> QtWidgets.QWidget | None:
        """Find a button whose text *or tooltip* contains *caption*.

        Icon-only buttons carry their caption in the tooltip, so text alone is
        not enough to find them.
        """
        needle = caption.strip().casefold()
        for button in self._host.findChildren(QtWidgets.QAbstractButton):
            haystack = f"{button.text()} {button.toolTip()}".casefold()
            if needle in haystack:
                return button
        return None

    def _resolve_panel(self, panel: str) -> QtWidgets.QWidget | None:
        """Find the navigation-list row named *panel* (substring, case-folded).

        Returns the list widget and records the row's rectangle in
        :attr:`_sub_rect`, because what has to be lit is one row of it and not
        the whole left pane — spotlighting the entire list would point at every
        step at once, which is the same as pointing at none.
        """
        nav_list = getattr(self._host, "nav_list", None)
        candidates = [nav_list] if isinstance(nav_list, QtWidgets.QListWidget) else []
        candidates += [
            found
            for found in self._host.findChildren(QtWidgets.QListWidget)
            if found is not nav_list
        ]
        needle = panel.strip().casefold()
        for widget in candidates:
            if widget is None:
                continue
            for row in range(widget.count()):
                item = widget.item(row)
                if item is None or needle not in str(item.text()).casefold():
                    continue
                self._sub_rect = widget.visualItemRect(item)
                self._panel_row = row
                return widget
        return None

    def _show_step(self) -> None:
        step = self._steps[self._index]
        bubble, spotlight = self._bubble, self._spotlight
        if bubble is None or spotlight is None:
            return

        self._disconnect()
        bubble.title.setText(step.title)
        bubble.body.setText(step.text)
        bubble.counter.setText(f"{self._index + 1} / {len(self._steps)}")
        bubble.back_button.setEnabled(self._index > 0)
        bubble.next_button.setText(
            "Done" if self._index + 1 >= len(self._steps) else "Next ▶"
        )

        spotlight.setGeometry(self._host.rect())
        widget = self.resolve_target(step.target)
        self._wire_wait(step, widget, self._action)
        rect = QtCore.QRect()
        if widget is not None:
            # Reveal and raise dock tab to foreground FIRST before computing coordinates
            self._reveal(widget)
            top_left = widget.mapTo(self._host, QtCore.QPoint(0, 0))
            sub = getattr(self, "_sub_rect", None)
            if sub is not None and sub.isValid():
                # A row inside a list: light the row, not the list.
                rect = QtCore.QRect(top_left + sub.topLeft(), sub.size())
            else:
                rect = QtCore.QRect(top_left, widget.size())
        spotlight.set_target_rect(rect)
        # Size to the *content*, measured at the width it will wrap to — see
        # ``_Bubble.fit_to_content``. Plain ``adjustSize()`` truncated long steps.
        bubble.fit_to_content(self._host.size())
        bubble.move(self._place(rect, bubble.size()))
        bubble.raise_()

    def _wire_wait(self, step: TourStep, widget, action) -> None:
        """Make the step wait for the user to use *widget*, if it asked to.

        The tour deliberately has no "do it for me" button. Someone who watched
        a button being pressed for them has not learned where it is, and the
        step they skip is usually the one they will need on their own data.
        """
        bubble = self._bubble
        if bubble is None:
            return
        if not step.waits or self._index in self._satisfied:
            bubble.prompt.setVisible(False)
            bubble.next_button.setEnabled(True)
            return

        # A panel step is satisfied by selecting *that* row, not by any change of
        # selection: a list emits on every row, so an ungated wait would be
        # cleared by the user browsing past the step they were asked to open.
        row = getattr(self, "_panel_row", None)
        gate = None
        if row is not None and hasattr(widget, "currentRowChanged"):
            # Already on that row: the step is asking for something that is
            # true. Selecting a current row emits nothing, so waiting on the
            # signal would strand the user on a step with no way forward — and
            # the very first panel of a workflow shell is always current.
            if widget.currentRow() == row:
                self._satisfied.add(self._index)
                bubble.prompt.setText(
                    "<span style='color:#2a8a4a'>✓ already open — press Next</span>"
                )
                bubble.prompt.setVisible(True)
                bubble.next_button.setEnabled(True)
                return
            signal = widget.currentRowChanged
            gate = lambda *args: bool(args) and args[0] == row  # noqa: E731
        else:
            signal = self._find_signal(step, widget, action)
        if signal is None:
            # Nothing to wait on: better to let the user through than to strand
            # them on a step whose control could not be found.
            logger.debug("tour step %d has nothing to wait on", self._index)
            bubble.prompt.setVisible(False)
            bubble.next_button.setEnabled(True)
            return

        hint = str(step.expect.get("hint", "")) or "Use the highlighted control to go on."
        bubble.prompt.setText(f"<span style='color:#c07800'>▸ {hint}</span>")
        bubble.prompt.setVisible(True)
        bubble.next_button.setEnabled(False)

        def _done(*args) -> None:
            if gate is not None and not gate(*args):
                return
            self._satisfied.add(self._index)
            self._disconnect()
            if self._bubble is None:
                return
            self._bubble.prompt.setText(
                "<span style='color:#2a8a4a'>✓ done — press Next</span>"
            )
            self._bubble.next_button.setEnabled(True)
            self._bubble.next_button.setDefault(True)
            self._bubble.next_button.setFocus()

        signal.connect(_done)
        self._waiting = (signal, _done)

    @staticmethod
    def _find_signal(step: TourStep, widget, action):
        """Return the signal that means "the user used this control"."""
        name = str(step.expect.get("signal", "") or "")
        for candidate in (action, widget):
            if candidate is None:
                continue
            if name:
                signal = getattr(candidate, name, None)
                if signal is not None and hasattr(signal, "connect"):
                    return signal
                continue
            # Auto-detect, most specific first: a toolbar button is backed by a
            # QAction, a plain button emits clicked, and a field is "used" when
            # its value changes rather than when it is clicked.
            for guess in ("triggered", "clicked", "editingFinished",
                          "valueChanged", "currentIndexChanged", "textChanged"):
                signal = getattr(candidate, guess, None)
                if signal is not None and hasattr(signal, "connect"):
                    return signal
        return None

    def _disconnect(self) -> None:
        """Drop the connection a waiting step made, if any."""
        if self._waiting is None:
            return
        signal, slot = self._waiting
        try:
            signal.disconnect(slot)
        except (TypeError, RuntimeError):
            pass
        self._waiting = None

    def _reveal(self, widget: QtWidgets.QWidget) -> None:
        """Scroll *widget* into view and raise the dock tab / stack page it lives on."""
        child = widget
        parent = widget.parentWidget()
        while parent is not None and parent is not self._host:
            # 0. Open a collapsed panel the target sits inside. An AutoForm
            #    ``panel`` is a CollapsibleBox, and a form of any size folds most
            #    of them: the target then resolves to a widget with a real
            #    geometry that is simply not drawn, and the spotlight lands on a
            #    header bar somewhere else in the column. Same silent degradation
            #    as an unresolved target, and just as invisible to the guardrail.
            self._unfold(parent)
            # 1. Raise pyqtgraph Dock / ChiSurf Dock if present
            if hasattr(parent, "raiseDock") and callable(parent.raiseDock):
                try:
                    parent.raiseDock()
                except Exception:
                    pass

            # 1b. A wizard step. An AutoForm wizard is a nav list driving a
            #     QStackedWidget, and *the list* is what updates the title, the
            #     subtitle and the page together. Setting the stack directly
            #     shows the right controls under the previous step's heading,
            #     which reads as a bug in the tool rather than in the tour.
            if isinstance(parent, QtWidgets.QStackedWidget):
                self._select_wizard_step(parent, child)
            # 2. QTabWidget or DockTabWidget / DockStackedTabWidget
            if hasattr(parent, "setCurrentWidget") and callable(parent.setCurrentWidget):
                try:
                    parent.setCurrentWidget(child)
                except Exception:
                    pass
            elif hasattr(parent, "indexOf") and hasattr(parent, "setCurrentIndex"):
                try:
                    idx = parent.indexOf(child)
                    if idx >= 0:
                        parent.setCurrentIndex(idx)
                except Exception:
                    pass

            # 3. Check if child is inside a Dock container or Tab widget that has raise_
            if hasattr(child, "raise_") and callable(child.raise_):
                try:
                    child.raise_()
                except Exception:
                    pass

            # 4. QScrollArea ensureWidgetVisible
            area = getattr(parent, "ensureWidgetVisible", None)
            if callable(area):
                try:
                    area(widget)
                except Exception:
                    pass

            child = parent
            parent = parent.parentWidget()

        QtWidgets.QApplication.processEvents()

    def _place(self, rect: QtCore.QRect, size: QtCore.QSize) -> QtCore.QPoint:
        """Choose a bubble position that points at *rect* without covering it.

        Evaluates candidate positions around *rect* and in the host window corners,
        preferring positions that do not intersect *rect*.
        """
        host = self._host.rect()
        margin = 12
        width, height = size.width(), size.height()
        if not rect.isValid() or rect.isEmpty():
            return QtCore.QPoint(
                max(margin, (host.width() - width) // 2),
                max(margin, (host.height() - height) // 2),
            )

        candidates = [
            # 1. Below (aligned left, right, center)
            (rect.left(), rect.bottom() + margin),
            (rect.right() - width, rect.bottom() + margin),
            (rect.center().x() - width // 2, rect.bottom() + margin),

            # 2. Above (aligned left, right, center)
            (rect.left(), rect.top() - margin - height),
            (rect.right() - width, rect.top() - margin - height),
            (rect.center().x() - width // 2, rect.top() - margin - height),

            # 3. Right (aligned top, bottom, center)
            (rect.right() + margin, rect.top()),
            (rect.right() + margin, rect.bottom() - height),
            (rect.right() + margin, rect.center().y() - height // 2),

            # 4. Left (aligned top, bottom, center)
            (rect.left() - margin - width, rect.top()),
            (rect.left() - margin - width, rect.bottom() - height),
            (rect.left() - margin - width, rect.center().y() - height // 2),

            # 5. Host window corners as fallback
            (host.right() - width - margin, host.top() + margin),
            (host.left() + margin, host.top() + margin),
            (host.right() - width - margin, host.bottom() - height - margin),
            (host.left() + margin, host.bottom() - height - margin),
        ]

        def clamp_to_host(x: int, y: int) -> QtCore.QPoint:
            cx = max(margin, min(x, host.width() - width - margin))
            cy = max(margin, min(y, host.height() - height - margin))
            return QtCore.QPoint(int(cx), int(cy))

        non_overlapping = []
        for x, y in candidates:
            pt = clamp_to_host(x, y)
            placed = QtCore.QRect(pt, size)
            if not placed.intersects(rect):
                dist = (placed.center() - rect.center()).manhattanLength()
                non_overlapping.append((dist, pt))

        if non_overlapping:
            non_overlapping.sort(key=lambda item: item[0])
            return non_overlapping[0][1]

        # Nothing fits beside the target — a tall bubble, a short window and a
        # full-width row leave no candidate clear of it. Cover as little as
        # possible, and among near-equal choices cover the **bottom right**:
        # a form fills left to right and top to bottom, so a widget's label,
        # its editor and its first control are anchored at the target's top
        # left. Losing that corner is losing the thing the step points at,
        # which is how a step ends up explaining a control the reader cannot
        # see. Found on the FCS calculator, whose dye panel is one full-width
        # row: minimum overlap alone put the bubble over the combo box.
        scored = []
        for x, y in candidates:
            pt = clamp_to_host(x, y)
            placed = QtCore.QRect(pt, size)
            overlap_rect = placed.intersected(rect)
            overlap_area = overlap_rect.width() * overlap_rect.height()
            # Bucket the area so "about as bad" placements are tied and the
            # corner preference decides between them, rather than a few stray
            # pixels of difference doing so.
            scored.append(((overlap_area + 999) // 1000, -pt.y(), -pt.x(), pt))
        scored.sort(key=lambda item: item[:3])
        return scored[0][3]
