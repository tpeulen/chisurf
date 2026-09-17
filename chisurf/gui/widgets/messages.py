"""Declared, non-modal widget messages: :class:`Msg` and :class:`MessagesMixin`.

A modal box is the wrong shape for most of what a tool has to say. "Load a file
first", "this dataset has no error column", "the fit did not converge" are
*states of the tool*, not events needing an answer: they arise, they persist
while the cause persists, and they go away when it is fixed. Raising a dialog
for them stops the user's work, says the thing once, and leaves nothing behind —
so the tool looks fine while still being unusable, and a test can only observe
the message by intercepting a dialog.

This module is the other half of :mod:`chisurf.gui.dialogs`. A dialog is for a
question or an event the user must acknowledge *now*; a message is for a
condition. Every condition a widget can be in is **declared** on its class:

    class MyTool(ChisurfDockTool):

        class Error(ChisurfDockTool.Error):
            no_file = Msg("Load a TTTR file first.")
            unreadable = Msg("Cannot read {}: {}")

        class Warning(ChisurfDockTool.Warning):
            no_irf = Msg("No IRF selected — the decay is fitted unconvolved.")

Raising and clearing are then addressed, not fired:

    self.Error.no_file()                    # show it
    self.Error.unreadable(path, exc)        # show it, formatted
    self.Error.no_file.clear()              # take it back
    self.Error.clear()                      # take back the whole group
    assert self.Error.no_file.is_shown      # and a test can just look

Three properties follow from declaring them, and none of them are available to a
dialog: the set of things a widget can complain about is enumerable (so it can be
reviewed and translated), a message can be *retracted* when its cause is fixed,
and a test asserts on `is_shown` rather than on a patched dialog.

The rendering is deliberately small — one line in the host's status bar, the
most severe message first, with the rest in the tooltip. See
:class:`MessageBar`.

Messages are translated at render time through :func:`chisurf.core.support.i18n.tr`, so
a language change re-renders what is already on screen; the extractor picks up
``Msg("…")`` literals the same way it picks up ``i18n.tr("…")``.
"""

from __future__ import annotations

import typing

from chisurf.core.support import i18n
from chisurf.gui import QtCore, QtGui, QtWidgets

__all__ = [
    "Msg",
    "BoundMsg",
    "MessageGroup",
    "MessageBar",
    "MessagesMixin",
]

#: Severity ordering, most severe first. Used for sorting and for styling.
SEVERITIES = ("error", "warning", "info")

_SEVERITY_STYLE = {
    "error": ("⛔", "#b3261e"),  # ⛔
    "warning": ("⚠", "#a1670a"),  # ⚠
    "info": ("ℹ", "#31567f"),  # ℹ
}


class Msg:
    """An unbound message declared on a widget's message group.

    Parameters
    ----------
    format_string : str
        The message text. ``str.format`` placeholders are filled from the
        arguments passed when the message is raised.

    Examples
    --------
    >>> m = Msg("Cannot read {}")
    >>> m.format_string
    'Cannot read {}'
    """

    def __init__(self, format_string: str):
        self.format_string = format_string
        #: Attribute name under which the group class holds this message; filled
        #: in when the group is bound to a widget.
        self.name = ""

    def __repr__(self) -> str:
        """Return a constructor-shaped representation."""
        return f"{type(self).__name__}({self.format_string!r})"


class BoundMsg:
    """A :class:`Msg` bound to one widget's message group.

    Instances are created by :class:`MessageGroup` when a widget is built; user
    code never constructs one directly.
    """

    def __init__(self, unbound: Msg, group: MessageGroup, name: str):
        self._unbound = unbound
        self._group = group
        self._name = name
        self._args: tuple = ()
        self._kwargs: dict = {}
        self._shown = False

    @property
    def name(self) -> str:
        """Attribute name of this message on its group."""
        return self._name

    @property
    def severity(self) -> str:
        """Severity of the group this message belongs to."""
        return self._group.severity

    @property
    def is_shown(self) -> bool:
        """Whether the message is currently active."""
        return self._shown

    @property
    def text(self) -> str:
        """The formatted, translated message text.

        Translation happens here rather than at declaration so that a language
        change re-renders messages that are already on screen.
        """
        template = i18n.tr(self._unbound.format_string)
        try:
            return template.format(*self._args, **self._kwargs)
        except Exception:
            # A catalogue with the wrong placeholders must not take the tool
            # down; show the untranslated text rather than raising from a
            # repaint. `Exception`, not a list: `str.format` raises `TypeError`
            # for a numeric spec against a non-number and `AttributeError` for
            # an attribute lookup, and message arguments are routinely not
            # strings — an exception object, most often. A message text is never
            # worth an exception.
            try:
                return self._unbound.format_string.format(*self._args, **self._kwargs)
            except Exception:
                return self._unbound.format_string

    def __call__(self, *args, **kwargs) -> BoundMsg:
        """Raise the message, formatted with ``args``/``kwargs``.

        Raising an already-shown message with new arguments updates its text.
        """
        self._args = args
        self._kwargs = kwargs
        self._shown = True
        self._group.notify_changed()
        return self

    def clear(self) -> None:
        """Retract the message. Clearing a message that is not shown is a no-op."""
        if self._shown:
            self._shown = False
            self._group.notify_changed()

    def __repr__(self) -> str:
        """Return the message name, severity and whether it is shown."""
        state = "shown" if self._shown else "hidden"
        return f"<{self._group.severity}.{self._name} {state}>"


class MessageGroup:
    """One severity's worth of messages, bound to a widget.

    Subclasses declare :class:`Msg` attributes; a widget subclass narrows the
    group by deriving from its base's group, so declarations accumulate down the
    hierarchy exactly like ordinary class attributes.
    """

    #: One of :data:`SEVERITIES`; set by the three concrete groups below.
    severity: str = "info"

    def __init__(self, widget: MessagesMixin):
        self.widget = widget
        self._messages: dict[str, BoundMsg] = {}
        # Walk the MRO so an inherited declaration is bound too, with the most
        # derived declaration winning.
        for cls in reversed(type(self).__mro__):
            for name, value in vars(cls).items():
                if isinstance(value, Msg):
                    value.name = name
                    self._messages[name] = BoundMsg(value, self, name)
        for name, bound in self._messages.items():
            if hasattr(MessageGroup, name):
                # A declaration named after the group's own API would silently
                # replace it: `clear = Msg(...)` makes `self.Error.clear()`
                # *raise* a message instead of retracting the group, and
                # `widget` would break `notify_changed`. The point of declaring
                # conditions is that the set is inspectable, so a collision is
                # cheap to reject here rather than to debug later.
                raise TypeError(
                    f"{type(self).__name__}.{name} shadows MessageGroup.{name}; "
                    "rename the declared message"
                )
            setattr(self, name, bound)

    @property
    def messages(self) -> tuple[BoundMsg, ...]:
        """Every message declared in this group, bound."""
        return tuple(self._messages.values())

    @property
    def active(self) -> tuple[BoundMsg, ...]:
        """The messages currently shown, in declaration order."""
        return tuple(m for m in self._messages.values() if m.is_shown)

    def clear(self) -> None:
        """Retract every message in the group."""
        changed = False
        for message in self._messages.values():
            if message.is_shown:
                message._shown = False
                changed = True
        if changed:
            self.notify_changed()

    def notify_changed(self) -> None:
        """Tell the host widget that the active set changed."""
        self.widget.messages_changed()

    def __repr__(self) -> str:
        """Return the group's severity and its active messages."""
        return f"<{self.severity} group: {[m.name for m in self.active]}>"


class Error(MessageGroup):
    """Something the tool cannot do until the user changes something."""

    severity = "error"


class Warning(MessageGroup):
    """The tool went ahead, but the result is not what the user may expect."""

    severity = "warning"


class Information(MessageGroup):
    """Context worth stating; nothing is wrong."""

    severity = "info"


class MessageBar(QtWidgets.QWidget):
    """One-line, non-modal renderer for a widget's active messages.

    The most severe message is shown; any others are counted and listed in the
    tooltip, which keeps the bar from growing into the panel it is reporting on.
    Long text is elided rather than allowed to widen the host — the full text is
    always in the tooltip. The bar hides itself when nothing is active, so a tool
    with no complaints looks exactly as it did before.
    """

    #: Widest the one-line label may get before it is elided, in pixels.
    max_width: int = 520

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 1, 4, 1)
        layout.setSpacing(4)
        self._label = QtWidgets.QLabel(self)
        self._label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self._label.setWordWrap(False)
        layout.addWidget(self._label, 1)
        self.setVisible(False)

    def set_messages(self, messages: typing.Sequence[BoundMsg]) -> None:
        """Render ``messages`` (already ordered most-severe-first)."""
        if not messages:
            self._label.clear()
            self.setToolTip("")
            self.setVisible(False)
            return
        first = messages[0]
        glyph, colour = _SEVERITY_STYLE.get(first.severity, _SEVERITY_STYLE["info"])
        text = f"{glyph} {first.text}"
        if len(messages) > 1:
            text += f"  (+{len(messages) - 1})"
        metrics = QtGui.QFontMetrics(self._label.font())
        self._label.setText(metrics.elidedText(text, QtCore.Qt.ElideRight, self.max_width))
        self._label.setStyleSheet(f"color: {colour};")
        self.setToolTip(
            "\n".join(
                f"{_SEVERITY_STYLE.get(m.severity, _SEVERITY_STYLE['info'])[0]} {m.text}"
                for m in messages
            )
        )
        self.setVisible(True)


class MessagesMixin:
    """Gives a widget declared, non-modal messages.

    Mix into a ``QWidget`` subclass and declare ``Error`` / ``Warning`` /
    ``Information`` groups on it. The mixin binds them per instance, so
    ``self.Error.no_file`` is this widget's message and not the class's.

    A host decides where the messages are shown by calling
    :meth:`install_message_bar` with a layout or a status bar; without one the
    messages are still tracked and testable, they are simply not painted.
    """

    #: Default groups, so a subclass can derive from ``Base.Error`` even when it
    #: is the first in the hierarchy to declare a message.
    Error = Error
    Warning = Warning
    Information = Information

    def __init__(self, *args, **kwargs):
        """Bind the declared groups per instance.

        The Qt base is initialised first — a mixin must not touch instance state
        before the widget it is mixed into exists — and the groups are bound
        immediately after, so a subclass constructor can raise a message on its
        very first line after ``super().__init__()``.
        """
        super().__init__(*args, **kwargs)
        self._message_bar: MessageBar | None = None
        self.Error = type(self).Error(self)
        self.Warning = type(self).Warning(self)
        self.Information = type(self).Information(self)

    # -- querying -------------------------------------------------------------

    @property
    def message_groups(self) -> tuple[MessageGroup, ...]:
        """The three bound groups, most severe first."""
        return (self.Error, self.Warning, self.Information)

    @property
    def active_messages(self) -> tuple[BoundMsg, ...]:
        """Every active message, most severe first."""
        return tuple(m for group in self.message_groups for m in group.active)

    def clear_messages(self) -> None:
        """Retract every message in every group."""
        for group in self.message_groups:
            group.clear()

    # -- rendering ------------------------------------------------------------

    def install_message_bar(
        self, host: QtWidgets.QLayout | QtWidgets.QStatusBar | None = None
    ) -> MessageBar:
        """Create the message bar and place it in ``host``.

        Parameters
        ----------
        host : QLayout or QStatusBar, optional
            Where to put the bar. A layout gets it appended; a status bar gets it
            as a **permanent** widget — a standing condition must not be hidden
            by the transient ``showMessage`` text tools already use for
            "Loaded: …". Passing nothing creates the bar without placing it,
            which is what a caller does when it wants to position the widget
            itself.

        Returns
        -------
        MessageBar
            The bar, also stored as ``self._message_bar``.

        Raises
        ------
        TypeError
            If *host* is neither a layout nor a status bar. Ignoring it would be
            worse than refusing: an unplaced bar stays parentless, so the first
            message turns it into a **stray top-level window** carrying the
            tool's error text.
        """
        # Parented to the host widget when there is one, so an unplaced bar is
        # never a window of its own; the layout/status-bar calls below reparent
        # it anyway.
        bar = MessageBar(self if isinstance(self, QtWidgets.QWidget) else None)
        bar.setVisible(False)
        self._message_bar = bar
        if host is not None and not isinstance(host, (QtWidgets.QLayout, QtWidgets.QStatusBar)):
            raise TypeError(
                f"message bar host must be a QLayout or a QStatusBar, not {type(host).__name__}"
            )
        if isinstance(host, QtWidgets.QStatusBar):
            # No stretch: a stretched permanent widget squeezes the transient
            # `showMessage` area to nothing, and tools use that area for "Loaded:
            # …". The bar elides instead of growing.
            host.addPermanentWidget(bar)
        elif isinstance(host, QtWidgets.QLayout):
            host.addWidget(bar)
        self.messages_changed()
        return bar

    def messages_changed(self) -> None:
        """Re-render after the active set changed.

        A ``QMainWindow`` host that has not placed the bar itself gets one in its
        status bar the first time it has something to say — so a tool opts in by
        declaring a message, not by remembering to call
        :meth:`install_message_bar`, and a tool that never complains does not
        grow a status bar it does not use.

        Override to drive something other than the built-in bar — a node glyph on
        a pipeline canvas, for instance.
        """
        if self._message_bar is None:
            if not self.active_messages or not isinstance(self, QtWidgets.QMainWindow):
                return
            self.install_message_bar(self.statusBar())
            return  # install_message_bar renders
        self._message_bar.set_messages(self.active_messages)
