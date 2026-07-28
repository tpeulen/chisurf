from __future__ import annotations

from typing import Optional
from qtpy import QtCore, QtWidgets, QtGui

class TimelineDock(QtCore.QObject):
    """Timeline slider and transport controls for movie playback."""

    def __init__(
        self,
        parent: QtWidgets.QWidget,
        viewer: "MolView",
        cmd: "Cmd",
        *,
        margins: tuple[int, int, int, int],
        spacing: int,
    ) -> None:
        super().__init__(parent)
        self.viewer = viewer
        self.cmd = cmd

        container = QtWidgets.QWidget(parent)
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(spacing)
        container.setFixedHeight(40)

        # Transport controls
        self.btn_stop = QtWidgets.QToolButton(container)
        self.btn_stop.setText("■")
        self.btn_stop.setToolTip("Stop (Jump to first frame)")
        self.btn_stop.clicked.connect(lambda: self.cmd.do("mstop"))

        self.btn_play = QtWidgets.QToolButton(container)
        self.btn_play.setText("▶")
        self.btn_play.setToolTip("Play")
        self.btn_play.clicked.connect(lambda: self.cmd.do("mplay"))

        self.btn_pause = QtWidgets.QToolButton(container)
        self.btn_pause.setText("‖")
        self.btn_pause.setToolTip("Pause")
        self.btn_pause.clicked.connect(lambda: self.cmd.do("mpause"))

        # Slider
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, container)
        self.slider.setMinimum(1)
        self.slider.setMaximum(1)
        self.slider.setValue(1)
        self.slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.slider.setTickInterval(10)
        self.slider.valueChanged.connect(self._on_slider_changed)

        # Labels
        self.lbl_frame = QtWidgets.QLabel("1 / 1", container)
        self.lbl_frame.setMinimumWidth(60)
        self.lbl_frame.setAlignment(QtCore.Qt.AlignCenter)

        # How many frames a step advances. A long trajectory is usually sampled
        # far more finely than anyone wants to watch, and stepping it one frame
        # at a time is both slow and indistinguishable from standing still.
        self.spin_step = QtWidgets.QSpinBox(container)
        self.spin_step.setRange(1, 1000)
        self.spin_step.setValue(1)
        self.spin_step.setPrefix("×")
        self.spin_step.setMaximumWidth(64)
        self.spin_step.setToolTip(
            "Frames advanced per step. Skips frames; it does not average them."
        )
        self.spin_step.valueChanged.connect(self._on_step_changed)

        # Running mean over neighbouring frames. Thermal motion jitters every
        # atom in every frame, so a trajectory can be restless to look at even
        # when nothing is happening; averaging a few frames takes that out and
        # leaves the slower motion alone.
        self.spin_smooth = QtWidgets.QSpinBox(container)
        self.spin_smooth.setRange(0, 999)
        self.spin_smooth.setValue(0)
        self.spin_smooth.setPrefix("~")
        self.spin_smooth.setSpecialValueText("~off")
        self.spin_smooth.setMaximumWidth(70)
        self.spin_smooth.setToolTip(
            "Smoothing window, in frames. Averages each frame with its "
            "neighbours for display only -- the frame number, measurements and "
            "exports are unchanged."
        )
        self.spin_smooth.valueChanged.connect(self._on_smoothing_changed)

        layout.addWidget(self.btn_stop)
        layout.addWidget(self.btn_play)
        layout.addWidget(self.btn_pause)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.lbl_frame)
        layout.addWidget(QtWidgets.QLabel("step", container))
        layout.addWidget(self.spin_step)
        layout.addWidget(QtWidgets.QLabel("smooth", container))
        layout.addWidget(self.spin_smooth)

        self._widget = container

        # Periodic update from viewer state
        self._update_timer = QtCore.QTimer(self)
        self._update_timer.timeout.connect(self.refresh_ui)
        self._update_timer.start(100) # 10Hz UI refresh
        container.destroyed.connect(self._on_container_destroyed)

    def _on_container_destroyed(self) -> None:
        try:
            self._update_timer.stop()
        except Exception:
            pass

    @property
    def widget(self) -> QtWidgets.QWidget:
        return self._widget

    def _on_slider_changed(self, value: int) -> None:
        if not self.viewer._animation_running:
             self.cmd.do(f"frame {value}")

    def _on_step_changed(self, value: int) -> None:
        """Set how many frames a step advances."""
        self.slider.setSingleStep(max(1, int(value)))
        self.slider.setPageStep(max(1, int(value)) * 10)
        setter = getattr(self.viewer, "set_frame_step", None)
        if callable(setter):
            setter(int(value))

    def _on_smoothing_changed(self, value: int) -> None:
        """Set the display-only smoothing window."""
        setter = getattr(self.viewer, "set_trajectory_smoothing", None)
        if callable(setter):
            setter(int(value))

    def refresh_ui(self) -> None:
        """Sync slider and label with viewer state."""
        try:
            curr = self.viewer.get_current_frame() + 1
            total = self.viewer.get_total_frames()

            if self.slider.maximum() != total:
                self.slider.setMaximum(total)
                self.slider.setTickInterval(max(1, total // 10))

            if not self.slider.isSliderDown():
                self.slider.blockSignals(True)
                self.slider.setValue(curr)
                self.slider.blockSignals(False)

            self.lbl_frame.setText(f"{curr} / {total}")
        except RuntimeError:
            # C++ widgets were destroyed (e.g. during plugin reload). Stop the
            # timer so we don't keep hitting deleted objects.
            try:
                self._update_timer.stop()
            except Exception:
                pass
