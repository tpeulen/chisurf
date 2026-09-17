"""Choose, generate or clear one plugin's icon.

The icon controls used to sit permanently in the manager, taking the bottom
third of the panel -- an AI provider, an endpoint and a model name always on
screen, in a window whose job is to tell you what is installed. They are a
per-plugin action, so they live in a dialog you open for the plugin you mean.

Generation runs through :func:`chisurf.gui.task.run_in_background`, so the
window stays alive while a provider takes its time; the old version blocked the
GUI thread for the whole request, retries and ``Retry-After`` sleeps included.
"""

from __future__ import annotations

import pathlib
import shutil

from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui import dialogs
from chisurf.gui.glyphs import Glyphs
from chisurf.plugins.core.plugin_manager.api import icons as icon_api

#: Rendered size of the icon written to disk.
ICON_SIZE = 256
#: Size of the preview swatch.
PREVIEW_SIZE = 96


class IconDialog(QtWidgets.QDialog):
    """Icon editor for a single plugin."""

    def __init__(self, row, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.row = row
        self.setWindowTitle(f"Icon — {row.name}")
        self.setMinimumWidth(560)
        self._task = None

        layout = QtWidgets.QVBoxLayout(self)

        top = QtWidgets.QHBoxLayout()
        self.preview = QtWidgets.QLabel()
        self.preview.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self.preview.setAlignment(QtCore.Qt.AlignCenter)
        self.preview.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.preview.setToolTip("The icon as it appears beside the plugin.")
        top.addWidget(self.preview)

        right = QtWidgets.QVBoxLayout()
        self.path_edit = QtWidgets.QLineEdit()
        self.path_edit.setPlaceholderText("Pick an image file, or generate one")
        self.path_edit.setToolTip(
            "Path to an image to use as this plugin's icon. PNG is copied as-is; "
            "other formats are rendered onto a square canvas."
        )
        right.addWidget(self.path_edit)

        buttons = QtWidgets.QHBoxLayout()
        for label, tooltip, slot in (
            (f"{Glyphs.FOLDER} Choose…", "Pick an image file from disk.", self._choose),
            (f"{Glyphs.SUCCESS} Use", "Write the chosen image as this plugin's icon.", self._use),
            (
                f"{Glyphs.SPARKLE} Generate…",
                "Ask the configured AI provider for an icon.",
                self._generate,
            ),
            (f"{Glyphs.EDIT} Edit", "Open the icon in the system image editor.", self._edit),
            (
                f"{Glyphs.DELETE} Clear",
                "Remove the icon and fall back to a generated label.",
                self._clear,
            ),
        ):
            button = QtWidgets.QToolButton()
            button.setText(label)
            button.setToolTip(tooltip)
            button.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch()
        right.addLayout(buttons)
        top.addLayout(right, 1)
        layout.addLayout(top)

        provider_box = QtWidgets.QGroupBox("AI generation")
        provider_box.setToolTip(
            "Where a generated icon comes from. The API key is taken from AI Settings."
        )
        form = QtWidgets.QFormLayout(provider_box)
        self.provider_combo = QtWidgets.QComboBox()
        self.provider_combo.setToolTip("Which image provider to ask.")
        from chisurf.core.settings import ai_settings

        for display, (key, *_rest) in ai_settings.PROVIDERS.items():
            self.provider_combo.addItem(display, key)
        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        self.endpoint_edit = QtWidgets.QLineEdit()
        self.endpoint_edit.setToolTip("Base URL of the provider's API.")
        self.model_edit = QtWidgets.QLineEdit()
        self.model_edit.setToolTip("Image model to request.")
        form.addRow("Provider", self.provider_combo)
        form.addRow("Endpoint", self.endpoint_edit)
        form.addRow("Image model", self.model_edit)
        layout.addWidget(provider_box)

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

        self._provider_changed()
        self._refresh_preview()
        self._changed = False

    # -- helpers ---------------------------------------------------------

    @property
    def package_dir(self) -> pathlib.Path:
        """The selected plugin's directory."""
        return pathlib.Path(self.row.package_dir)

    @property
    def icon_path(self) -> pathlib.Path:
        """Where this plugin's icon file lives."""
        return self.package_dir / "icon.png"

    def _config(self) -> icon_api.IconConfig:
        """The generation settings as currently shown."""
        return icon_api.IconConfig(
            provider=str(self.provider_combo.currentData() or ""),
            endpoint=self.endpoint_edit.text().strip(),
            model=self.model_edit.text().strip(),
        )

    def _provider_changed(self) -> None:
        endpoint, model = icon_api.default_icon_generation_values(
            str(self.provider_combo.currentData() or "")
        )
        self.endpoint_edit.setText(endpoint)
        self.model_edit.setText(model)

    def _refresh_preview(self) -> None:
        """Show the icon as it currently stands."""
        if self.icon_path.is_file():
            pixmap = QtGui.QPixmap(str(self.icon_path))
            if not pixmap.isNull():
                self.preview.setPixmap(
                    pixmap.scaled(
                        PREVIEW_SIZE,
                        PREVIEW_SIZE,
                        QtCore.Qt.KeepAspectRatio,
                        QtCore.Qt.SmoothTransformation,
                    )
                )
                self.path_edit.setText(str(self.icon_path))
                return
        self.preview.setPixmap(QtGui.QPixmap())
        self.preview.setText("no icon")

    def _write_pixmap(self, pixmap: QtGui.QPixmap) -> None:
        """Save *pixmap* as the plugin's icon and record it in the manifest."""
        canvas = QtGui.QPixmap(ICON_SIZE, ICON_SIZE)
        canvas.fill(QtCore.Qt.transparent)
        scaled = pixmap.scaled(
            ICON_SIZE, ICON_SIZE, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
        )
        painter = QtGui.QPainter(canvas)
        painter.drawPixmap(
            (ICON_SIZE - scaled.width()) // 2,
            (ICON_SIZE - scaled.height()) // 2,
            scaled,
        )
        painter.end()
        canvas.save(str(self.icon_path), "PNG")
        self._set_manifest_icon("icon.png")
        self._changed = True
        self._refresh_preview()

    def _set_manifest_icon(self, value: str | None) -> None:
        """Point the manifest's ``icon`` at *value*, or drop the key."""
        import json

        manifest_path = self.package_dir / "manifest.json"
        if not manifest_path.is_file():
            return
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if value is None:
            data.pop("icon", None)
        else:
            data["icon"] = value
        manifest_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    # -- actions ---------------------------------------------------------

    def _choose(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Choose an icon image",
            "",
            "Images (*.png *.svg *.jpg *.jpeg *.ico);;All files (*)",
        )
        if path:
            self.path_edit.setText(path)

    def _use(self) -> None:
        source = pathlib.Path(self.path_edit.text().strip())
        if not source.is_file():
            dialogs.warning(self, "No image", "Choose an image file first.")
            return
        if source.resolve() == self.icon_path.resolve():
            return
        if source.suffix.lower() == ".png":
            shutil.copyfile(source, self.icon_path)
            self._set_manifest_icon("icon.png")
            self._changed = True
            self._refresh_preview()
            return
        pixmap = QtGui.QPixmap(str(source))
        if pixmap.isNull():
            dialogs.error(self, "Unreadable image", f"Qt could not read {source.name}.")
            return
        self._write_pixmap(pixmap)

    def _generate(self) -> None:
        """Ask the provider for an icon, off the GUI thread."""
        from chisurf.gui.task import run_in_background

        config = self._config()
        if not config.base_url or not config.model:
            dialogs.warning(
                self,
                "Not configured",
                "Set an endpoint and an image model before generating.",
            )
            return

        info = {"name": self.row.name, "doc": self.row.description}
        self.status.setText("Generating…")

        def work(task):
            # The provider's Retry-After sleeps happen here, on the worker.
            return icon_api.request_icon_bytes(config, info)

        self._task = run_in_background(
            self,
            "Generating icon…",
            work,
            owner="plugin_manager_icon",
            on_result=self._generated,
            on_error=self._generate_failed,
        )

    def _generated(self, payload: bytes) -> None:
        pixmap = QtGui.QPixmap()
        if not payload or not pixmap.loadFromData(payload):
            self.status.setText("The provider returned something that is not an image.")
            return
        self._write_pixmap(pixmap)
        self.status.setText("Icon generated.")

    def _generate_failed(self, exc: BaseException) -> None:
        self.status.setText(f"Generation failed: {exc}")

    def _edit(self) -> None:
        if not self.icon_path.is_file():
            dialogs.information(self, "No icon", "This plugin has no icon file to edit.")
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.icon_path)))

    def _clear(self) -> None:
        if not self.icon_path.is_file():
            self._set_manifest_icon(None)
            return
        if not dialogs.confirm(self, "Clear icon", f"Delete {self.icon_path}?"):
            return
        self.icon_path.unlink()
        self._set_manifest_icon(None)
        self._changed = True
        self._refresh_preview()

    # -- result ----------------------------------------------------------

    def exec_(self) -> int:  # noqa: D102 - Qt signature
        super().exec_()
        return 1 if self._changed else 0

    exec = exec_
