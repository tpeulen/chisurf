"""The objects panel, laid out like PyMOL's.

PyMOL's panel is a stack of rows, one per object, and **the A/S/H/L/C buttons
live on the row** — they act on that molecule, not on whatever happens to be
selected. Above them sits a permanent ``all`` row whose buttons act on
everything. Getting that wrong is not cosmetic: a single shared button row
silently retargets every menu action to the current selection, which is the one
thing a PyMOL user would never expect.

The look follows PyMOL too — dark panel, monospace, enabled objects in green,
the grey ``all`` header, periwinkle buttons with a rainbow ``C`` — because the
point of copying the layout is that it is recognisable at a glance.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Dict, Optional

from qtpy import QtCore, QtGui, QtWidgets

from ..colors import _OBJECT_ID_ROLE
from .object_menus import OBJECT_MENUS, MenuEntry

#: PyMOL's panel palette, read off its internal GUI.
_PANEL_BG = "#000000"
_HEADER_BG = "#808080"
_HEADER_FG = "#000000"
_ENABLED_FG = "#00e000"      # an enabled object's name
_DISABLED_FG = "#707070"     # a disabled one greys out
_BUTTON_BG = "#9d9dff"
_BUTTON_FG = "#101060"
_MENU_BG = "#3a3a3a"
_MENU_FG = "#f0f0f0"
_MENU_TITLE_BG = "#4a4a8a"

#: The C button's rainbow, left to right.
_COLOR_BUTTON_STOPS = ("#ff0000", "#ffff00", "#00ff00", "#00ffff", "#0000ff")

_MONO = "Menlo, Monaco, 'Courier New', monospace"

_BUTTON_STYLE = f"""
QToolButton {{
    background: {_BUTTON_BG};
    color: {_BUTTON_FG};
    border: 1px solid #202060;
    font-family: {_MONO};
    font-weight: bold;
    padding: 0px;
    margin: 0px;
    min-width: 16px;
    max-width: 18px;
    min-height: 16px;
}}
QToolButton:hover {{ background: #c0c0ff; }}
QToolButton::menu-indicator {{ image: none; width: 0px; }}
"""

_COLOR_BUTTON_STYLE = f"""
QToolButton {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {_COLOR_BUTTON_STOPS[0]}, stop:0.25 {_COLOR_BUTTON_STOPS[1]},
        stop:0.5 {_COLOR_BUTTON_STOPS[2]}, stop:0.75 {_COLOR_BUTTON_STOPS[3]},
        stop:1 {_COLOR_BUTTON_STOPS[4]});
    color: #000000;
    border: 1px solid #202060;
    font-family: {_MONO};
    font-weight: bold;
    padding: 0px;
    margin: 0px;
    min-width: 16px;
    max-width: 18px;
    min-height: 16px;
}}
QToolButton::menu-indicator {{ image: none; width: 0px; }}
"""

_MENU_STYLE = f"""
QMenu {{
    background: {_MENU_BG};
    color: {_MENU_FG};
    font-family: {_MONO};
    border: 1px solid #909090;
}}
QMenu::item:selected {{ background: {_MENU_TITLE_BG}; }}
QMenu::item:disabled {{ color: #909090; }}
QMenu::separator {{ height: 1px; background: #909090; margin: 2px 0px; }}
"""


class _MenuHost(QtCore.QObject):
    """Builds the five menus for one target and keeps them wired to it.

    Split out because both the ``all`` header and every object row need exactly
    the same five menus, differing only in what ``{sele}`` expands to.
    """

    def __init__(
        self,
        parent: QtWidgets.QWidget,
        target: Callable[[], str],
        run_command: Callable[[Callable[[], str], MenuEntry], None],
    ) -> None:
        super().__init__(parent)
        self._target = target
        self._run = run_command
        self.buttons: dict[str, QtWidgets.QToolButton] = {}
        for key, title, entries in OBJECT_MENUS:
            button = QtWidgets.QToolButton(parent)
            button.setText(key)
            button.setToolTip(f"{title} — {target()}")
            button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
            button.setStyleSheet(
                _COLOR_BUTTON_STYLE if key == "C" else _BUTTON_STYLE
            )
            button.setMenu(self._build_menu(button, f"{title}:", entries))
            self.buttons[key] = button

    def strip(self, parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Return the five buttons as one gap-free strip.

        A single widget rather than five loose ones, for two reasons: the
        buttons read as one control -- they are five menus over the same
        selection -- and every row then gets the identical strip, so the columns
        cannot drift apart between a group row, a member row and the header.
        """
        holder = QtWidgets.QWidget(parent)
        layout = QtWidgets.QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for key, _, _ in OBJECT_MENUS:
            layout.addWidget(self.buttons[key])
        return holder

    def _build_menu(
        self,
        parent: QtWidgets.QWidget,
        header: str,
        entries: tuple[MenuEntry, ...],
    ) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu(header, parent)
        menu.setStyleSheet(_MENU_STYLE)
        # PyMOL prints the menu's purpose as an inert first row.
        title = menu.addAction(header)
        title.setEnabled(False)
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        menu.addSeparator()
        self._populate(menu, entries)
        return menu

    def _populate(self, menu: QtWidgets.QMenu, entries) -> None:
        for entry in entries:
            if entry.is_separator:
                menu.addSeparator()
                continue
            if entry.is_submenu:
                sub = menu.addMenu(entry.label)
                sub.setStyleSheet(_MENU_STYLE)
                if entry.note:
                    sub.setToolTip(entry.note)
                self._populate(sub, entry.children)
                continue
            action = menu.addAction(entry.label)
            if entry.note:
                action.setToolTip(entry.note)
            if entry.color:
                action.setIcon(_swatch(entry.color))
            if entry.command is None:
                # Shown, disabled and explained: dropping it would change the
                # menu's shape, and wiring it to something approximate would
                # misreport what happened.
                action.setEnabled(False)
                action.setToolTip(entry.note or "Not implemented in Chimol.")
                continue
            action.triggered.connect(
                lambda _checked=False, e=entry: self._run(self._target, e)
            )
        menu.setToolTipsVisible(True)


def _swatch(color: str) -> QtGui.QIcon:
    """Return a small colour chip, standing in for PyMOL's coloured text."""
    pixmap = QtGui.QPixmap(10, 10)
    pixmap.fill(QtGui.QColor(color))
    return QtGui.QIcon(pixmap)


#: Item role carrying a group row's name. Distinct from ``_OBJECT_ID_ROLE``
#: because a group is not an object: nothing may look one up in the viewer's
#: object registry, and code that iterates rows has to be able to tell them
#: apart rather than guessing from the absence of an id.
_GROUP_NAME_ROLE = _OBJECT_ID_ROLE + 1


class GroupRow(QtWidgets.QWidget):
    """A group's header: a disclosure marker, its name, and its A/S/H/L/C.

    The menus are the same five as an object's, because in PyMOL a group can be
    used wherever an object name can and the command applies to every member --
    ``hide everything, kinases`` hides all of them. That is handled in the
    command layer by expanding a group name to its members, so this row needs no
    special-casing beyond passing the group's name as the selection.
    """

    def __init__(
        self,
        parent: QtWidgets.QWidget,
        group: str,
        is_open: bool,
        run_command: Callable[[Callable[[], str], MenuEntry], None],
    ) -> None:
        super().__init__(parent)
        self._group = group

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(2)

        self.disclosure = QtWidgets.QToolButton(self)
        self.disclosure.setAutoRaise(True)
        self.disclosure.setText(("▾ " if is_open else "▸ ") + group)
        self.disclosure.setStyleSheet(
            f"QToolButton {{ color: {_ENABLED_FG}; font-family: {_MONO}; "
            "border: none; }"
        )
        self.disclosure.clicked.connect(
            lambda: run_command(
                lambda: self._group, MenuEntry("toggle", "group {sele}, toggle")
            )
        )
        layout.addWidget(self.disclosure)
        layout.addStretch(1)

        self._menus = _MenuHost(self, lambda: self._group, run_command)
        layout.addWidget(self._menus.strip(self))

    @property
    def group(self) -> str:
        """Name of the group this row stands for."""
        return self._group

    @property
    def buttons(self) -> dict[str, QtWidgets.QToolButton]:
        """The row's five menu buttons, keyed by letter."""
        return self._menus.buttons

    def set_open(self, is_open: bool) -> None:
        """Update the disclosure marker without rebuilding the row."""
        self.disclosure.setText(("▾ " if is_open else "▸ ") + self._group)


class ObjectRow(QtWidgets.QWidget):
    """One molecule: a visibility box, its name, and its own A/S/H/L/C."""

    def __init__(
        self,
        parent: QtWidgets.QWidget,
        object_id: str,
        name: str,
        run_command: Callable[[Callable[[], str], MenuEntry], None],
        on_toggled: Callable[[str, bool], None],
        on_clicked: Callable[[str], None],
        indent: int = 0,
    ) -> None:
        super().__init__(parent)
        self._object_id = object_id
        self._name = name
        self._on_clicked = on_clicked

        layout = QtWidgets.QHBoxLayout(self)
        # Group members are indented so the hierarchy is visible at a glance,
        # the way it is in PyMOL's panel. The indent goes in the margin rather
        # than as a spacer widget, so the A/S/H/L/C buttons still line up with
        # every other row's -- indenting the whole row instead would push them
        # out of column, which is the alignment defect this panel already had.
        layout.setContentsMargins(2 + int(indent), 0, 2, 0)
        layout.setSpacing(2)

        self.check = QtWidgets.QCheckBox(name, self)
        self.check.setChecked(True)
        self.check.setStyleSheet(
            f"QCheckBox {{ color: {_ENABLED_FG}; font-family: {_MONO}; }}"
        )
        self.check.toggled.connect(
            lambda checked: self._on_toggled(checked, on_toggled)
        )
        layout.addWidget(self.check)

        # PyMOL prints the state counter next to the name, e.g. "1/1".
        self.state_label = QtWidgets.QLabel("", self)
        self.state_label.setStyleSheet(
            f"QLabel {{ color: {_ENABLED_FG}; font-family: {_MONO}; "
            "background: transparent; }"
        )
        layout.addWidget(self.state_label)
        layout.addStretch(1)

        self._menus = _MenuHost(self, lambda: self._name, run_command)
        layout.addWidget(self._menus.strip(self))

    @property
    def object_id(self) -> str:
        """Identifier of the molecule this row stands for."""
        return self._object_id

    @property
    def buttons(self) -> dict[str, QtWidgets.QToolButton]:
        """The row's five menu buttons, keyed by letter."""
        return self._menus.buttons

    def set_state(self, current: int, total: int) -> None:
        """Show PyMOL's ``current/total`` state counter, or nothing if static."""
        # The leading space keeps the counter off the name; PyMOL columns them.
        self.state_label.setText(
            f" {int(current)}/{int(total)}" if int(total) > 0 else ""
        )

    def set_checked(self, checked: bool) -> None:
        """Set the visibility box without re-emitting the toggle."""
        blocked = self.check.blockSignals(True)
        try:
            self.check.setChecked(checked)
        finally:
            self.check.blockSignals(blocked)
        self._recolor(checked)

    def _on_toggled(self, checked: bool, callback) -> None:
        self._recolor(checked)
        callback(self._object_id, checked)

    def _recolor(self, checked: bool) -> None:
        # PyMOL greys out a disabled object's name; the row stays in place.
        color = _ENABLED_FG if checked else _DISABLED_FG
        self.check.setStyleSheet(
            f"QCheckBox {{ color: {color}; font-family: {_MONO}; }}"
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Clicking anywhere on the row makes it the active molecule."""
        self._on_clicked(self._object_id)
        super().mousePressEvent(event)


class ObjectsDock(QtCore.QObject):
    """Objects panel — content widget (no outer QDockWidget wrapper)."""

    def __init__(
        self,
        parent: QtWidgets.QWidget,
        *,
        margins: tuple[int, int, int, int],
        spacing: int,
        run_command: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._run_command = run_command
        self._rows: Dict[str, ObjectRow] = {}
        self._group_rows: Dict[str, GroupRow] = {}
        self._widget = QtWidgets.QWidget(parent)
        layout = QtWidgets.QVBoxLayout(self._widget)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)

        objects_group = QtWidgets.QGroupBox("Loaded Molecules", self._widget)
        objects_layout = QtWidgets.QVBoxLayout(objects_group)
        objects_layout.setContentsMargins(4, 8, 4, 4)
        objects_layout.setSpacing(2)

        # PyMOL's permanent `all` row, above the objects and acting on them all.
        header = QtWidgets.QWidget(objects_group)
        header.setStyleSheet(f"background: {_HEADER_BG};")
        header_layout = QtWidgets.QHBoxLayout(header)
        header_layout.setContentsMargins(2, 1, 2, 1)
        header_layout.setSpacing(2)
        label = QtWidgets.QLabel("all", header)
        label.setStyleSheet(
            f"color: {_HEADER_FG}; font-family: {_MONO}; background: transparent;"
        )
        header_layout.addWidget(label)
        header_layout.addStretch(1)
        self._header_layout = header_layout
        self._all_menus = _MenuHost(header, lambda: "all", self._run_entry)
        header_layout.addWidget(self._all_menus.strip(header))
        objects_layout.addWidget(header)

        self.object_list = QtWidgets.QListWidget(objects_group)
        self.object_list.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection,
        )
        self.object_list.setStyleSheet(
            f"QListWidget {{ background: {_PANEL_BG}; border: 1px solid #505050; }}"
            # The row widget carries the visible checkbox; the item keeps the
            # state for the existing handlers but must not draw a second box.
            "QListWidget::indicator { width: 0px; height: 0px; }"
            "QListWidget::item:selected { background: #202038; }"
            # No item padding: the row widget is sized to the viewport so that
            # its buttons line up with the  header's, and any inset here
            # shifts that column out of true.
            "QListWidget::item { padding: 0px; margin: 0px; }"
        )
        # Rows are sized to the viewport, so they have to be re-sized when it
        # changes -- otherwise widening the panel leaves the buttons where the
        # old width put them.
        self.object_list.viewport().installEventFilter(self)
        objects_layout.addWidget(self.object_list)
        layout.addWidget(objects_group)

    def _row_width(self) -> int:
        """Width a row should span: the list's viewport, less its margins."""
        try:
            return max(int(self.object_list.viewport().width()) - 4, 120)
        except Exception:
            return 320

    def _sync_header_inset(self) -> None:
        """Inset the header by whatever the list's scrollbar is taking.

        The rows are sized to the *viewport*, which excludes a vertical
        scrollbar; the header is an ordinary widget and spans the whole panel. So
        the moment the list grows a scrollbar the two columns of buttons stop
        lining up -- by exactly the scrollbar's width.
        """
        layout = getattr(self, "_header_layout", None)
        if layout is None:
            return
        bar = self.object_list.verticalScrollBar()
        inset = bar.width() if bar is not None and bar.isVisible() else 0
        left, top, _, bottom = layout.getContentsMargins()
        layout.setContentsMargins(left, top, 2 + int(inset), bottom)

    def eventFilter(self, watched, event):  # noqa: N802 - Qt's spelling
        """Re-stretch every row when the list is resized."""
        if event.type() == QtCore.QEvent.Resize and watched is (
            self.object_list.viewport()
        ):
            width = self._row_width()
            for index in range(self.object_list.count()):
                item = self.object_list.item(index)
                item.setSizeHint(QtCore.QSize(width, item.sizeHint().height()))
            self._sync_header_inset()
        return super().eventFilter(watched, event)

    # ------------------------------------------------------------------ #
    # Wiring
    # ------------------------------------------------------------------ #
    @property
    def widget(self) -> QtWidgets.QWidget:
        """The panel's content widget."""
        return self._widget

    def set_run_command(self, run_command: Callable[[str], None] | None) -> None:
        """Set the callable that executes a chimol command line."""
        self._run_command = run_command

    @property
    def all_buttons(self) -> dict[str, QtWidgets.QToolButton]:
        """The ``all`` row's five menu buttons."""
        return self._all_menus.buttons

    def row(self, object_id: str) -> Optional[ObjectRow]:
        """Return the row widget for ``object_id``, if it has one."""
        return self._rows.get(object_id)

    def _run_entry(self, target: Callable[[], str], entry: MenuEntry) -> None:
        """Expand a menu entry against its own row's target and run it."""
        if self._run_command is None or entry.command is None:
            return

        text = None
        if entry.prompt is not None:
            title, question = entry.prompt
            text, ok = QtWidgets.QInputDialog.getText(
                self._widget, title, question
            )
            if not ok or not str(text).strip():
                return
            text = str(text).strip()

        name = target()
        for line in entry.command.split(";"):
            line = line.strip()
            if not line:
                continue
            if text is not None:
                line = line.replace("{text}", text)
            for target_name in self._targets_for(line, name):
                self._run_command(line.replace("{sele}", target_name))

    #: Commands that take a group name themselves, so must not be expanded into
    #: one call per member. `group kinases, toggle` run per member would toggle
    #: nothing and complain about objects that are not groups.
    _GROUP_AWARE = ("group", "ungroup", "order", "delete", "del")

    def _targets_for(self, line: str, name: str) -> list[str]:
        """Names to substitute for ``{sele}`` — a group becomes its members.

        PyMOL: "Group objects can typically be used as arguments to commands. In
        such cases, the command should be applied to all members of the group."
        The selection resolver here answers for one object at a time, so the
        expansion happens where the target is known instead: the group's row
        runs the entry once per member.
        """
        verb = line.split(None, 1)[0].strip().lower() if line.strip() else ""
        if verb in self._GROUP_AWARE:
            return [name]
        viewer = getattr(self.parent(), "viewer", None)
        members = getattr(viewer, "group_members", None)
        if not callable(members):
            return [name]
        try:
            ids = members(name)
        except Exception:
            return [name]
        if not ids:
            return [name]
        by_id = {
            str(o.get("id")): str(o.get("name", "")) for o in viewer.list_objects()
        }
        return [by_id.get(oid) or oid for oid in ids]

    # ------------------------------------------------------------------ #
    # List items
    # ------------------------------------------------------------------ #
    def create_item(
        self,
        object_id: str,
        entry: Dict[str, Any],
    ) -> QtWidgets.QListWidgetItem:
        """Build the list item for a molecule (its row widget is attached later)."""
        item = QtWidgets.QListWidgetItem(entry.get("name", object_id))
        item.setFlags(
            item.flags()
            | QtCore.Qt.ItemIsUserCheckable
            | QtCore.Qt.ItemIsSelectable
        )
        item.setCheckState(QtCore.Qt.Checked)
        item.setData(_OBJECT_ID_ROLE, object_id)
        return item

    def attach_row(
        self,
        item: QtWidgets.QListWidgetItem,
        object_id: str,
        entry: Dict[str, Any],
        *,
        indent: int = 0,
    ) -> ObjectRow:
        """Give ``item`` its PyMOL-style row, once it is in the list.

        Must run after the item is added: Qt can only host a widget for a row
        that exists.
        """
        row = ObjectRow(
            self.object_list,
            object_id,
            str(entry.get("name", object_id)),
            self._run_entry,
            self._set_item_check_state,
            self._select_object,
            indent=indent,
        )
        row.set_state(*self._state_of(object_id))
        # Span the viewport, not the row's own content width. A row sized to its
        # content leaves the layout's stretch nothing to expand into, so the
        # A/S/H/L/C buttons sat immediately after each name -- at a different x on
        # every row, and never lining up with the `all` header's, which is an
        # ordinary widget and so always spanned the panel.
        item.setSizeHint(
            QtCore.QSize(self._row_width(), row.sizeHint().height())
        )
        # The row widget shows the name; the item's own text would render
        # underneath it and show through.
        item.setText("")
        self.object_list.setItemWidget(item, row)
        self._rows[object_id] = row
        self._sync_header_inset()
        return row

    def create_group_item(
        self, group: str, is_open: bool
    ) -> QtWidgets.QListWidgetItem:
        """Build the list item standing for a group row.

        A group is not an object, so it gets no visibility checkbox and no id:
        the marker plus the name is the whole row, and clicking it toggles the
        group open. It is not selectable, because selecting it would make it the
        active object and there is no such object.
        """
        item = QtWidgets.QListWidgetItem("")
        item.setFlags(QtCore.Qt.ItemIsEnabled)
        item.setData(_GROUP_NAME_ROLE, group)
        item.setData(_OBJECT_ID_ROLE, None)
        return item

    def attach_group_row(
        self, item: QtWidgets.QListWidgetItem, group: str, is_open: bool
    ) -> GroupRow:
        """Give a group item its row widget, once it is in the list."""
        row = GroupRow(self.object_list, group, is_open, self._run_entry)
        item.setSizeHint(
            QtCore.QSize(self._row_width(), row.sizeHint().height())
        )
        self.object_list.setItemWidget(item, row)
        self._group_rows[group] = row
        self._sync_header_inset()
        return row

    def _state_of(self, object_id: str) -> tuple[int, int]:
        """Return the current and total frame, as PyMOL's counter shows them."""
        viewer = getattr(self.parent(), "viewer", None)
        if viewer is None:
            return 1, 1
        try:
            total = int(viewer.get_frame_count(object_id))
            current = int(viewer.get_active_frame_index(object_id)) + 1
        except Exception:
            return 1, 1
        return max(current, 1), max(total, 1)

    def update_states(self) -> None:
        """Refresh every row's state counter, e.g. after loading frames."""
        for object_id, row in self._rows.items():
            row.set_state(*self._state_of(object_id))

    def _set_item_check_state(self, object_id: str, checked: bool) -> None:
        """Mirror a row's box onto its item, so existing handlers still fire."""
        for i in range(self.object_list.count()):
            item = self.object_list.item(i)
            if item is None or item.data(_OBJECT_ID_ROLE) != object_id:
                continue
            item.setCheckState(
                QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked
            )
            return

    def _select_object(self, object_id: str) -> None:
        self.set_current_object(object_id)

    def set_current_object(self, object_id: Optional[str]) -> None:
        """Highlight the row for ``object_id``."""
        for i in range(self.object_list.count()):
            item = self.object_list.item(i)
            if item is None:
                continue
            if item.data(_OBJECT_ID_ROLE) == object_id:
                self.object_list.setCurrentItem(item)
                return

    def set_item_checked(self, object_id: str, checked: bool) -> None:
        """Set a molecule's visibility box, item and row together."""
        row = self._rows.get(object_id)
        if row is not None:
            row.set_checked(checked)
        for i in range(self.object_list.count()):
            item = self.object_list.item(i)
            if item is None:
                continue
            if item.data(_OBJECT_ID_ROLE) == object_id:
                item.setCheckState(
                    QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked,
                )
                return

    def clear_rows(self) -> None:
        """Forget the row widgets; call when the list itself is cleared."""
        self._rows.clear()
        self._group_rows.clear()
