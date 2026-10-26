"""The Datasets workspace shows what each dataset is and narrows to one kind.

Real files are read through the shell (an FCS curve, a TCSPC decay); the kind filter above the table is
operated through its own control, and the table's rows are read back.
"""

from __future__ import annotations

from pathlib import Path

from emtk.testing import Driver

from chisurf.emtk.fit_docks import DATASETS_KEY
from test.native_emtk.test_emtk_shell_fits import (  # noqa: F401  (the fixture and the helpers)
    KRISTINE,
    SHOTS,
    _idle,
    _load,
    _settle,
    shell,
)

REPO = Path(__file__).resolve().parents[2]
TCSPC = REPO / "test" / "data" / "tcspc" / "decay_fit"
DECAY = "Decay_577D.txt"


def _rows(shell):  # noqa: F811
    return [r for r in shell.data.datasets.dataset_rows() if r.get("experiment") != "Global"]


def _loaded(driver, shell):  # noqa: F811
    _load(driver, shell, KRISTINE)
    data = shell.data
    data.read.experiment = "TCSPC"
    data.read.experiment_changed("TCSPC")
    data.read.setup = "TXT/CSV"
    data.read.path = str(TCSPC / "Decay_577D.txt")
    driver.click("read.load")
    # The TXT/CSV reader names the dataset after the whole file name.
    _settle(
        driver,
        lambda: _idle(shell) and any(r["name"] == DECAY for r in data.datasets.datasets),
        "the decay",
    )
    shell.docks.focus(DATASETS_KEY)
    driver.frame(3)


def test_rows_carry_kind_and_source_and_the_filter_narrows_by_kind(shell):  # noqa: F811
    driver = Driver(shell, size=(1300, 900))
    _loaded(driver, shell)
    model = shell.data.datasets
    by_name = {r["name"]: r for r in _rows(shell)}
    assert by_name["Kristine_with_error"]["kind"] == "correlation"
    assert by_name[DECAY]["kind"] == "decay"
    assert by_name[DECAY]["source"] == "Decay_577D.txt"
    assert by_name[DECAY]["source_address"].endswith("Decay_577D.txt")

    values = [value for value, _label in model.kind_options()]
    assert values[0] == "" and {"decay", "correlation"} <= set(values)
    assert "photons" not in values, "a kind no dataset has is not offered"

    model.kind_filter = "decay"
    driver.frame(3)
    assert [r["name"] for r in _rows(shell)] == [DECAY]
    table = shell.data.forms["datasets"].tables["dataset_rows"]
    assert table.control.row_count() == len(model.dataset_rows())

    model.kind_filter = ""
    driver.frame(3)
    assert {r["name"] for r in _rows(shell)} >= {"Kristine_with_error", DECAY}


def test_the_kind_filter_is_a_control_above_the_table(shell):  # noqa: F811
    driver = Driver(shell, size=(1300, 900))
    _loaded(driver, shell)
    form = shell.data.forms["datasets"]
    filter_rect = form.rects.get("kind_filter")
    table_rect = form.tables["dataset_rows"].control
    assert filter_rect is not None, f"no kind filter drawn: {sorted(form.rects)[:20]}"
    texts = " ".join(t[5] for t in driver.painter.texts)
    for header in ("Kind", "Experiment", "Source"):
        assert header in texts, f"{header} column header not drawn"
    assert table_rect is not None
    SHOTS.mkdir(parents=True, exist_ok=True)
    driver.screenshot(SHOTS / "datasets_kinds.png")


def test_a_photon_row_offers_no_model_and_add_analysis_stays_off(shell):  # noqa: F811
    driver = Driver(shell, size=(1300, 900))
    _loaded(driver, shell)
    model = shell.data.datasets
    row = dict(next(r for r in _rows(shell) if r["name"] == DECAY), kind="photons")
    model.select_dataset(row)
    assert model.model_names() == []
    assert not model.enabled("add_fit")
