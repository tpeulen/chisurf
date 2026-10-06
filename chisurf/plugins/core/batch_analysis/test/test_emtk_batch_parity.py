"""The native Batch Analysis wizard against the Qt wizard: same steps, same selection, same numbers, same files.

The Qt side is built offscreen from the same fakes (``fakes.FakeSession``): the Qt view model's ``run`` writes the CSV, DOCX
and ZIP, the Qt ``LoadedDatasetSelector`` and ``PathListWidget`` list what the user picked. Everything runs on temporary
settings; the real ``~/.chisurf`` is checked unchanged.
"""

from __future__ import annotations

import csv
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
from ..gui import view_model as qt_vm_module
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
    marks = lambda m: (
        [m.step_complete(i) for i in range(5)] if hasattr(m, "step_complete") else None
    )  # noqa: E731
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


def test_the_dataset_rows_are_the_qt_lists_items_and_a_tick_selects_the_same_indices(
    qapp, monkeypatch
):
    from ..gui.loaded_datasets import LoadedDatasetSelector

    session = FakeSession(datasets=("A", "B", "C", "Global Dataset"))
    qt = BatchViewModel()
    qt.imported_datasets = lambda: [d for d in session.datasets if d.name != "Global Dataset"]
    widget = LoadedDatasetSelector(qt)
    native = BatchModel(session=session)
    labels = [widget._list.item(i).text() for i in range(widget._list.count())]  # noqa: SLF001
    assert labels == [r["label"] for r in native.dataset_rows()] == ["1. A", "2. B", "3. C"]
    from qtpy import QtCore

    widget._list.item(1).setCheckState(QtCore.Qt.Checked)  # noqa: SLF001
    native.set_dataset_use(native.dataset_rows()[1], "use", True)
    assert qt.selected_dataset_indices == native.selected_dataset_indices == [1]
    assert (
        [d.name for d in qt.selected_datasets()]
        == [d.name for d in native.selected_datasets()]
        == ["B"]
    )
    widget._list.item(1).setCheckState(QtCore.Qt.Unchecked)  # noqa: SLF001
    native.set_dataset_use(native.dataset_rows()[1], "use", False)
    assert qt.selected_dataset_indices == native.selected_dataset_indices == []


def test_refresh_keeps_the_ticks_of_datasets_that_are_still_there():
    session = FakeSession(datasets=("A", "B", "C"))
    native = BatchModel(session=session)
    native.set_dataset_use(native.dataset_rows()[2], "use", True)
    session.datasets.pop()  # the third dataset was closed in ChiSurf
    native.refresh_datasets()
    assert native.selected_dataset_indices == [] and len(native.dataset_rows()) == 2


# -- files: the Qt path list --------------------------------------------------------------------------------------------- #


def test_adding_files_and_folders_gives_the_qt_path_lists_result(qapp, tmp_path):
    from chisurf.gui.autoform.sections.path_list_section import PathListWidget

    from ..gui.view_model import BatchViewModel as Vm

    folder = tmp_path / "data"
    (folder / "sub").mkdir(parents=True)
    for name in ("b.sm", "a.sm", "sub/c.sm"):
        (folder / name).write_text("x")
    loose = tmp_path / "loose.sm"
    loose.write_text("x")
    qt = Vm()
    widget = PathListWidget(qt, "files", add_folders=True, mmfdb=False)
    native = BatchModel(session=FakeSession())
    for batch in (
        [str(loose)],
        [str(folder)],
        [str(loose), str(tmp_path / "missing.sm")],
    ):  # the last repeats and misses
        widget.add_paths(batch)
        native.add_paths(batch)
        assert qt.files == native.files
    assert [Path(p).name for p in native.files] == ["loose.sm", "a.sm", "b.sm", "c.sm"]


def test_remove_and_clear_match_the_qt_buttons(qapp, tmp_path):
    from chisurf.gui.autoform.sections.path_list_section import PathListWidget

    files = make_files(tmp_path, ("a.sm", "b.sm", "c.sm"))
    qt = BatchViewModel()
    widget = PathListWidget(qt, "files", mmfdb=False)
    native = BatchModel(session=FakeSession())
    widget.add_paths(files)
    native.add_paths(files)
    widget.select_index(1)
    native.select_file(native.file_rows()[1])
    widget._remove_selected()  # noqa: SLF001
    native.remove_selected()
    assert qt.files == native.files == [files[0], files[2]]
    widget.clear()
    native.clear_files()
    assert qt.files == native.files == []


# -- the run: the same numbers and files as the Qt run ------------------------------------------------------------------- #


def qt_run(monkeypatch, tmp_path, session, files, indices, save):
    """Drive the Qt view model's own ``run`` (dialogs recorded, no real progress dialog) on *session*'s fakes."""
    import chisurf as cs
    import chisurf.core.actions
    from chisurf.gui import dialogs
    from chisurf.gui.widgets.fitting import fitting_client

    shown = []
    monkeypatch.setattr(
        dialogs,
        "information",
        lambda parent, title, text: shown.append(("information", title, text)),
    )
    monkeypatch.setattr(
        dialogs, "warning", lambda parent, title, text: shown.append(("warning", title, text))
    )
    monkeypatch.setattr(
        dialogs, "error", lambda parent, title, text: shown.append(("error", title, text))
    )
    monkeypatch.setattr(fitting_client, "get_fitting_client", lambda: session.client)
    monkeypatch.setattr(
        chisurf.core.actions, "dispatch", lambda name, payload: session.dispatch(name, payload)
    )
    monkeypatch.setattr(cs, "imported_datasets", session.datasets, raising=False)
    qt = BatchViewModel()
    qt.files = list(files)
    qt.selected_dataset_indices = list(indices)
    qt.selected_fit_name = "Template fit"
    qt.save_path = str(save)
    qt.run()
    assert qt._results is not None, shown  # noqa: SLF001
    return qt, shown


def test_a_batch_writes_the_same_csv_zip_and_rows_as_the_qt_run(qapp, monkeypatch, tmp_path):
    files = make_files(tmp_path)
    (tmp_path / "qt").mkdir()
    (tmp_path / "nat").mkdir()
    qt_session, nat_session = FakeSession(), FakeSession()
    qt, shown = qt_run(
        monkeypatch, tmp_path, qt_session, files, [0, 2], tmp_path / "qt" / "results.csv"
    )
    native = BatchModel(session=nat_session)
    native.files = list(files)
    native.selected_dataset_indices = [0, 2]
    native.selected_fit_name = "Template fit"
    native.save_path = str(tmp_path / "nat" / "results.csv")
    native.run()
    native.wait()
    assert native.message == "Batch complete" and native.message_ok and not native.running
    assert native.result_rows() == [
        {c: r.get(c, "") for c in runner.FIELDNAMES} for r in qt._results.rows
    ]  # noqa: SLF001
    assert (tmp_path / "nat" / "results.csv").read_text() == (
        tmp_path / "qt" / "results.csv"
    ).read_text()
    names = lambda p: sorted(zipfile.ZipFile(p).namelist())  # noqa: E731
    assert names(tmp_path / "nat" / "results_fit_results.zip") == names(
        tmp_path / "qt" / "results_fit_results.zip"
    )
    assert (tmp_path / "nat" / "results.docx").exists() == (
        tmp_path / "qt" / "results.docx"
    ).exists()
    assert [name for name, _ in nat_session.log] == [name for name, _ in qt_session.log]
    assert [(p.name, p.value, p.fixed) for p in nat_session.fits[0].model.parameters_all] == [
        (p.name, p.value, p.fixed) for p in qt_session.fits[0].model.parameters_all
    ]
    # the Qt box listed the CSV, the DOCX when written and the ZIP; the window lists the same lines
    qt_lines = shown[-1][2].splitlines()
    mine = [
        line.replace("/nat/", "/qt/")
        for line in native.outputs
        if not line.startswith("DOCX report not written")
    ]
    assert mine == qt_lines
    rows = native.result_rows()
    assert [r["Filename"] for r in rows[::3]] == ["Sample A", "Sample C", files[0], files[1]]
    assert [r["Run"] for r in rows[::3]] == ["1", "2", "3", "4"]
    assert [r["Value"] for r in rows if r["Parameter"] == "tau"] == [
        1.0,
        1.5,
        2.0,
        2.5,
    ]  # restored to the template each run


def test_the_results_table_cells_equal_the_qt_results_html(qapp, monkeypatch, tmp_path):
    session = FakeSession()
    (tmp_path / "o").mkdir()
    qt, _ = qt_run(
        monkeypatch, tmp_path, session, make_files(tmp_path), [0], tmp_path / "o" / "r.csv"
    )
    native = BatchModel(session=FakeSession())
    native.files = make_files(tmp_path)
    native.selected_dataset_indices = [0]
    native.selected_fit_name = "Template fit"
    native.save_path = str(tmp_path / "o2.csv")
    native.run()
    native.wait()
    html = qt.results_html()
    cells = re.findall(r"<td>(.*?)</td>", html)
    flat = [str(r[c]) for r in native.result_rows() for c in runner.FIELDNAMES]
    assert cells == flat


def test_no_data_no_fit_and_a_missing_csv_are_the_qt_warnings_as_lines_and_a_chooser(
    qapp, monkeypatch, tmp_path
):
    shown = []
    from chisurf.gui import dialogs

    monkeypatch.setattr(dialogs, "warning", lambda parent, title, text: shown.append((title, text)))
    qt = BatchViewModel()
    qt.fit_names = lambda: ["Template fit"]
    qt.run()
    native = BatchModel(session=FakeSession())
    native.run()
    assert shown[0] == ("No data", "Select datasets or add files first.")
    assert (
        native.message == "No data: Select datasets or add files first." and not native.message_ok
    )
    qt2 = BatchViewModel()
    qt2.files = ["/x/a.sm"]
    qt2.run()
    native2 = BatchModel(session=FakeSession(fits=()))
    native2.files = ["/x/a.sm"]
    native2.run()
    assert shown[1] == ("No fit", "Select a template fit first.")
    assert native2.message == "No fit: Select a template fit first."
    native3 = BatchModel(session=FakeSession())
    native3.files = ["/x/a.sm"]
    native3.run()  # no CSV path: the Qt tool opened a save dialog
    assert native3.dialog_request == "results" and not native3.running


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
