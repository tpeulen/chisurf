"""The native Batch Analysis wizard against the Qt wizard: same steps, same selection, same numbers, same files.

The Qt side is the shared view model (steps, texts, completion) and, for the run, ``qt_reference.json``: what the
retired Qt ``run`` wrote and showed (CSV, DOCX, ZIP, progress labels, message boxes) on the same fakes
(``fakes.FakeSession``), recorded once from the live Qt code before it was deleted. Everything runs on temporary
settings; the real ``~/.chisurf`` is checked unchanged.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.core.project_browser.test.driving import (
    clipped_texts,
    draw_clip,
    layout_problems,
)
from chisurf.plugins.emtk_hermetic import (  # noqa: F401  (autouse fixtures)
    hermetic,
    real_chisurf_untouched,
)

from ..core import runner
from ..gui.app import BatchAnalysisApp
from ..gui.model import STEPS, BatchModel
from ..gui.view_model import BatchViewModel
from .fakes import FakeSession

PLUGIN = Path(__file__).parent.parent
BIG, SMALL = (1200, 800), (800, 600)


def draw(app, size=BIG, frames=3):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def make_files(tmp_path, names=("run_01.sm", "run_02.sm")):
    out = []
    for n in names:
        path = tmp_path / n
        path.write_text("x")
        out.append(str(path))
    return out


def strip_html(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def strip_md(md: str) -> str:
    return re.sub(
        r"\s+", " ", re.sub(r"[#*]", "", re.sub(r"^\d+\.\s+|^- ", "", md, flags=re.M))
    ).strip()


# -- the steps ----------------------------------------------------------------------------------------------------------- #


def qt_steps():
    spec = json.loads((PLUGIN / "batch.view.json").read_text())
    return spec["sections"][0]["steps"]


def test_the_steps_are_the_qt_wizards_steps_in_order_with_titles_subtitles_and_conditions():
    qt = qt_steps()
    assert [s.title for s in STEPS] == [s["title"] for s in qt]
    assert [s.subtitle for s in STEPS] == [s["subtitle"] for s in qt]
    assert [s.complete_when for s in STEPS] == [
        (s.get("complete_when") or {}).get("attr") for s in qt
    ]
    assert len(STEPS) == 5


def test_every_spec_reference_resolves_on_the_model():
    spec = json.loads((PLUGIN / "gui/batch_emtk.view.json").read_text())
    model = BatchModel(session=FakeSession())

    def walk(sections):
        for s in sections:
            opts = s.get("options") or {}
            for key in ("source", "edited_call", "selected_call", "delete_call"):
                if opts.get(key):
                    assert callable(getattr(model, opts[key])), opts[key]
            for key in ("options_source", "text_source"):
                if s.get(key):
                    assert callable(getattr(model, s[key])), s[key]
            if s.get("attr"):
                assert hasattr(model, s["attr"]), s["attr"]
            for b in list(s.get("buttons", [])) + list(opts.get("buttons", [])):
                assert callable(getattr(model, b["action"])), b["action"]
                assert model.enabled(b["action"]) in (True, False)
            walk(s.get("sections", []))

    walk(spec["sections"])


def test_the_completion_marks_follow_the_qt_conditions(monkeypatch):
    session = FakeSession()
    qt, native = BatchViewModel(), BatchModel(session=session)
    monkeypatch.setattr(BatchViewModel, "_fit_client", lambda self: session.client)

    def marks(m):
        return [m.step_complete(i) for i in range(5)] if hasattr(m, "step_complete") else None  # noqa: E731

    assert marks(native) == [
        True,
        True,
        True,
        False,
        True,
    ]  # a fit exists (Files & fit), no results yet (Run)
    assert qt.fit_selected and native.fit_selected
    native.selected_fit_name = qt.selected_fit_name = "nope"
    native.refresh_completion()
    assert not qt.fit_selected and not native.fit_selected and native.step_complete(2) is False
    assert qt.has_results is False and native.has_results is False


def test_the_welcome_text_is_the_qt_text():
    qt, native = BatchViewModel(), BatchModel(session=FakeSession())
    numbered = lambda s: re.sub(r"\s\d\.\s", " ", s)  # noqa: E731  (the list numbers are markup in both)
    assert numbered(strip_md(native.welcome_md())) == numbered(strip_html(qt.welcome_html()))


def test_the_selection_summary_equals_the_qt_summary(tmp_path):
    session = FakeSession()
    qt, native = BatchViewModel(), BatchModel(session=session)
    qt.imported_datasets = lambda: list(session.datasets)
    for model in (qt, native):
        model.files = make_files(tmp_path)
        model.selected_dataset_indices = [0, 2]
        model.selected_fit_name = "Template fit"
    native.reload_files()
    q, n = strip_html(qt.selection_html()), strip_md(native.selection_md())
    assert q == n


# -- loaded datasets: the Qt check list ---------------------------------------------------------------------------------- #


def test_the_dataset_rows_are_the_qt_lists_items_and_a_tick_selects_the_same_indices():
    """The retired Qt list showed "1. A" ...; ticking row 1 selected index [1] and unticking cleared it."""
    session = FakeSession(datasets=("A", "B", "C", "Global Dataset"))
    native = BatchModel(session=session)
    assert [r["label"] for r in native.dataset_rows()] == ["1. A", "2. B", "3. C"]
    native.set_dataset_use(native.dataset_rows()[1], "use", True)
    assert native.selected_dataset_indices == [1]
    assert [d.name for d in native.selected_datasets()] == ["B"]
    native.set_dataset_use(native.dataset_rows()[1], "use", False)
    assert native.selected_dataset_indices == []


def test_refresh_keeps_the_ticks_of_datasets_that_are_still_there():
    session = FakeSession(datasets=("A", "B", "C"))
    native = BatchModel(session=session)
    native.set_dataset_use(native.dataset_rows()[2], "use", True)
    session.datasets.pop()  # the third dataset was closed in ChiSurf
    native.refresh_datasets()
    assert native.selected_dataset_indices == [] and len(native.dataset_rows()) == 2


# -- files: the Qt path list --------------------------------------------------------------------------------------------- #


def test_adding_files_and_folders_gives_the_qt_path_lists_result(tmp_path):
    folder = tmp_path / "data"
    (folder / "sub").mkdir(parents=True)
    for name in ("b.sm", "a.sm", "sub/c.sm"):
        (folder / name).write_text("x")
    loose = tmp_path / "loose.sm"
    loose.write_text("x")
    native = BatchModel(session=FakeSession())
    # what the retired Qt path list held after each add (a folder expands sorted; repeats and misses add nothing)
    expected = [
        ["loose.sm"],
        ["loose.sm", "a.sm", "b.sm", "c.sm"],
        ["loose.sm", "a.sm", "b.sm", "c.sm"],
    ]
    for batch, names in zip(
        (
            [str(loose)],
            [str(folder)],
            [str(loose), str(tmp_path / "missing.sm")],  # the last repeats and misses
        ),
        expected,
        strict=True,
    ):
        native.add_paths(batch)
        assert [Path(p).name for p in native.files] == names


def test_remove_and_clear_match_the_qt_buttons(tmp_path):
    files = make_files(tmp_path, ("a.sm", "b.sm", "c.sm"))
    native = BatchModel(session=FakeSession())
    native.add_paths(files)
    native.select_file(native.file_rows()[1])
    native.remove_selected()
    assert native.files == [files[0], files[2]]  # the Qt remove button left the same two
    native.clear_files()
    assert native.files == []


# -- the run: the same numbers and files as the Qt run ------------------------------------------------------------------- #

#: The retired Qt run (``BatchViewModel.run``: progress dialog, save dialog, message boxes), recorded once from the live
#: Qt code on these fakes before it was deleted: files ``run_01.sm``/``run_02.sm``, datasets [0, 2], fit "Template fit".
#: ``<tmp>`` stands for the test's ``tmp_path``; the Qt run wrote into ``<tmp>/qt``.
QT = json.loads((Path(__file__).parent / "qt_reference.json").read_text(encoding="utf-8"))


def native_run(tmp_path, session, files, indices, save):
    """Run the native model on *session*'s fakes; returns it and the progress texts it showed."""
    native = BatchModel(session=session)
    native.files = list(files)
    native.selected_dataset_indices = list(indices)
    native.selected_fit_name = "Template fit"
    native.save_path = str(save)
    shown = []
    events = native._events  # noqa: SLF001

    class Recording:
        """The worker's queue, noting the progress bar's text for every progress event."""

        def put(self, event):
            if event[0] == "progress":
                _, done, total, name = event
                bar = type("Bar", (), {"progress": (done, total), "progress_name": name})()
                shown.append(BatchModel.progress_text(bar))  # the model's own text over the bar
            events.put(event)

        def get_nowait(self):
            return events.get_nowait()

    native._events = Recording()  # noqa: SLF001
    native.run()
    native.wait()
    return native, shown


def test_a_batch_writes_the_same_csv_zip_and_rows_as_the_qt_run(tmp_path):
    files = make_files(tmp_path)
    (tmp_path / "nat").mkdir()
    session = FakeSession()
    native, progress = native_run(
        tmp_path, session, files, [0, 2], tmp_path / "nat" / "results.csv"
    )
    tmp = lambda text: text.replace(str(tmp_path), "<tmp>")  # noqa: E731
    assert native.message == "Batch complete" and native.message_ok and not native.running
    assert [
        {k: tmp(v) if isinstance(v, str) else v for k, v in r.items()} for r in native.result_rows()
    ] == QT["rows"]
    assert tmp((tmp_path / "nat" / "results.csv").read_text()) == QT["csv"]
    assert (
        sorted(zipfile.ZipFile(tmp_path / "nat" / "results_fit_results.zip").namelist())
        == QT["zip_names"]
    )
    assert (tmp_path / "nat" / "results.docx").exists() == QT["docx_written"]
    assert [name for name, _ in session.log] == QT["dispatched"]
    assert [[p.name, p.value, p.fixed] for p in session.fits[0].model.parameters_all] == QT[
        "parameters_after"
    ]
    # the Qt progress dialog's label, step by step, is the text over the native progress bar
    assert progress == QT["progress_labels"]
    # the Qt "Batch complete" box listed the CSV, the DOCX when written and the ZIP; the window lists the same lines
    ((kind, title, text),) = QT["boxes"]
    assert (kind, title) == ("information", native.message)
    mine = [tmp(line).replace("/nat/", "/qt/") for line in native.outputs]
    assert mine == text.splitlines()
    rows = native.result_rows()
    assert [r["Filename"] for r in rows[::3]] == ["Sample A", "Sample C", files[0], files[1]]
    assert [r["Run"] for r in rows[::3]] == ["1", "2", "3", "4"]
    assert [r["Value"] for r in rows if r["Parameter"] == "tau"] == [
        1.0,
        1.5,
        2.0,
        2.5,
    ]  # restored to the template each run


def test_the_results_table_cells_equal_the_qt_results_html(tmp_path):
    files = make_files(tmp_path)
    native, _ = native_run(tmp_path, FakeSession(), files, [0, 2], tmp_path / "o2.csv")
    flat = [
        str(r[c]).replace(str(tmp_path), "<tmp>")
        for r in native.result_rows()
        for c in runner.FIELDNAMES
    ]
    assert flat == QT["results_html_cells"]


def test_no_data_no_fit_and_a_missing_csv_are_the_qt_warnings_as_lines_and_a_chooser():
    (no_data, no_fit) = QT["warnings"]
    native = BatchModel(session=FakeSession())
    native.run()
    assert native.message == ": ".join(no_data) and not native.message_ok
    native2 = BatchModel(session=FakeSession(fits=()))
    native2.files = ["/x/a.sm"]
    native2.run()
    assert native2.message == ": ".join(no_fit)
    native3 = BatchModel(session=FakeSession())
    native3.files = ["/x/a.sm"]
    native3.run()  # no CSV path: the Qt tool opened a "Save results" CSV dialog
    assert QT["save_dialog"][0][0] == "Save results"
    assert native3.dialog_request == "results" and not native3.running


def test_each_runs_picture_is_drawn_on_the_polling_thread_and_goes_into_the_docx(tmp_path):
    """The Qt run grabbed the fit sub-window between two fits; the worker hands each capture to the window's thread."""
    import threading

    from emtk.testing import png_encode

    threads, names = [], []

    def capture(out_dir, name, run_index):
        threads.append(threading.get_ident())
        names.append((name, run_index))
        path = Path(out_dir) / f"{run_index:03d}.png"
        path.write_bytes(png_encode(2, 2, bytes([200, 30, 30, 255] * 4)))
        return str(path)

    native = BatchModel(session=FakeSession(), capture=capture)
    native.files = make_files(tmp_path)
    native.selected_dataset_indices = [0, 2]
    native.selected_fit_name = "Template fit"
    native.save_path = str(tmp_path / "r.csv")
    native.run()
    native.wait()
    assert native.message == "Batch complete", native.message
    assert threads == [threading.get_ident()] * 4
    assert [Path(n).name for n, _ in names] == ["Sample A", "Sample C", "run_01.sm", "run_02.sm"]
    assert len(native._results.screenshot_map) == 4  # noqa: SLF001
    assert all(Path(p).is_file() for p in native._results.screenshot_map.values())  # noqa: SLF001


def test_the_default_picture_is_the_template_fit_window(monkeypatch, tmp_path):
    """Without an injected session the model draws the template fit's emtk window (the Qt run grabbed its sub-window)."""
    from ..gui import model as model_module

    session = FakeSession()
    native = BatchModel(session=session)
    assert native.capture is None  # an injected session takes no pictures unless asked
    native.capture = native.capture_fit_window
    drawn = []
    monkeypatch.setattr(
        model_module, "fit_window_png", lambda fit, path: drawn.append((fit, path)) or path
    )
    native._run_fit_index = 0  # noqa: SLF001
    out = native.capture_fit_window(str(tmp_path), "a/b.sm", 3)
    assert drawn == [(session.fits[0], out)] and Path(out).name == "003_b.png"
    # a fit that cannot be drawn gives no picture, never an error
    monkeypatch.undo()
    assert model_module.fit_window_png(object(), str(tmp_path / "x.png")) == ""


def test_a_failing_fit_is_reported_in_the_window_as_the_qt_error_box_reported_it(tmp_path):
    session = FakeSession()
    session.dispatch = lambda name, payload: (_ for _ in ()).throw(
        RuntimeError("fit server is gone")
    )
    native = BatchModel(session=session)
    native.files = make_files(tmp_path)
    native.selected_fit_name = "Template fit"
    native.save_path = str(tmp_path / "r.csv")
    native.run()
    native.wait()
    assert (
        native.message == "Batch failed: fit server is gone"
        and not native.message_ok
        and not native.running
    )
    assert not (tmp_path / "r.csv").exists() and native.result_rows() == []


# -- settings, drawing, tooltips, layout --------------------------------------------------------------------------------- #


def test_the_remembered_state_round_trips_and_ignores_bad_values():
    app = BatchAnalysisApp(BatchModel(session=FakeSession()))
    app.model.go_to(3)
    app.model.selected_fit_name = "Template fit"
    app.model.save_path = "/tmp/r.csv"
    app.model.files = ["/stale.sm"]
    state = json.loads(json.dumps(app.export_settings()))
    other = BatchAnalysisApp(BatchModel(session=FakeSession()))
    other.restore_settings(state)
    assert (
        other.model.step,
        other.model.selected_fit_name,
        other.model.save_path,
        other.model.files,
    ) == (3, "Template fit", "/tmp/r.csv", [])
    other.restore_settings({"step": "x", "selected_fit_name": None, "save_path": None, "docks": 7})
    assert (
        other.model.step == 0
        and other.model.selected_fit_name == "Template fit"
        and other.model.save_path == ""
    )


@pytest.mark.parametrize("size", [BIG, SMALL])
def test_every_step_draws_populated_and_empty_without_markup_or_layout_problems(size, tmp_path):
    for populated in (False, True):
        model = BatchModel(
            session=FakeSession() if populated else FakeSession(datasets=(), fits=())
        )
        if populated:
            model.add_paths(make_files(tmp_path))
            model.set_dataset_use(model.dataset_rows()[0], "use", True)
            model.save_path = str(
                tmp_path / "very" / "long" / "folder" / "name" / "for" / "the" / "results.csv"
            )
        app = BatchAnalysisApp(model)
        for i in range(len(STEPS)):
            model.go_to(i)
            painter = draw_clip(app, size)
            shown = " ".join(painter.strings)
            assert "<" not in shown and "**" not in shown, (i, populated)
            assert layout_problems(painter, size) == [], (
                i,
                populated,
                layout_problems(painter, size),
            )
            assert clipped_texts(painter) == [], (i, populated, clipped_texts(painter))
        if populated:
            model.run()
            model.wait()
            painter = draw_clip(app, size)
            assert layout_problems(painter, size) == []
            model.go_to(4)
            painter = draw_clip(app, size)
            assert layout_problems(painter, size) == [] and clipped_texts(painter) == []
            assert "Sample A" in painter.strings


def test_every_control_has_a_tooltip_and_the_spec_describes_every_section():
    from test.gui.emtk_port_parity import emtk_inventory

    model = BatchModel(session=FakeSession())
    model.add_paths(["/x"])
    app = BatchAnalysisApp(model)
    for i in range(len(STEPS)):
        model.go_to(i)
        inv = emtk_inventory(app, BIG)
        assert inv["controls_without_tooltip"] == [], (i, inv["controls_without_tooltip"])

    spec = json.loads((PLUGIN / "gui/batch_emtk.view.json").read_text())

    def walk(sections):
        for s in sections:
            assert s.get("description"), s
            for column in (s.get("options") or {}).get("columns", []):
                assert column.get("tooltip"), column
            for b in list(s.get("buttons", [])) + list((s.get("options") or {}).get("buttons", [])):
                assert b.get("description"), b
            walk(s.get("sections", []))

    walk(spec["sections"])


def test_the_app_imports_no_qt():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("batch_analysis")
    assert result.get("qt_free", result.get("ok", True)) in (True, 1) or not result.get(
        "qt_modules"
    ), result
