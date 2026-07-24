"""Custom AutoForm section: the FCS channel-pair editor table.

Registers the ``fcs_channel_pairs`` custom-section key used by
``fcs_channel_preset.view.json``. The widget is the one part of the editor that
the generic form primitives cannot express: an add-row (two channel combos + an
optional label) above a table whose rows carry per-cell channel combos, an
integer bins/cascades editor, a *fine* checkbox and a delete button.

It is a thin view over :class:`~chisurf.plugins.fcs.fcs_channel_preset.gui.view_model.FCSChannelViewModel`:
all state lives on the model (``model.pairs`` / ``model.channel_names``) and every
edit is written straight back through ``model.add_pair`` / ``model.remove_pair`` /
``model.update_pair``. The widget rebuilds itself when the model emits
``setup_changed`` / ``pairs_changed`` / ``setups_reloaded``.

User-facing strings (column headers, the *Add* label, the A/B labels, the
placeholder, the delete tooltip) arrive from the view spec's ``options`` and are
localized through :func:`chisurf.core.i18n.tr`. Because those same strings live
under ``label`` / ``add_label`` / ``placeholder`` / ``remove_label`` / ``labels``
keys in the JSON, ``build_tools/i18n/extract_strings.py`` collects them into the
translation catalogue automatically.
"""

from __future__ import annotations

import typing

from qtpy import QtCore, QtWidgets

from chisurf.core import i18n
from chisurf.gui.autoform.sections.registry import register_section

#: Delete-column index (after the declared data columns).
_DELETE_COL_OFFSET = 0


@register_section("fcs_channel_pairs")
def _fcs_channel_pairs_factory(model, target: str = "pairs", **options):
    """Build the channel-pair editor bound to ``model`` (custom-section factory)."""
    return FcsChannelPairsWidget(model, target, **options)


class FcsChannelPairsWidget(QtWidgets.QWidget):
    """Add-row + editable table over the model's channel-pair list."""

    def __init__(
        self,
        model,
        target: str = "pairs",
        *,
        columns: typing.Sequence[typing.Mapping[str, str]] = (),
        add_label: str = "Add",
        placeholder: str = "",
        remove_label: str = "Remove this pair",
        labels: typing.Sequence[str] = ("A", "B"),
        parent: QtWidgets.QWidget | None = None,
        **_ignored,
    ) -> None:
        super().__init__(parent)
        self._model = model
        self._loading = False

        self._col_keys = [str(c.get("key", "")) for c in columns]
        self._headers = [i18n.tr(c.get("label", c.get("key", ""))) for c in columns]
        self._add_label = i18n.tr(add_label)
        self._placeholder = i18n.tr(placeholder)
        self._remove_tip = i18n.tr(remove_label)
        ab = list(labels) or ["A", "B"]
        self._a_label = i18n.tr(ab[0]) + ":"
        self._b_label = i18n.tr(ab[1] if len(ab) > 1 else "B") + ":"

        self._build_ui()
        if hasattr(model, "add_observer"):
            model.add_observer(self._on_model_event)
        self._rebuild()

    # ── construction ─────────────────────────────────────────────────
    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        controls = QtWidgets.QHBoxLayout()
        self._combo_a = QtWidgets.QComboBox(self)
        self._combo_b = QtWidgets.QComboBox(self)
        self._edit_name = QtWidgets.QLineEdit(self)
        self._edit_name.setPlaceholderText(self._placeholder)
        self._btn_add = QtWidgets.QToolButton(self)
        self._btn_add.setText(f"＋ {self._add_label}")
        controls.addWidget(QtWidgets.QLabel(self._a_label, self))
        controls.addWidget(self._combo_a)
        controls.addWidget(QtWidgets.QLabel(self._b_label, self))
        controls.addWidget(self._combo_b)
        controls.addWidget(self._edit_name, 1)
        controls.addWidget(self._btn_add)
        layout.addLayout(controls)

        self._table = QtWidgets.QTableWidget(self)
        self._table.setColumnCount(len(self._headers) + 1)
        self._table.setHorizontalHeaderLabels([*self._headers, ""])
        self._table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        header = self._table.horizontalHeader()
        try:
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
            for col in range(1, len(self._headers)):
                header.setSectionResizeMode(col, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(len(self._headers), QtWidgets.QHeaderView.Fixed)
            header.resizeSection(len(self._headers), 30)
        except Exception:  # noqa: BLE001
            pass
        self._table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table, 1)

        self._btn_add.clicked.connect(self._on_add)
        self._table.itemChanged.connect(self._on_item_changed)

    # ── model events ─────────────────────────────────────────────────
    def _on_model_event(self, event: str) -> None:
        if event in ("setup_changed", "pairs_changed", "setups_reloaded"):
            self._rebuild()

    # ── rebuild from the model ───────────────────────────────────────
    def _channel_options(self, *extra: str) -> list[str]:
        names = list(getattr(self._model, "channel_names", []) or [])
        for value in extra:
            if value and value not in names:
                names.append(value)
        return names

    def _repopulate_add_row(self) -> None:
        names = self._channel_options()
        for combo in (self._combo_a, self._combo_b):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(names)
            combo.blockSignals(False)

    def _rebuild(self) -> None:
        self._loading = True
        try:
            self._repopulate_add_row()
            pairs = list(getattr(self._model, "pairs", []) or [])
            self._table.setRowCount(0)
            for pair in pairs:
                self._append_row(pair)
        finally:
            self._loading = False

    def _append_row(self, pair: typing.Mapping[str, typing.Any]) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        cha = str(pair.get("channel_a", ""))
        chb = str(pair.get("channel_b", ""))
        options = self._channel_options(cha, chb)
        for col, key in enumerate(self._col_keys):
            if key in ("channel_a", "channel_b"):
                combo = QtWidgets.QComboBox(self._table)
                combo.addItems(options)
                idx = combo.findText(cha if key == "channel_a" else chb)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                combo.currentTextChanged.connect(
                    lambda text, r=row, k=key: self._on_channel_changed(r, k, text)
                )
                self._table.setCellWidget(row, col, combo)
            elif key == "make_fine":
                chk = QtWidgets.QCheckBox(self._table)
                chk.setTristate(False)
                fine = pair.get("make_fine")
                chk.setChecked(bool(fine)) if fine is not None else None
                chk.toggled.connect(
                    lambda checked, r=row: self._commit(r, "make_fine", bool(checked))
                )
                self._table.setCellWidget(row, col, chk)
            else:
                value = pair.get(key)
                text = "" if value is None else str(value)
                self._table.setItem(row, col, QtWidgets.QTableWidgetItem(text))
        del_btn = QtWidgets.QToolButton(self._table)
        del_btn.setText("✕")
        del_btn.setToolTip(self._remove_tip)
        del_btn.clicked.connect(lambda _checked=False, r=row: self._on_delete(r))
        self._table.setCellWidget(row, len(self._col_keys), del_btn)

    # ── edit write-back ──────────────────────────────────────────────
    def _commit(self, row: int, key: str, value: typing.Any) -> None:
        if self._loading:
            return
        if hasattr(self._model, "update_pair"):
            self._model.update_pair(row, key, value)

    def _on_channel_changed(self, row: int, key: str, text: str) -> None:
        self._commit(row, key, text.strip())

    def _on_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        if self._loading:
            return
        row, col = item.row(), item.column()
        if col >= len(self._col_keys):
            return
        key = self._col_keys[col]
        text = item.text().strip()
        if key in ("n_bins", "n_casc"):
            value: typing.Any = None
            if text:
                try:
                    value = int(text)
                except ValueError:
                    value = None
            self._commit(row, key, value)
        else:
            self._commit(row, key, text)

    def _on_add(self) -> None:
        self._model.add_pair(
            self._combo_a.currentText(),
            self._combo_b.currentText(),
            self._edit_name.text(),
        )
        self._edit_name.clear()

    def _on_delete(self, row: int) -> None:
        self._model.remove_pair(row)
