"""eLabFTW synchronization panel for MMFDB Admin."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from qtpy import QtCore, QtWidgets

Submit = Callable[
    [Callable[[], Any], Callable[[Any], None], Callable[[str], None]], None
]


class _Worker(QtCore.QObject):
    finished = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, fn: Callable[[], Any]):
        super().__init__()
        self._fn = fn

    @QtCore.Slot()
    def run(self) -> None:
        try:
            self.finished.emit(self._fn())
        except Exception as exc:
            self.failed.emit(str(exc))


class ELabFTWView(QtWidgets.QWidget):
    """Connect, browse, import, and export eLabFTW experiments.

    API keys are masked and cleared as soon as a connection attempt starts. The
    backend returns an opaque owner-bound handle; this widget never persists the
    key or includes it in status text.
    """

    def __init__(
        self,
        client: Any,
        parent: QtWidgets.QWidget | None = None,
        *,
        submit: Submit | None = None,
    ) -> None:
        """Build the panel around an auth-injecting MMFDB Admin client."""
        super().__init__(parent)
        self.client = client
        self.connection_id: str | None = None
        self._busy = False
        self._jobs: list[tuple[QtCore.QThread, _Worker]] = []
        self._submit = submit or self._submit_in_thread
        self._build_ui()
        self._update_controls()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        connection = QtWidgets.QGroupBox("eLabFTW connection")
        form = QtWidgets.QGridLayout(connection)
        self.endpoint_edit = QtWidgets.QLineEdit()
        self.endpoint_edit.setPlaceholderText("https://elab.example.org")
        self.api_key_edit = QtWidgets.QLineEdit()
        self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.api_key_edit.setClearButtonEnabled(True)
        self.api_key_edit.setPlaceholderText("API key (kept in memory only)")
        self.timeout_spin = QtWidgets.QDoubleSpinBox()
        self.timeout_spin.setRange(0.1, 120.0)
        self.timeout_spin.setValue(15.0)
        self.timeout_spin.setSuffix(" s")
        self.verify_tls_check = QtWidgets.QCheckBox("Verify TLS certificates")
        self.verify_tls_check.setChecked(True)
        self.allow_http_check = QtWidgets.QCheckBox("Allow plain HTTP (unsafe)")
        self.allow_http_check.setChecked(False)
        self.allow_http_check.setToolTip(
            "Only enable for an isolated trusted network. API keys are plaintext over HTTP."
        )
        form.addWidget(QtWidgets.QLabel("Endpoint"), 0, 0)
        form.addWidget(self.endpoint_edit, 0, 1, 1, 3)
        form.addWidget(QtWidgets.QLabel("API key"), 1, 0)
        form.addWidget(self.api_key_edit, 1, 1, 1, 3)
        form.addWidget(QtWidgets.QLabel("Timeout"), 2, 0)
        form.addWidget(self.timeout_spin, 2, 1)
        form.addWidget(self.verify_tls_check, 2, 2)
        form.addWidget(self.allow_http_check, 2, 3)
        self.connect_button = QtWidgets.QPushButton("Connect")
        self.disconnect_button = QtWidgets.QPushButton("Disconnect")
        self.connect_button.clicked.connect(self.connect_remote)
        self.disconnect_button.clicked.connect(self.disconnect_remote)
        form.addWidget(self.connect_button, 3, 2)
        form.addWidget(self.disconnect_button, 3, 3)
        layout.addWidget(connection)

        browse_bar = QtWidgets.QHBoxLayout()
        self.query_edit = QtWidgets.QLineEdit()
        self.query_edit.setPlaceholderText("Search remote experiments")
        self.query_edit.returnPressed.connect(self.refresh_remote)
        self.refresh_button = QtWidgets.QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_remote)
        browse_bar.addWidget(self.query_edit, stretch=1)
        browse_bar.addWidget(self.refresh_button)
        layout.addLayout(browse_bar)

        self.remote_table = QtWidgets.QTableWidget(0, 7)
        self.remote_table.setHorizontalHeaderLabels(
            ["✓", "Remote ID", "Title", "Date", "Status", "Modified", "Tags"]
        )
        self.remote_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.remote_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.remote_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.remote_table, stretch=1)

        import_box = QtWidgets.QGroupBox("Import into MMFDB")
        import_layout = QtWidgets.QHBoxLayout(import_box)
        self.conflict_combo = QtWidgets.QComboBox()
        self.conflict_combo.addItems(["skip", "update", "error"])
        self.sample_id_edit = QtWidgets.QLineEdit()
        self.sample_id_edit.setPlaceholderText("Optional MMFDB sample ID")
        self.import_button = QtWidgets.QPushButton("Import checked")
        self.import_button.clicked.connect(self.import_selected)
        import_layout.addWidget(QtWidgets.QLabel("Existing"))
        import_layout.addWidget(self.conflict_combo)
        import_layout.addWidget(self.sample_id_edit, stretch=1)
        import_layout.addWidget(self.import_button)
        layout.addWidget(import_box)

        export_box = QtWidgets.QGroupBox("Export from MMFDB")
        export_layout = QtWidgets.QHBoxLayout(export_box)
        self.local_experiment_combo = QtWidgets.QComboBox()
        self.export_mode_combo = QtWidgets.QComboBox()
        self.export_mode_combo.addItems(["create", "update"])
        self.export_mode_combo.currentTextChanged.connect(self._update_controls)
        self.remote_id_spin = QtWidgets.QSpinBox()
        self.remote_id_spin.setRange(1, 2_147_483_647)
        self.remote_id_spin.setToolTip("Required only when explicitly updating a remote entry")
        self.export_button = QtWidgets.QPushButton("Export")
        self.export_button.clicked.connect(self.export_selected)
        export_layout.addWidget(self.local_experiment_combo, stretch=1)
        export_layout.addWidget(self.export_mode_combo)
        export_layout.addWidget(QtWidgets.QLabel("Remote ID"))
        export_layout.addWidget(self.remote_id_spin)
        export_layout.addWidget(self.export_button)
        layout.addWidget(export_box)

        self.status_label = QtWidgets.QLabel("Not connected")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def connect_remote(self) -> None:
        """Submit a connection probe and immediately clear the key field."""
        if self._busy or self.connection_id:
            return
        endpoint = self.endpoint_edit.text().strip()
        api_key = self.api_key_edit.text()
        if not endpoint or not api_key:
            self.status_label.setText("Endpoint and API key are required.")
            return
        self.api_key_edit.clear()
        self._run(
            lambda: self.client.connect_elabftw(
                endpoint,
                api_key,
                timeout=self.timeout_spin.value(),
                verify_tls=self.verify_tls_check.isChecked(),
                allow_insecure_http=self.allow_http_check.isChecked(),
            ),
            self._connected,
            redactions=(api_key,),
        )

    def _connected(self, result: dict[str, Any]) -> None:
        self.connection_id = str(result["connection_id"])
        info = result.get("info") or {}
        version = info.get("version") or info.get("elabftw_version") or "unknown"
        self.status_label.setText(
            f"Connected to {result.get('endpoint', '')} (eLabFTW {version})"
        )
        self._update_controls()
        self.refresh_remote()

    def disconnect_remote(self) -> None:
        """Disconnect the active owner-bound backend handle."""
        if self._busy or not self.connection_id:
            return
        connection_id = self.connection_id
        self._run(
            lambda: self.client.disconnect_elabftw(connection_id),
            lambda _result: self._disconnected(),
        )

    def _disconnected(self) -> None:
        self.connection_id = None
        self.api_key_edit.clear()
        self.remote_table.setRowCount(0)
        self.local_experiment_combo.clear()
        self.status_label.setText("Disconnected")
        self._update_controls()

    def refresh_remote(self) -> None:
        """Load a bounded page traversal without blocking the GUI thread."""
        if self._busy or not self.connection_id:
            return
        connection_id = self.connection_id
        query = self.query_edit.text().strip()
        self._run(
            lambda: self.client.list_elabftw_experiments(
                connection_id, query=query, page_size=50, max_items=500
            ),
            self._remote_loaded,
        )

    def _remote_loaded(self, rows: list[dict[str, Any]]) -> None:
        self.remote_table.setSortingEnabled(False)
        self.remote_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            checked = QtWidgets.QTableWidgetItem("")
            checked.setFlags(
                QtCore.Qt.ItemIsEnabled
                | QtCore.Qt.ItemIsSelectable
                | QtCore.Qt.ItemIsUserCheckable
            )
            checked.setCheckState(QtCore.Qt.Unchecked)
            values = [
                row.get("id"),
                row.get("title"),
                row.get("date"),
                row.get("status"),
                row.get("modified_at"),
                ", ".join(str(tag) for tag in row.get("tags") or []),
            ]
            self.remote_table.setItem(row_index, 0, checked)
            for column, value in enumerate(values, start=1):
                self.remote_table.setItem(
                    row_index,
                    column,
                    QtWidgets.QTableWidgetItem("" if value is None else str(value)),
                )
        self.remote_table.setSortingEnabled(True)
        self.status_label.setText(f"Loaded {len(rows)} remote experiments.")
        self.refresh_local_experiments()

    def refresh_local_experiments(self) -> None:
        """Refresh the selectable local export targets."""
        if self._busy or not self.connection_id:
            return
        self._run(self.client.list_experiments, self._local_loaded)

    def _local_loaded(self, rows: list[dict[str, Any]]) -> None:
        selected = self.local_experiment_combo.currentData()
        self.local_experiment_combo.clear()
        for row in rows:
            experiment_id = str(row.get("experiment_id") or "")
            if experiment_id:
                status = str(row.get("status") or "")
                label = f"{experiment_id} — {status}" if status else experiment_id
                self.local_experiment_combo.addItem(label, experiment_id)
        if selected:
            index = self.local_experiment_combo.findData(selected)
            if index >= 0:
                self.local_experiment_combo.setCurrentIndex(index)
        self._update_controls()

    def import_selected(self) -> None:
        """Import checked remote rows using the selected conflict policy."""
        if self._busy or not self.connection_id:
            return
        remote_ids = []
        for row in range(self.remote_table.rowCount()):
            checked = self.remote_table.item(row, 0)
            remote = self.remote_table.item(row, 1)
            if (
                checked is not None
                and checked.checkState() == QtCore.Qt.Checked
                and remote is not None
            ):
                remote_ids.append(int(remote.text()))
        if not remote_ids:
            self.status_label.setText("Check at least one remote experiment to import.")
            return
        connection_id = self.connection_id
        sample_id = self.sample_id_edit.text().strip() or None
        conflict = self.conflict_combo.currentText()
        self._run(
            lambda: self.client.import_elabftw_experiments(
                connection_id,
                remote_ids,
                conflict=conflict,
                sample_id=sample_id,
            ),
            self._imported,
        )

    def _imported(self, result: dict[str, Any]) -> None:
        self.status_label.setText(
            "Import complete: "
            f"{len(result.get('imported', []))} created, "
            f"{len(result.get('updated', []))} updated, "
            f"{len(result.get('skipped', []))} skipped."
        )
        self.refresh_local_experiments()

    def export_selected(self) -> None:
        """Export the selected local experiment in explicit create/update mode."""
        if self._busy or not self.connection_id:
            return
        experiment_id = self.local_experiment_combo.currentData()
        if not experiment_id:
            # ``setCurrentText`` is useful for editable/fake combos in tests.
            experiment_id = self.local_experiment_combo.currentText().split(" — ", 1)[0]
        if not experiment_id:
            self.status_label.setText("Select an MMFDB experiment to export.")
            return
        mode = self.export_mode_combo.currentText()
        remote_id = self.remote_id_spin.value() if mode == "update" else None
        connection_id = self.connection_id
        self._run(
            lambda: self.client.export_elabftw_experiment(
                connection_id,
                str(experiment_id),
                mode=mode,
                remote_id=remote_id,
            ),
            lambda result: self.status_label.setText(
                f"Export {result.get('mode', mode)} complete: "
                f"remote experiment {result.get('remote_id')}."
            ),
        )

    def _run(
        self,
        fn: Callable[[], Any],
        success: Callable[[Any], None],
        *,
        redactions: tuple[str, ...] = (),
    ) -> None:
        self._set_busy(True)

        def succeeded(result: Any) -> None:
            self._set_busy(False)
            success(result)

        def failed(message: str) -> None:
            self._set_busy(False)
            safe = str(message)
            for secret in redactions:
                if secret:
                    safe = safe.replace(secret, "***REDACTED***")
            self.status_label.setText(f"eLabFTW error: {safe}")

        self._submit(fn, succeeded, failed)

    def _submit_in_thread(
        self,
        fn: Callable[[], Any],
        success: Callable[[Any], None],
        failure: Callable[[str], None],
    ) -> None:
        thread = QtCore.QThread(self)
        worker = _Worker(fn)
        worker.moveToThread(thread)
        job = (thread, worker)
        self._jobs.append(job)

        def cleanup() -> None:
            if job in self._jobs:
                self._jobs.remove(job)
            worker.deleteLater()
            thread.deleteLater()

        worker.finished.connect(success)
        worker.failed.connect(failure)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(cleanup)
        thread.started.connect(worker.run)
        thread.start()

    def _set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        self._update_controls()

    def _update_controls(self, *_args: Any) -> None:
        connected = self.connection_id is not None
        enabled = not self._busy
        self.connect_button.setEnabled(enabled and not connected)
        self.disconnect_button.setEnabled(enabled and connected)
        self.refresh_button.setEnabled(enabled and connected)
        self.import_button.setEnabled(enabled and connected)
        has_local = self.local_experiment_combo.count() > 0
        self.export_button.setEnabled(enabled and connected and has_local)
        self.remote_id_spin.setEnabled(
            enabled and connected and self.export_mode_combo.currentText() == "update"
        )


__all__ = ["ELabFTWView"]
