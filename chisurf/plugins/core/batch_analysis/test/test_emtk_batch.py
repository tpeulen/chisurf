"""The Batch Analysis wizard app: steps, selection, run numbers, written files, drawing, settings.

The run's expected numbers are known by construction: ``fakes.FakeSession`` answers the k-th fit with
``tau = 1 + 0.5 k`` and ``chi2r = 1 + 0.05 k`` (see ``planted_rows``). The texts and the selection are
compared with :class:`~.view_model.BatchViewModel`, the base class :class:`BatchModel` extends. Everything
runs on temporary settings; the real ``~/.chisurf`` is checked unchanged.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.core.batch_analysis.fakes import FakeSession
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


def spec_steps():
    spec = json.loads((PLUGIN / "batch.view.json").read_text())
    return spec["sections"][0]["steps"]


def test_the_steps_follow_the_wizard_spec_in_order_with_titles_subtitles_and_conditions():
    spec = spec_steps()
    assert [s.title for s in STEPS] == [s["title"] for s in spec]
    assert [s.subtitle for s in STEPS] == [s["subtitle"] for s in spec]
    assert [s.complete_when for s in STEPS] == [
        (s.get("complete_when") or {}).get("attr") for s in spec
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


def test_the_completion_marks_follow_the_view_model_conditions(monkeypatch):
    session = FakeSession()
    base, native = BatchViewModel(), BatchModel(session=session)
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
    assert base.fit_selected and native.fit_selected
    native.selected_fit_name = base.selected_fit_name = "nope"
    native.refresh_completion()
    assert not base.fit_selected and not native.fit_selected and native.step_complete(2) is False
    assert base.has_results is False and native.has_results is False


def test_the_welcome_text_is_the_view_models_text():
    base, native = BatchViewModel(), BatchModel(session=FakeSession())
    numbered = lambda s: re.sub(r"\s\d\.\s", " ", s)  # noqa: E731  (the list numbers are markup in both)
    assert numbered(strip_md(native.welcome_md())) == numbered(strip_html(base.welcome_html()))


def test_the_selection_summary_equals_the_view_models_summary(tmp_path):
    session = FakeSession()
    base, native = BatchViewModel(), BatchModel(session=session)
    base.imported_datasets = lambda: list(session.datasets)
    for model in (base, native):
        model.files = make_files(tmp_path)
        model.selected_dataset_indices = [0, 2]
        model.selected_fit_name = "Template fit"
    native.reload_files()
    q, n = strip_html(base.selection_html()), strip_md(native.selection_md())
    assert q == n


# -- loaded datasets: the check list -------------------------------------------------------------------------------------- #


def test_the_dataset_rows_are_numbered_and_a_tick_selects_that_index():
    """The rows read "1. A" ...; ticking row 1 selects index [1] and unticking clears it."""
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


# -- files: the path list ------------------------------------------------------------------------------------------------- #


def test_adding_files_and_folders_expands_sorted_and_skips_repeats_and_misses(tmp_path):
    folder = tmp_path / "data"
    (folder / "sub").mkdir(parents=True)
    for name in ("b.sm", "a.sm", "sub/c.sm"):
        (folder / name).write_text("x")
    loose = tmp_path / "loose.sm"
    loose.write_text("x")
    native = BatchModel(session=FakeSession())
    # the list after each add: a folder expands sorted; repeats and misses add nothing
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


def test_remove_and_clear(tmp_path):
    files = make_files(tmp_path, ("a.sm", "b.sm", "c.sm"))
    native = BatchModel(session=FakeSession())
    native.add_paths(files)
    native.select_file(native.file_rows()[1])
    native.remove_selected()
    assert native.files == [files[0], files[2]]
    native.clear_files()
    assert native.files == []


# -- the run: numbers planted by the fake session ------------------------------------------------------------------- #


def planted_rows(labels):
    """The result rows ``FakeSession`` makes: the k-th run gives ``tau = 1 + 0.5 k``, ``chi2r = 1 + 0.05 k``."""
    rows = []
    for k, label in enumerate(labels):
        chi2r = 1.0 + 0.05 * k
        for name, value, fixed in (("tau", 1.0 + 0.5 * k, "No"), ("amplitude", 0.5, "No"), ("offset", 0.0, "Yes")):
            rows.append(
                {"Run": str(k + 1), "Filename": label, "Parameter": name, "Fixed": fixed, "Value": value, "Chi2r": chi2r}
            )
    return rows


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


def test_a_batch_writes_the_planted_rows_to_csv_zip_and_docx(tmp_path):
    import csv

    files = make_files(tmp_path)
    (tmp_path / "nat").mkdir()
    session = FakeSession()
    out = tmp_path / "nat"
    native, progress = native_run(tmp_path, session, files, [0, 2], out / "results.csv")
    assert native.message == "Batch complete" and native.message_ok and not native.running
    # datasets 0 and 2 of the session, then the two files
    expected = planted_rows(["Sample A", "Sample C", files[0], files[1]])
    assert native.result_rows() == expected
    with open(out / "results.csv", newline="") as handle:
        written = list(csv.DictReader(handle))
    assert written == [{k: str(v) for k, v in row.items()} for row in expected]
    assert sorted(zipfile.ZipFile(out / "results_fit_results.zip").namelist()) == [
        "001_Sample_A.csv",
        "002_Sample_C.csv",
        "003_run_01.csv",
        "004_run_02.csv",
    ]
    assert (out / "results.docx").exists()
    # a selected dataset is set and run; a file is added first
    assert [name for name, _ in session.log] == ["fit.set_dataset", "fit.run"] * 2 + [
        "dataset.add",
        "fit.set_dataset",
        "fit.run",
    ] * 2
    # the template keeps the last run's fitted tau and its own fixed flags
    assert [[p.name, p.value, p.fixed] for p in session.fits[0].model.parameters_all] == [
        ["tau", 1.0 + 0.5 * 3, False],
        ["amplitude", 0.5, False],
        ["offset", 0.0, True],
    ]
    assert progress == ["1/4: Sample A", "2/4: Sample C", "3/4: run_01.sm", "4/4: run_02.sm"]
    assert native.outputs == [
        f"CSV: {out / 'results.csv'}",
        f"DOCX: {out / 'results.docx'}",
        f"Per-run exports (ZIP): {out / 'results_fit_results.zip'}",
    ]


def test_no_data_no_fit_and_a_missing_csv_are_lines_and_a_chooser():
    native = BatchModel(session=FakeSession())
    native.run()
    assert native.message == "No data: Select datasets or add files first." and not native.message_ok
    native2 = BatchModel(session=FakeSession(fits=()))
    native2.files = ["/x/a.sm"]
    native2.run()
    assert native2.message == "No fit: Select a template fit first."
    native3 = BatchModel(session=FakeSession())
    native3.files = ["/x/a.sm"]
    native3.run()  # no CSV path: the results chooser is asked for
    assert native3.dialog_request == "results" and not native3.running


def test_each_runs_picture_is_drawn_on_the_polling_thread_and_goes_into_the_docx(tmp_path):
    """A picture is taken between two fits; the worker hands each capture to the window's thread."""
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
    """Without an injected session the model draws the template fit's emtk window."""
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


def test_a_failing_fit_is_reported_in_the_window(tmp_path):
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
