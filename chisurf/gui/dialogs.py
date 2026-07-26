"""The one message box in ChiSurf: :class:`ChiSurfMessageBox`.

``QMessageBox.critical(...)`` spins its own event loop until a button is
pressed. On the ``offscreen`` / ``minimal`` Qt platforms — every headless test
run, every CI job, every screenshot script — no button can ever be pressed, so a
dialog raised from an ``except`` branch does not report an error: it hangs the
process forever, with the traceback nowhere in sight. A ``question`` box is
worse: headless it hangs *and* the answer it would have returned is the one
deciding whether a file gets overwritten or a record deleted.

:class:`ChiSurfMessageBox` replaces the ``QMessageBox`` statics everywhere in
ChiSurf and fixes both problems at once:

* every box is **logged** at a matching level, whether or not it is shown;
* it is only **raised** when a person could actually dismiss it — headless it
  returns the caller-declared safe default instead of blocking;
* tests can **script answers** with :func:`auto_answer`, so a confirmation path
  is testable without a human or a fake event loop.

Interactively it behaves exactly like the static it replaces, so migration is
mechanical: ``QMessageBox.warning(self, t, m)`` → ``dialogs.warning(self, t, m)``
and ``QMessageBox.question(self, t, m, buttons, default)`` →
``dialogs.question(self, t, m, buttons, default)``, whose return value is still a
``QMessageBox.StandardButton`` and still compares against ``QMessageBox.Yes``.

Examples
--------
>>> from chisurf.gui import dialogs
>>> dialogs.warning(self, "Cannot split", "Load a file first.")     # doctest: +SKIP
>>> if dialogs.confirm(self, "Delete", "Delete this fit?"):         # doctest: +SKIP
...     ...
>>> with dialogs.auto_answer(question=dialogs.ChiSurfMessageBox.Yes):  # doctest: +SKIP
...     widget.delete_selected()   # the confirmation answers itself
"""

from __future__ import annotations

import contextlib
import logging
import typing

logger = logging.getLogger(__name__)

__all__ = [
    "Answer",
    "ChiSurfMessageBox",
    "is_interactive",
    "auto_answer",
    "error",
    "critical",
    "warning",
    "information",
    "question",
    "confirm",
    "choice",
    "about",
    "report_exception",
    "report_error",
    "report_warning",
    "report_information",
]


class Answer(typing.NamedTuple):
    """What the user chose in a :meth:`ChiSurfMessageBox.choice` box.

    Attributes
    ----------
    key : str or None
        The option key that was pressed; ``None`` when the box was dismissed
        or no user was present to answer it.
    checked : bool
        State of the optional tick box (``False`` when the box had none).
    """

    key: str | None
    checked: bool = False

    def __bool__(self) -> bool:
        """Truthy exactly when an option was chosen."""
        return self.key is not None

#: Qt platform plugins that draw to nothing a user can click.
_HEADLESS_PLATFORMS = frozenset({"offscreen", "minimal", "vnc", ""})

#: Scripted answers installed by :func:`auto_answer` (kind -> value).
_AUTO_ANSWERS: dict[str, object] = {}


def is_interactive() -> bool:
    """Whether a modal dialog would reach a person who can dismiss it.

    Returns
    -------
    bool
        ``True`` only when a ``QApplication`` exists *and* it is running on a
        platform with a real window system.
    """
    try:
        from qtpy.QtGui import QGuiApplication
        from qtpy.QtWidgets import QApplication
    except Exception:
        return False
    if QApplication.instance() is None:
        return False
    try:
        return str(QGuiApplication.platformName()).lower() not in _HEADLESS_PLATFORMS
    except Exception:
        return False


@contextlib.contextmanager
def auto_answer(**answers):
    """Answer message boxes from a script instead of from a person.

    Every keyword names a box kind (``question``, ``critical``, ``warning``,
    ``information``, ``about``) and gives the value that kind returns for the
    duration of the block — *without showing anything*, even in an interactive
    session. This is how a confirmation-guarded code path gets tested.

    Parameters
    ----------
    **answers
        ``kind=value`` pairs, e.g. ``question=ChiSurfMessageBox.Yes``.

    Yields
    ------
    dict
        The active answer map (mutable, for nested adjustments).

    Examples
    --------
    >>> with auto_answer(question=ChiSurfMessageBox.No):  # doctest: +SKIP
    ...     tool.delete_selected()   # the "are you sure?" answers No
    """
    previous = dict(_AUTO_ANSWERS)
    _AUTO_ANSWERS.update(answers)
    try:
        yield _AUTO_ANSWERS
    finally:
        _AUTO_ANSWERS.clear()
        _AUTO_ANSWERS.update(previous)


class ChiSurfMessageBox:
    """Headless-safe replacement for the ``QMessageBox`` statics.

    All methods are class methods, so the class is used exactly like
    ``QMessageBox`` itself. The standard-button constants are re-exported as
    class attributes (``ChiSurfMessageBox.Yes`` …) so a call site that compares
    a result never has to import ``QMessageBox`` alongside this class.

    Every call logs; a call only opens a window when :func:`is_interactive` says
    a user is there to close it, or is answered outright by :func:`auto_answer`.
    """

    # ── standard buttons (resolved lazily; see __getattr__ fallback below) ──
    Yes = 0x00004000
    No = 0x00010000
    Ok = 0x00000400
    Cancel = 0x00400000
    Save = 0x00000800
    Discard = 0x00800000
    Abort = 0x00040000
    Retry = 0x00080000
    Ignore = 0x00100000
    Close = 0x00200000
    NoButton = 0x00000000

    # ── internals ───────────────────────────────────────────────────────────
    @staticmethod
    def _standard_button(value):
        """Return *value* as a real ``QMessageBox.StandardButton`` when possible.

        Headless returns must compare equal to ``QMessageBox.Yes`` at the call
        site, which the raw ints already do; converting when Qt is importable
        keeps ``repr`` and any ``isinstance`` check honest as well.

        Parameters
        ----------
        value : int or QMessageBox.StandardButton
            The button flag to normalise.

        Returns
        -------
        int or QMessageBox.StandardButton
            The Qt enum member, or *value* unchanged if Qt is unavailable.
        """
        try:
            from qtpy.QtWidgets import QMessageBox

            return QMessageBox.StandardButton(int(value))
        except Exception:
            return value

    @staticmethod
    def _fortune(informative: str | None) -> str | None:
        """Append the session's fortune to *informative* when that is enabled.

        ChiSurf traditionally garnishes its notification popups with a fortune
        cookie (``settings.fortune``). Keeping it here means the whimsy survives
        the consolidation instead of being tied to one bespoke box class.

        Parameters
        ----------
        informative : str or None
            Second-tier text the caller supplied.

        Returns
        -------
        str or None
            The text with the fortune appended, or unchanged on any failure.
        """
        try:
            import chisurf as cs

            if not cs.core.settings.cs_settings.get("fortune", False):
                return informative
            from chisurf.gui.widgets import fortune as fortune_module

            saying = fortune_module.get_fortune()
        except Exception:
            return informative
        if not saying:
            return informative
        return f"{informative}\n\n{saying}" if informative else str(saying)

    @classmethod
    def _build(cls, kind: str, parent, title: str, message: str, informative, detail, text_format):
        """Build the ``QMessageBox`` shared by every kind of box.

        Parameters
        ----------
        kind : str
            Box kind — picks the icon.
        parent : QWidget or None
            Dialog parent.
        title, message : str
            Caption and body.
        informative : str or None
            Second-tier text below the body.
        detail : str or None
            Long text folded behind "Show Details".
        text_format : str
            ``"plain"``, ``"rich"`` or ``"markdown"``.

        Returns
        -------
        QMessageBox
            The configured (not yet executed) box.
        """
        from qtpy.QtCore import Qt
        from qtpy.QtWidgets import QMessageBox

        icons = {
            "critical": QMessageBox.Critical,
            "warning": QMessageBox.Warning,
            "information": QMessageBox.Information,
            "about": QMessageBox.Information,
            "question": QMessageBox.Question,
        }
        formats = {
            "plain": Qt.PlainText,
            "rich": Qt.RichText,
            "markdown": getattr(Qt, "MarkdownText", Qt.RichText),
        }
        box = QMessageBox(parent)
        box.setIcon(icons.get(kind, QMessageBox.NoIcon))
        box.setWindowTitle(str(title))
        box.setTextFormat(formats.get(text_format, Qt.PlainText))
        box.setText(str(message))
        if informative:
            box.setInformativeText(str(informative))
        if detail:
            box.setDetailedText(str(detail))
            # A traceback or a file listing is unreadable proportionally spaced,
            # and needs a box the user can drag bigger.
            box.setSizeGripEnabled(True)
            box.setStyleSheet(
                'QTextEdit { font-family: "Courier New", Courier, monospace; font-size: 12px; }'
            )
        return box

    @classmethod
    def _show(
        cls,
        kind: str,
        parent,
        title: str,
        message: str,
        level: int,
        *,
        informative: str | None = None,
        detail: str | None = None,
        text_format: str = "plain",
        fortune: bool = False,
        shown_result=None,
        headless_result=None,
    ):
        """Log the message, then show it only when someone can dismiss it.

        Parameters
        ----------
        kind : str
            Box kind — ``critical``/``warning``/``information``/``about``.
        parent : QWidget or None
            Dialog parent.
        title, message : str
            Dialog caption and body.
        level : int
            Logging level for the unconditional log record.
        informative : str, optional
            Second-tier text shown below the body.
        detail : str, optional
            Long text (a traceback, a file list) folded behind "Show Details".
        text_format : str
            ``"plain"`` (default), ``"rich"`` or ``"markdown"``.
        fortune : bool
            Append the session's fortune cookie when that setting is on.
        shown_result, headless_result : object
            Value returned when the box was / was not shown.

        Returns
        -------
        object
            ``shown_result`` or ``headless_result``.
        """
        logger.log(level, "%s: %s", title, "\n".join(
            str(part) for part in (message, informative, detail) if part
        ))
        if kind in _AUTO_ANSWERS:
            return _AUTO_ANSWERS[kind]
        if not is_interactive():
            return headless_result
        from qtpy.QtWidgets import QMessageBox

        if fortune:
            informative = cls._fortune(informative)
        box = cls._build(kind, parent, title, message, informative, detail, text_format)
        box.setStandardButtons(QMessageBox.Ok)
        box.exec_()
        return shown_result

    # ── public API ──────────────────────────────────────────────────────────
    @classmethod
    def critical(cls, parent, title: str, message: str, *, informative: str | None = None,
                 detail: str | None = None, text_format: str = "plain") -> bool:
        """Report an error; log it always, show it when a user is present.

        Parameters
        ----------
        parent : QWidget or None
            Dialog parent.
        title, message : str
            Caption and body.
        informative : str, optional
            Second-tier text shown below the body.
        detail : str, optional
            Long text (e.g. a traceback) folded behind "Show Details".
        text_format : str
            ``"plain"`` (default), ``"rich"`` or ``"markdown"``.

        Returns
        -------
        bool
            Whether the dialog was actually shown.
        """
        return cls._show(
            "critical", parent, title, message, logging.ERROR,
            informative=informative, detail=detail, text_format=text_format,
            shown_result=True, headless_result=False,
        )

    #: ``error`` reads better at a call site than Qt's ``critical``.
    error = critical

    @classmethod
    def warning(cls, parent, title: str, message: str, *, informative: str | None = None,
                detail: str | None = None, text_format: str = "plain") -> bool:
        """Report a warning; log it always, show it when a user is present."""
        return cls._show(
            "warning", parent, title, message, logging.WARNING,
            informative=informative, detail=detail, text_format=text_format,
            shown_result=True, headless_result=False,
        )

    @classmethod
    def information(cls, parent, title: str, message: str, *, informative: str | None = None,
                    detail: str | None = None, text_format: str = "plain",
                    fortune: bool = False) -> bool:
        """Report a notice; log it always, show it when a user is present.

        Set *fortune* on the app's own notification popups to append the
        session's fortune cookie (when ``settings.fortune`` is enabled).
        """
        return cls._show(
            "information", parent, title, message, logging.INFO,
            informative=informative, detail=detail, text_format=text_format,
            fortune=fortune, shown_result=True, headless_result=False,
        )

    @classmethod
    def about(cls, parent, title: str, message: str, *, text_format: str = "plain") -> bool:
        """Show an "about" box; log it always, show it when a user is present."""
        return cls._show(
            "about", parent, title, message, logging.INFO,
            text_format=text_format, shown_result=True, headless_result=False,
        )

    @classmethod
    def question(cls, parent, title: str, message: str, buttons=None, default=None, *,
                 informative: str | None = None, detail: str | None = None,
                 text_format: str = "plain"):
        """Ask a question and return the button the user pressed.

        Unlike the ``QMessageBox`` static this never blocks a run with nobody at
        the keyboard: headless (or under :func:`auto_answer`) it returns
        *default* immediately, which is why *default* must name the **safe**
        answer — the one that declines a deletion or an overwrite.

        Parameters
        ----------
        parent : QWidget or None
            Dialog parent.
        title, message : str
            Caption and body.
        buttons : QMessageBox.StandardButtons, optional
            Offered buttons. Defaults to ``Yes | No``.
        default : QMessageBox.StandardButton, optional
            Pre-selected button *and* the answer returned headlessly. Defaults
            to ``No`` when it is among *buttons*, else the first offered button.
        informative : str, optional
            Second-tier text shown below the body.
        detail : str, optional
            Long text folded behind "Show Details".
        text_format : str
            ``"plain"`` (default), ``"rich"`` or ``"markdown"``.

        Returns
        -------
        QMessageBox.StandardButton
            The pressed button; comparable against ``QMessageBox.Yes`` etc.
        """
        if buttons is None:
            buttons = cls.Yes | cls.No
        if default is None:
            default = cls.No if int(buttons) & int(cls.No) else int(buttons) & -int(buttons)
        logger.info("%s: %s", title, "\n".join(
            str(part) for part in (message, informative, detail) if part
        ))

        if "question" in _AUTO_ANSWERS:
            return cls._standard_button(_AUTO_ANSWERS["question"])
        if not is_interactive():
            logger.info("%s: not interactive, answering with the default button", title)
            return cls._standard_button(default)

        from qtpy.QtWidgets import QMessageBox

        box = cls._build("question", parent, title, message, informative, detail, text_format)
        box.setStandardButtons(QMessageBox.StandardButtons(int(buttons)))
        box.setDefaultButton(QMessageBox.StandardButton(int(default)))
        return box.exec_()

    @classmethod
    def confirm(cls, parent, title: str, message: str, *, default: bool = False,
                informative: str | None = None, detail: str | None = None) -> bool:
        """Ask a yes/no question and return the answer as a plain ``bool``.

        The boolean form for the common "are you sure?" guard. *default* is the
        answer returned headlessly and defaults to ``False``, so an unattended
        run never confirms a destructive action by accident.

        Parameters
        ----------
        parent : QWidget or None
            Dialog parent.
        title, message : str
            Caption and body.
        default : bool
            Answer used when no user is present.
        informative : str, optional
            Second-tier text shown below the body.
        detail : str, optional
            Long text folded behind "Show Details".

        Returns
        -------
        bool
            ``True`` when the user chose Yes.
        """
        answer = cls.question(
            parent, title, message,
            buttons=cls.Yes | cls.No,
            default=cls.Yes if default else cls.No,
            informative=informative,
            detail=detail,
        )
        return int(answer) == int(cls.Yes)

    @classmethod
    def choice(cls, parent, title: str, message: str, options, *, default: str | None = None,
               kind: str = "question", informative: str | None = None,
               detail: str | None = None, checkbox: str | None = None,
               checkbox_default: bool = False) -> Answer:
        """Offer custom-labelled buttons and report which one was pressed.

        The general form behind every hand-built ``QMessageBox`` — "Overwrite /
        Skip / Cancel", "Register in database / Save to file", "Update / Skip" —
        so those stop being one-off widget code that hangs a headless run.

        Parameters
        ----------
        parent : QWidget or None
            Dialog parent.
        title, message : str
            Caption and body.
        options : Mapping or sequence of (key, label)
            The offered buttons, in order. Keys are what the caller compares
            against; labels are what the user reads.
        default : str, optional
            Key of the pre-selected button *and* the answer returned headlessly.
            Defaults to ``None`` — headless, no option is chosen, which is the
            safe outcome for an overwrite or a deletion.
        kind : str
            Icon to use (``"question"``, ``"warning"``, ``"critical"``,
            ``"information"``).
        informative : str, optional
            Second-tier text shown below the body.
        detail : str, optional
            Long text folded behind "Show Details".
        checkbox : str, optional
            Label of a tick box shown in the box (e.g. "Don't ask again" or a
            mandatory acknowledgement); its state is returned in the answer.
        checkbox_default : bool
            Initial (and headless) state of that tick box.

        Returns
        -------
        Answer
            ``(key, checked)``; ``key`` is ``None`` when the box was dismissed
            or no user was present. Truthy exactly when a key was chosen.

        Examples
        --------
        >>> answer = ChiSurfMessageBox.choice(       # doctest: +SKIP
        ...     self, "Folder exists", f"'{path}' already exists.",
        ...     {"overwrite": "Overwrite", "skip": "Skip", "cancel": "Cancel"},
        ...     default="skip",
        ... )
        >>> if answer.key == "overwrite":            # doctest: +SKIP
        ...     ...
        """
        items = list(options.items()) if hasattr(options, "items") else [tuple(o) for o in options]
        logger.info("%s: %s [%s]", title, "\n".join(
            str(part) for part in (message, informative, detail) if part
        ), ", ".join(str(label) for _, label in items))

        if "choice" in _AUTO_ANSWERS:
            scripted = _AUTO_ANSWERS["choice"]
            return scripted if isinstance(scripted, Answer) else Answer(scripted, checkbox_default)
        if not is_interactive():
            logger.info("%s: not interactive, answering with %r", title, default)
            return Answer(default, checkbox_default)

        from qtpy.QtWidgets import QCheckBox, QMessageBox

        box = cls._build(kind, parent, title, message, informative, detail, "plain")
        buttons = {}
        for key, label in items:
            role = QMessageBox.DestructiveRole if key == "cancel" else QMessageBox.ActionRole
            buttons[key] = box.addButton(str(label), role)
            if key == default:
                box.setDefaultButton(buttons[key])
        tick = None
        if checkbox:
            tick = QCheckBox(str(checkbox))
            tick.setChecked(bool(checkbox_default))
            box.setCheckBox(tick)
        box.exec_()
        clicked = box.clickedButton()
        chosen = next((key for key, button in buttons.items() if button is clicked), None)
        return Answer(chosen, bool(tick.isChecked()) if tick is not None else False)

    @classmethod
    def exception(cls, parent, title: str, exc: BaseException, *, message: str | None = None) -> bool:
        """Report a caught exception with its traceback behind "Show Details".

        Parameters
        ----------
        parent : QWidget or None
            Dialog parent.
        title : str
            Caption.
        exc : BaseException
            The caught exception.
        message : str, optional
            Body text; defaults to ``str(exc)``.

        Returns
        -------
        bool
            Whether the dialog was actually shown.
        """
        import traceback

        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        return cls.critical(parent, title, message or str(exc) or type(exc).__name__, detail=detail)


# ── module-level shorthands (the form used at call sites) ──────────────────
#
# These delegate at *call* time rather than aliasing the bound classmethods, so
# a test that patches a method on :class:`ChiSurfMessageBox` also intercepts the
# ``dialogs.warning(...)`` spelling every call site uses.


def critical(*args, **kwargs):
    """Report an error — see :meth:`ChiSurfMessageBox.critical`."""
    return ChiSurfMessageBox.critical(*args, **kwargs)


def error(*args, **kwargs):
    """Report an error — see :meth:`ChiSurfMessageBox.critical`."""
    return ChiSurfMessageBox.critical(*args, **kwargs)


def warning(*args, **kwargs):
    """Report a warning — see :meth:`ChiSurfMessageBox.warning`."""
    return ChiSurfMessageBox.warning(*args, **kwargs)


def information(*args, **kwargs):
    """Report a notice — see :meth:`ChiSurfMessageBox.information`."""
    return ChiSurfMessageBox.information(*args, **kwargs)


def question(*args, **kwargs):
    """Ask a question — see :meth:`ChiSurfMessageBox.question`."""
    return ChiSurfMessageBox.question(*args, **kwargs)


def confirm(*args, **kwargs):
    """Ask a yes/no question — see :meth:`ChiSurfMessageBox.confirm`."""
    return ChiSurfMessageBox.confirm(*args, **kwargs)


def choice(*args, **kwargs):
    """Offer custom buttons — see :meth:`ChiSurfMessageBox.choice`."""
    return ChiSurfMessageBox.choice(*args, **kwargs)


def about(*args, **kwargs):
    """Show an "about" box — see :meth:`ChiSurfMessageBox.about`."""
    return ChiSurfMessageBox.about(*args, **kwargs)


def report_exception(*args, **kwargs):
    """Report a caught exception — see :meth:`ChiSurfMessageBox.exception`."""
    return ChiSurfMessageBox.exception(*args, **kwargs)


#: Historical names kept so existing imports keep working.
report_error = critical
report_warning = warning
report_information = information
