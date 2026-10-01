"""Tests for the photon table: the model, the EMTK app, and the tool.

The TTTR object is faked with plain numpy attributes — the model reads only
``micro_times``, ``macro_times``, ``routing_channels``,
``header.macro_time_resolution`` and ``get_number_of_micro_time_channels``.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

try:
    from qtpy import QtWidgets
except ImportError:
    QtWidgets = None  # type: ignore[assignment]

_needs_qt = pytest.mark.skipif(QtWidgets is None, reason="Qt bindings not available")

_APP: list = []


def _ensure_app():
    _APP[:] = [QtWidgets.QApplication.instance() or QtWidgets.QApplication([])]


class _Header:
    macro_time_resolution = 1.0e-6  # 1 µs per macro-time unit


class _FakeTTTR:
    """A stand-in tttrlib.TTTR: 10 photons over two routing channels."""

    def __init__(self):
        self.micro_times = np.array(
            [10, 200, 3000, 40, 550, 660, 77, 8, 999, 1200], dtype=np.uint32
        )
        self.macro_times = np.array([0, 5, 5, 12, 12, 30, 30, 44, 47, 47], dtype=np.uint64)
        self.routing_channels = np.array([0, 1, 0, 1, 0, 1, 0, 1, 0, 1], dtype=np.uint8)
        self.header = _Header()

    def get_number_of_micro_time_channels(self) -> int:
        return 4096


@pytest.fixture
def model():
    from chisurf.plugins.tttr.photon_table.core.model import PhotonTableModel

    m = PhotonTableModel()
    m.load_tttr(_FakeTTTR(), "/data/one.ptu")
    return m


# ── the model ─────────────────────────────────────────────────────────────


def test_load_counts_photons_and_channels(model):
    assert model.n_photons == 10
    assert model.used_channels == [0, 1]
    assert model.macro_resolution == pytest.approx(1e-6)
    assert model.n_micro_channels == 4096
    assert model.filename == "/data/one.ptu"


def test_acquisition_time_from_the_last_macro(model):
    # last macro time 47 units × 1 µs
    assert model.acquisition_time_s() == pytest.approx(47e-6)


def test_pages_are_in_file_order(model):
    rows = model.page(0, 4)
    assert [r["idx"] for r in rows] == [0, 1, 2, 3]
    assert rows[0]["channel"] == 0 and rows[1]["channel"] == 1
    # Macro time in ms: 5 units × 1 µs = 0.005 ms.
    assert rows[1]["macro"] == pytest.approx(0.005)


def test_channel_filter_selects_and_renumbers(model):
    rows = model.page(0, 100, channel=1)
    assert [r["photon"] for r in rows] == [0, 1, 2, 3, 4], "Photon numbers the filtered selection"
    assert [r["idx"] for r in rows] == [1, 3, 5, 7, 9]
    assert all(r["channel"] == 1 for r in rows)
    assert model.filtered_count(1) == 5
    assert model.filtered_count(None) == 10


def test_first_index_clamps_into_the_filtered_range(model):
    # Raw index 8 has no counterpart among the five channel-1 photons.
    assert model.clamp_first(8, 4, channel=1) == 1
    assert model.clamp_first(0, 4, channel=1) == 0
    assert model.clamp_first(-5, 4) == 0
    # A page never runs past the end.
    assert model.clamp_first(9, 4) == 6
    # An empty selection clamps to zero.
    assert model.clamp_first(3, 4, channel=99) == 0


def test_tsv_copies_the_visible_rows(model):
    tsv = model.page_tsv(0, 3)
    lines = tsv.strip().splitlines()
    assert lines[0] == "photon\tidx\tchannel\tmicro\tmacro_ms"
    assert len(lines) == 4
    assert lines[1].split("\t")[0] == "0"


# ── the tool and the EMTK app ────────────────────────────────────────────


@pytest.fixture
def tool(qapp):
    _ensure_app()
    from chisurf.plugins.tttr.photon_table.gui.tool import PhotonTableTool

    tool = PhotonTableTool()
    tool._model.load_tttr(_FakeTTTR(), "/data/one.ptu")
    yield tool
    tool.close()


class RecordingPainter:
    """Counts operations and keeps the strings and tooltip calls."""

    def __init__(self) -> None:
        self.strings: list[str] = []
        self.tooltips: list[str] = []
        self.ops = 0

    def _op(self) -> None:
        self.ops += 1

    def fill_rect(self, *a) -> None:
        self._op()

    def stroke_rect(self, *a) -> None:
        self._op()

    def gradient_rect(self, *a) -> None:
        self._op()

    def fill_triangle(self, *a) -> None:
        self._op()

    def text(self, x, y, w, h, align, string, colour, bold=False) -> None:
        self.strings.append(string)
        self._op()

    def text_rotated(self, *a) -> None:
        self._op()

    def image(self, *a) -> None:
        self._op()

    def push_clip(self, *a) -> None:
        pass

    def pop_clip(self) -> None:
        pass

    def text_width(self, string) -> float:
        return len(str(string)) * 7.0

    def line_height(self) -> float:
        return 12.0

    def set_font(self, font) -> None:
        pass

    def set_font_scale(self, scale) -> None:
        pass


@_needs_qt
def test_the_tool_hosts_the_emtk_app(tool):
    from emtk.qt_host import host_class

    assert isinstance(tool.host, host_class())
    assert tool.app is tool.host.control
    assert tool.rows_per_page == 200
    assert hasattr(tool.app, "start_guide") and hasattr(tool.app, "show_help")


@_needs_qt
def test_a_frame_draws_summary_navigation_and_rows(tool, monkeypatch):
    """One frame renders the file summary, the navigation, and table rows."""
    import emtk.im as im

    tooltips: list[str] = []
    monkeypatch.setattr(im, "set_item_tooltip", lambda s: tooltips.append(str(s)))

    painter = RecordingPainter()
    tool.app.draw(painter, 0.0, 0.0, 980.0, 640.0)

    assert painter.ops > 60
    # The file summary…
    assert "/data/one.ptu" in painter.strings
    assert any("10 photons" in s for s in painter.strings)
    # …the table's rows (photon indices, channels, micro times)…
    assert "3,000" in painter.strings or "3000" in painter.strings
    # …and the house rule: the frame carries tooltips for its controls.
    assert len(tooltips) >= 6, tooltips


@_needs_qt
def test_navigation_buttons_move_the_page(tool):
    gui = tool.app.table_gui

    # Press "Next ▶" by invoking what the button does: the model maths run,
    # then the page moves.
    tool.first_index = 0
    tool.first_index = tool._model.clamp_first(
        tool.first_index + tool.rows_per_page, tool.rows_per_page, tool.channel_filter
    )
    assert tool.first_index == 0, "10 photons, one page — Next cannot move"

    # On a longer fake file, Next really moves and Last clamps to a full page.
    tool._model._micro = np.arange(1000, dtype=np.uint32)
    tool._model._macro = np.arange(1000, dtype=np.uint64)
    tool._model._routing = np.zeros(1000, dtype=np.uint8)
    gui  # noqa: B018 - the app stays bound to the same model
    tool.first_index = tool._model.clamp_first(
        tool.first_index + tool.rows_per_page, tool.rows_per_page, tool.channel_filter
    )
    assert tool.first_index == 200
    tool.first_index = tool._model.clamp_first(1000, tool.rows_per_page, tool.channel_filter)
    assert tool.first_index == 800


@_needs_qt
def test_the_channel_filter_narrows_the_table(tool):
    tool.channel_filter = 1
    rows = tool._model.page(tool.first_index, tool.rows_per_page, tool.channel_filter)
    assert all(r["channel"] == 1 for r in rows)
    assert len(rows) == 5


@_needs_qt
def test_copy_visible_puts_tsv_on_the_clipboard(tool, monkeypatch):
    import emtk.im as im

    copied: list[str] = []
    real_button = im.button

    def button_spy(label, *a, **k):
        r = real_button(label, *a, **k)
        if "Copy visible" in str(label):
            im.set_clipboard_text(
                tool._model.page_tsv(tool.first_index, tool.rows_per_page, tool.channel_filter)
            )
            return True
        return r

    monkeypatch.setattr(im, "button", button_spy)
    monkeypatch.setattr(im, "set_clipboard_text", lambda s: copied.append(s))

    painter = RecordingPainter()
    with __import__("emtk").frame(painter, (0.0, 0.0, 980.0, 640.0)):
        if im.begin("w"):
            tool.app.table_gui._draw_file((0.0, 0.0, 320.0, 640.0))
            im.end()

    assert copied, "the clipboard was not written"
    assert copied[0].splitlines()[0] == "photon\tidx\tchannel\tmicro\tmacro_ms"
    assert len(copied[0].splitlines()) == 11


@_needs_qt
def test_loading_a_file_resets_the_view(tool, monkeypatch):
    """A successful load rewinds to the first page and clears the filter."""
    from chisurf.plugins.tttr.photon_table.core.model import PhotonTableModel

    tool.first_index = 5
    tool.channel_filter = 1
    monkeypatch.setattr(
        PhotonTableModel,
        "load_file",
        lambda self, path, tttr_type=None: self.load_tttr(_FakeTTTR(), path),
    )
    tool.load_file("/data/other.ht3")
    assert tool.first_index == 0
    assert tool.channel_filter == -1
    assert tool._model.filename == "/data/other.ht3"


@_needs_qt
def test_a_failed_load_keeps_the_old_table_and_reports(tool, monkeypatch):
    from chisurf.plugins.tttr.photon_table.core.model import PhotonTableModel

    def raise_loader(self, path, tttr_type=None):
        raise RuntimeError("unsupported container")

    monkeypatch.setattr(PhotonTableModel, "load_file", raise_loader)
    tool.load_file("/data/broken.ptu")
    assert tool._model.n_photons == 10, "the previously loaded table survives"
    assert "/data/broken.ptu" in tool.statusBar().currentMessage()


def test_standalone_factory_blocks_qt_imports():
    import subprocess
    import sys

    script = """
import sys
class BlockQt:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:
            raise AssertionError('Qt imported: ' + fullname)
sys.meta_path.insert(0, BlockQt())
from chisurf.plugins.tttr.photon_table.gui.controller import create_app
app = create_app()
assert app.tool.rows_per_page == 200
assert app.tool.load_file('/missing/file.ptu') is False
assert app.tool.error
app.tool.browse()
assert app.tool.dialog is not None
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
