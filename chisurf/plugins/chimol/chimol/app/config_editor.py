from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from qtpy import QtWidgets, QtGui

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ..renderer.view import MolView


class MolViewConfigEditor(QtWidgets.QDialog):

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget],
        *,
        json_path: Path | None,
        viewer: "MolView" | None,
    ) -> None:
        super().__init__(parent)
        self._json_path = json_path
        self._viewer = viewer

        self.setWindowTitle("Chimol Display Configuration")
        self.resize(800, 600)

        layout = QtWidgets.QVBoxLayout(self)

        self._edit = QtWidgets.QPlainTextEdit(self)
        font = QtGui.QFont("Courier New")
        font.setPointSize(9)
        self._edit.setFont(font)
        layout.addWidget(self._edit, 1)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel,
            parent=self,
        )
        # A hand-edited config that predates a new setting is indistinguishable
        # from a deliberate choice, so there has to be a way back to the shipped
        # defaults without hunting for the file on disk.
        self._reset_button = btn_box.addButton(
            "\N{ANTICLOCKWISE OPEN CIRCLE ARROW} Reset to defaults",
            QtWidgets.QDialogButtonBox.ResetRole,
        )
        self._reset_button.setToolTip(
            "Replace the editor contents with the configuration shipped with "
            "this version of Chimol. Nothing is written until you press Save."
        )
        layout.addWidget(btn_box)

        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        self._reset_button.clicked.connect(self._on_reset)

        self._load_from_disk()

    def _on_reset(self) -> None:
        """Load the packaged defaults into the editor, leaving the file alone.

        Deliberately not written straight to disk: the user still has to press
        Save, so a mis-click cannot silently discard a config they tuned.
        """
        from ..config import get_package_display_config_path

        package_path = get_package_display_config_path()
        try:
            text = package_path.read_text(encoding="utf-8")
        except Exception as exc:  # pragma: no cover - UI feedback
            QtWidgets.QMessageBox.warning(
                self,
                "Failed to read the defaults",
                f"Could not read {package_path}:\n{exc}",
            )
            return

        self._edit.setReadOnly(False)
        self._edit.setPlainText(text)
        QtWidgets.QMessageBox.information(
            self,
            "Defaults loaded",
            "The shipped configuration is now in the editor.\n\n"
            "Press Save to write it to your settings file, or Cancel to keep "
            "what you had.",
        )

    def _load_from_disk(self) -> None:
        if self._json_path is None:
            self._edit.setPlainText("// Could not locate chimol_display.json")
            self._edit.setReadOnly(True)
            return
        try:
            with self._json_path.open("r", encoding="utf-8") as fh:
                text = fh.read()
        except Exception as e:  # pragma: no cover - UI feedback
            self._edit.setPlainText(f"// Failed to read {self._json_path}: {e}")
            self._edit.setReadOnly(True)
            return

        self._edit.setReadOnly(False)
        self._edit.setPlainText(text)

    def _on_save(self) -> None:
        if self._json_path is None:
            self.reject()
            return

        text = self._edit.toPlainText()
        try:
            # Validate JSON before writing.
            json.loads(text)
        except Exception as e:  # pragma: no cover - UI feedback
            QtWidgets.QMessageBox.warning(
                self,
                "Invalid JSON",
                f"The configuration is not valid JSON:\n{e}",
            )
            return

        try:
            with self._json_path.open("w", encoding="utf-8") as fh:
                fh.write(text)
        except Exception as e:  # pragma: no cover - UI feedback
            QtWidgets.QMessageBox.warning(
                self,
                "Failed to save configuration",
                f"Could not write to {self._json_path}:\n{e}",
            )
            return

        # Reload display configuration globally so future redraws see it.
        try:
            from chisurf.plugins.chimol.chimol import config as _chimol_config

            _chimol_config.reload_display_config()
        except Exception:  # pragma: no cover - optional refresh
            pass

        # Ask the current viewer, if any, to refresh its view.
        if self._viewer is not None:
            try:
                if getattr(self._viewer, "_coords", None) is not None:
                    self._viewer._update_view()  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - best effort refresh
                pass

        self.accept()
