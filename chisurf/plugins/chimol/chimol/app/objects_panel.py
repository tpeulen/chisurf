from __future__ import annotations

from collections.abc import Callable
from typing import Any, Dict, Optional

from qtpy import QtCore, QtWidgets

from ..colors import _OBJECT_ID_ROLE
from .object_menus import OBJECT_MENUS, MenuEntry


class ObjectsDock(QtCore.QObject):
    """Objects panel — content widget (no outer QDockWidget wrapper).

    Carries PyMOL's five per-object menus (A/S/H/L/C). They are the panel most
    PyMOL users drive the program from, so they are laid out and labelled exactly
    as PyMOL lays them out; see :mod:`.object_menus`.
    """

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
        self._widget = QtWidgets.QWidget(parent)
        layout = QtWidgets.QVBoxLayout(self._widget)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)

        objects_group = QtWidgets.QGroupBox("Loaded Molecules", self._widget)
        objects_layout = QtWidgets.QVBoxLayout(objects_group)
        objects_layout.setContentsMargins(4, 8, 4, 4)
        objects_layout.setSpacing(4)

        # PyMOL's A S H L C row, in PyMOL's order.
        button_row = QtWidgets.QHBoxLayout()
        button_row.setSpacing(2)
        self._menu_buttons: dict[str, QtWidgets.QToolButton] = {}
        for key, title, entries in OBJECT_MENUS:
            button = QtWidgets.QToolButton(objects_group)
            button.setText(key)
            button.setToolTip(f"{title} — for the selected molecule")
            button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
            button.setMenu(self._build_menu(button, f"{title}:", entries))
            button_row.addWidget(button)
            self._menu_buttons[key] = button
        button_row.addStretch(1)
        objects_layout.addLayout(button_row)

        self.object_list = QtWidgets.QListWidget(objects_group)
        self.object_list.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection,
        )
        # Right-clicking a molecule is the other way into the same menus, which
        # is how PyMOL behaves.
        self.object_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.object_list.customContextMenuRequested.connect(self._on_context_menu)
        objects_layout.addWidget(self.object_list)
        layout.addWidget(objects_group)

    # ------------------------------------------------------------------ #
    # Menus
    # ------------------------------------------------------------------ #
    def set_run_command(self, run_command: Callable[[str], None] | None) -> None:
        """Set the callable that executes a chimol command line."""
        self._run_command = run_command

    def _build_menu(
        self,
        parent: QtWidgets.QWidget,
        header: str,
        entries: tuple[MenuEntry, ...],
    ) -> QtWidgets.QMenu:
        """Build a QMenu from a declarative table, preserving order and gaps."""
        menu = QtWidgets.QMenu(header, parent)
        # PyMOL prints the menu's purpose as its first, inert row.
        title = menu.addAction(header)
        title.setEnabled(False)
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
                if entry.note:
                    sub.setToolTip(entry.note)
                self._populate(sub, entry.children)
                continue
            action = menu.addAction(entry.label)
            if entry.note:
                action.setToolTip(entry.note)
            if entry.command is None:
                # Shown, disabled, and explained -- see the module docstring for
                # why the entry is kept rather than dropped.
                action.setEnabled(False)
                action.setToolTip(entry.note or "Not implemented in Chimol.")
                continue
            action.triggered.connect(
                lambda _checked=False, e=entry: self._run_entry(e)
            )
        menu.setToolTipsVisible(True)

    def _run_entry(self, entry: MenuEntry) -> None:
        """Fill in the target (and any prompted value) and run the command."""
        if self._run_command is None or entry.command is None:
            return
        target = self.current_object_name() or "all"

        text = None
        if entry.prompt is not None:
            title, question = entry.prompt
            text, ok = QtWidgets.QInputDialog.getText(
                self._widget, title, question
            )
            if not ok or not str(text).strip():
                return
            text = str(text).strip()

        for line in entry.command.split(";"):
            line = line.strip()
            if not line:
                continue
            line = line.replace("{sele}", target)
            if text is not None:
                line = line.replace("{text}", text)
            self._run_command(line)

    def current_object_name(self) -> Optional[str]:
        """Name of the highlighted molecule, or ``None`` when nothing is."""
        item = self.object_list.currentItem()
        if item is None:
            return None
        return item.text() or None

    def _on_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.object_list.itemAt(pos)
        if item is not None:
            self.object_list.setCurrentItem(item)
        menu = QtWidgets.QMenu(self.object_list)
        for key, title, entries in OBJECT_MENUS:
            sub = menu.addMenu(title)
            self._populate(sub, entries)
        menu.exec_(self.object_list.viewport().mapToGlobal(pos))

    @property
    def widget(self) -> QtWidgets.QWidget:
        return self._widget

    def create_item(
        self,
        object_id: str,
        entry: Dict[str, Any],
    ) -> QtWidgets.QListWidgetItem:
        item = QtWidgets.QListWidgetItem(entry.get("name", object_id))
        item.setFlags(
            item.flags()
            | QtCore.Qt.ItemIsUserCheckable
            | QtCore.Qt.ItemIsSelectable
        )
        item.setCheckState(QtCore.Qt.Checked)
        item.setData(_OBJECT_ID_ROLE, object_id)
        return item

    def set_current_object(self, object_id: Optional[str]) -> None:
        for i in range(self.object_list.count()):
            item = self.object_list.item(i)
            if item is None:
                continue
            oid = item.data(_OBJECT_ID_ROLE)
            if oid == object_id:
                self.object_list.setCurrentItem(item)
                return

    def set_item_checked(self, object_id: str, checked: bool) -> None:
        for i in range(self.object_list.count()):
            item = self.object_list.item(i)
            if item is None:
                continue
            oid = item.data(_OBJECT_ID_ROLE)
            if oid == object_id:
                item.setCheckState(
                    QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked,
                )
                return
