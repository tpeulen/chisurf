"""A small, self-contained UI-language selector widget.

This is the one reusable language-picker component for ChiSurf's GUI. It wraps
the Qt-free language machinery in :mod:`chisurf.core.support.i18n` (locale get/set) and
the GUI translation bootstrap in :mod:`chisurf.gui.i18n` (catalogue discovery +
live switch), exposing them as a labelled combo box that any dialog can drop in.

The combo shows each language's *endonym* (``Deutsch``, ``Français`` …) while
storing the two-letter locale *code*; choosing a language persists it to the
user settings and switches the running UI live. Newly opened tools/dialogs
render in the new language immediately; already-open windows fully retranslate
after a restart (Qt reads most static text at build time).

The available languages are discovered from the shipped ``chisurf_<code>.qm``
catalogues, so shipping a new locale makes it appear here with no code change.
"""

from __future__ import annotations

from qtpy import QtCore, QtWidgets

from chisurf.core.support import i18n


class LanguageSelector(QtWidgets.QWidget):
    """A ``🌐 Language: [combo]`` row that persists and live-applies the choice.

    Parameters
    ----------
    parent
        The parent widget, if any.
    show_label
        When ``True`` (default) a leading ``🌐 Language:`` label is shown; set
        ``False`` to embed the bare combo (e.g. inside a form row that already
        supplies its own label).

    Signals
    -------
    languageChanged(str)
        Emitted with the applied locale code after the user picks a language and
        it has been persisted and live-applied.
    """

    languageChanged = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None, *, show_label: bool = True):
        super().__init__(parent)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if show_label:
            self.label = QtWidgets.QLabel("🌐 " + i18n.tr("Language:"), self)
            layout.addWidget(self.label)
        else:
            self.label = None

        self.combo = QtWidgets.QComboBox(self)
        self.combo.setProperty("isLanguage", True)
        self.combo.setToolTip(
            i18n.tr(
                "UI language. Applies to newly opened tools/dialogs immediately; "
                "restart to fully retranslate open windows."
            )
        )
        layout.addWidget(self.combo, 1)

        self._populate()
        self.combo.activated.connect(self._on_activated)

        # Re-sync when the language is changed anywhere else (e.g. the ribbon
        # flag dropdown), so every open picker shows the same current language.
        from chisurf.gui import i18n as gui_i18n

        gui_i18n.language_notifier.language_changed.connect(self._on_external_change)

    def _on_external_change(self, code: str) -> None:
        """Re-select the applied language after an external switch."""
        self._populate(code)

    # -- population -----------------------------------------------------------

    def _populate(self, current: str | None = None) -> None:
        """Fill the combo from the shipped catalogues and preselect ``current``.

        ``current`` defaults to the persisted locale; the app-wide notifier passes
        the *applied* code instead, since a live switch need not be persisted yet.
        """
        from chisurf.core.support import i18n as core_i18n
        from chisurf.gui import i18n as gui_i18n

        if current is None:
            current = core_i18n.get_locale() or core_i18n.DEFAULT_LOCALE
        current = str(current).strip()

        self.combo.blockSignals(True)
        self.combo.clear()
        for code in gui_i18n.available_languages():
            self.combo.addItem(
                gui_i18n.language_flag_icon(code), gui_i18n.language_display_name(code), code
            )

        idx = self.combo.findData(current)
        self.combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo.blockSignals(False)

    def current_code(self) -> str:
        """Return the locale code currently selected in the combo."""
        return str(self.combo.currentData() or "en")

    def refresh(self) -> None:
        """Re-discover catalogues and re-sync the selection with the settings."""
        self._populate()

    # -- change handling ------------------------------------------------------

    def _on_activated(self, _index: int) -> None:
        """Persist the picked language and switch the UI live."""
        from chisurf.core.settings import settings_utils
        from chisurf.gui import i18n as gui_i18n

        applied = _apply_language_choice(self.current_code())
        self.languageChanged.emit(applied)


def _apply_language_choice(code: str) -> str:
    """Persist ``code`` and switch the running UI to it; return the applied code.

    Shared by every language picker (the settings combo and the ribbon flag
    dropdown) so persistence and live-switch behave identically. Persistence is
    best-effort; the live switch is authoritative for the applied code.
    """
    from chisurf.core.settings import settings_utils
    from chisurf.gui import i18n as gui_i18n

    try:
        settings_utils.set_language(code)
    except Exception:  # pragma: no cover - persistence is best-effort
        pass
    return gui_i18n.apply_language(code)


class LanguageFlagSwitcher(QtWidgets.QToolButton):
    """A compact flag-dropdown language switcher for toolbars and ribbons.

    Shows the current language's flag emoji (🇬🇧 / 🇩🇪 / 🇫🇷 …) as a tool button;
    clicking pops up a menu of ``flag  Endonym`` entries. Picking one persists
    and live-switches the UI, mirroring :class:`LanguageSelector`. The button is
    generic enough to reuse in any toolbar/ribbon corner.

    Signals
    -------
    languageChanged(str)
        Emitted with the applied locale code after a language is chosen.
    """

    languageChanged = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        self.setAutoRaise(True)
        self._menu = QtWidgets.QMenu(self)
        self.setMenu(self._menu)
        self.rebuild()

        # Re-sync the flag/menu when the language changes anywhere else.
        from chisurf.gui import i18n as gui_i18n

        gui_i18n.language_notifier.language_changed.connect(self.rebuild)

    def rebuild(self, current: str | None = None) -> None:
        """(Re)build the flag menu from the shipped catalogues + ``current`` locale.

        ``current`` defaults to the persisted locale; the app-wide notifier passes
        the *applied* code instead, since a live switch need not be persisted yet.
        """
        from chisurf.core.support import i18n as core_i18n
        from chisurf.gui import i18n as gui_i18n

        if current is None:
            current = core_i18n.get_locale() or core_i18n.DEFAULT_LOCALE
        current = str(current).strip()

        self._menu.clear()
        for code in gui_i18n.available_languages():
            name = gui_i18n.language_display_name(code)
            action = self._menu.addAction(gui_i18n.language_flag_icon(code, 16), name)
            action.setData(code)
            action.setCheckable(True)
            action.setChecked(code == current)
            action.triggered.connect(lambda _checked=False, c=code: self._select(c))

        # Show the current flag as the button's icon (emoji flags render
        # unreliably in Qt, so a painted icon is used instead of button text).
        self.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        self.setIcon(gui_i18n.language_flag_icon(current, 18))
        self.setIconSize(QtCore.QSize(24, 18))
        self.setToolTip(
            i18n.tr("Language") + f": {gui_i18n.language_display_name(current)}"
        )

    def _select(self, code: str) -> None:
        """Apply the chosen language and refresh the button glyph/menu state."""
        applied = _apply_language_choice(code)
        self.rebuild()
        self.languageChanged.emit(applied)
