"""What the inspector must get right about a container it did not write.

The claims worth pinning are the ones a list view would quietly get wrong: that a
result with two parents keeps **both** edges, that it is drawn to the right of
both rather than beside the nearer one, and that a step's operation resolves back
to the tool that performs it — which is the whole point of recording the
operation in a file that deliberately never names a program.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.core.fio.pto import Measurement
from chisurf.plugins.core.pto_inspector.core import (
    PtoInspection,
    provenance_graph,
    settings_text,
    short_uid,
)

DATA = Path(__file__).resolve().parents[4].parent / "test" / "data"
PTU = DATA / "clsm" / "Leica_SP5.ptu"

pytestmark = pytest.mark.skipif(not PTU.exists(), reason="instrument test data missing")


@pytest.fixture
def container(tmp_path: Path) -> Path:
    """A container whose last result has two parents, so the DAG is a DAG."""
    import shutil

    raw = tmp_path / "m.ptu"
    shutil.copy(PTU, raw)
    n = 32
    with Measurement.create(raw) as m:
        bursts = m.put_table(
            "bursts",
            {
                "First Photon": np.arange(n, dtype=np.int64),
                "Number of Photons": np.arange(n, dtype=np.int32) + 60,
                "Duration": np.linspace(0.5, 5.0, n),
            },
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"M": 10, "min_photons": 60},
            derived_from=m.instrument_uid,
            units={"Duration": "milliseconds"},
        )
        background = m.put_table(
            "background",
            {"channel": np.array([0, 1], np.int32), "rate": np.array([1.2, 0.7])},
            artifact_kind="background_data",
            operation_type="background_correction",
            row_grain="channel",
            parameters={"window_ms": 100.0},
            derived_from=m.instrument_uid,
        )
        m.put_table(
            "lifetimes",
            {
                "First Photon": np.arange(n, dtype=np.int64),
                "tau": np.linspace(1.0, 4.0, n),
            },
            artifact_kind="analysis_result",
            operation_type="burst_lifetime_fitting",
            row_grain="burst",
            parameters={"model": "1-exponential"},
            derived_from=[bursts, background],
            source_row_column="First Photon",
            target_row_column="First Photon",
            units={"tau": "nanoseconds"},
        )
        m.put_curve(
            "fcs",
            np.logspace(-3, 3, 64),
            np.linspace(1.4, 1.0, 64),
            artifact_kind="fcs_correlation",
            operation_type="fcs_correlation",
            x_units="milliseconds",
            y_units="dimensionless",
            derived_from=m.instrument_uid,
        )
    return tmp_path / "m.pto"


def test_every_object_is_listed_with_its_grain(container: Path):
    """A list that drops the grain cannot say what one row of a table is."""
    with PtoInspection(container) as insp:
        by_name = {item.name: item for item in insp.infos()}
    assert by_name["bursts"].grain == "burst"
    assert by_name["background"].grain == "channel"
    assert by_name["fcs"].grain == "curve_point"
    # Carried, not computed: the operation is genuinely empty, not "unknown".
    assert by_name["m.ptu"].operation == ""


def test_a_result_with_two_parents_keeps_both_edges(container: Path):
    """The case a tree view cannot draw without dropping one of them."""
    with PtoInspection(container) as insp:
        graph = insp.graph()
        lifetimes = next(i for i in insp.infos() if i.name == "lifetimes")
    incoming = [e for e in graph["edges"] if e["target"] == str(lifetimes.uid)]
    assert len(incoming) == 2


def test_a_node_is_drawn_right_of_every_parent(container: Path):
    """Longest path, not shortest: an edge must never run backwards."""
    with PtoInspection(container) as insp:
        graph = insp.graph()
    x = {n["id"]: n["pos"][0] for n in graph["nodes"]}
    assert graph["edges"], "the fixture has edges"
    for edge in graph["edges"]:
        assert x[edge["source"]] < x[edge["target"]]


def test_a_root_has_no_input_port(container: Path):
    """A drawn-but-unconnected input port reads as a missing parent."""
    with PtoInspection(container) as insp:
        graph = insp.graph()
        raw = next(i for i in insp.infos() if i.kind == "tttr_photon_stream")
    node = next(n for n in graph["nodes"] if n["id"] == str(raw.uid))
    assert node["inputs"] == []


def test_the_graph_validates_against_the_node_editor_schema(container: Path):
    """The viewer refuses a graph outright; a missing key must fail here."""
    from chisurf.gui.widgets.node_editor.validation import validate_graph_dict

    with PtoInspection(container) as insp:
        validate_graph_dict(insp.graph())


def test_a_table_reads_back_with_its_units_on_the_columns(container: Path):
    """A number whose unit is only in a convention is a number read wrong."""
    with PtoInspection(container) as insp:
        lifetimes = next(i for i in insp.infos() if i.name == "lifetimes")
        store = insp.store(lifetimes.uid)
        assert Measurement.column_units(store, "tau") == "nanoseconds"


def test_a_non_table_has_no_store(container: Path):
    """Asking for the photon stream as a table must answer "no", not raise."""
    with PtoInspection(container) as insp:
        raw = next(i for i in insp.infos() if i.kind == "tttr_photon_stream")
        assert insp.store(raw.uid) is None


def test_a_curve_reads_back_with_its_axis_units(container: Path):
    """An FCS lag axis is milliseconds; nothing about the numbers says so."""
    with PtoInspection(container) as insp:
        fcs = next(i for i in insp.infos() if i.name == "fcs")
        curve = insp.curve(fcs.uid)
    assert curve["x_units"] == "milliseconds"
    assert len(curve["x"]) == 64


def test_lineage_reaches_the_primary_data(container: Path):
    """The claim the container exists for."""
    with PtoInspection(container) as insp:
        lifetimes = next(i for i in insp.infos() if i.name == "lifetimes")
        names = [step["name"] for step in insp.lineage(lifetimes.uid)]
    assert names[0] == "lifetimes"
    assert "bursts" in names and "background" in names
    assert names[-1] == "m.ptu"


def test_verify_passes_on_an_untouched_file(container: Path):
    with PtoInspection(container) as insp:
        assert insp.verify() == []


def test_opening_something_that_is_not_a_container_is_refused(tmp_path: Path):
    """A clear refusal, not a traceback out of the parser."""
    other = tmp_path / "not.pto"
    other.write_bytes(b"not a container")
    with pytest.raises(ValueError):
        PtoInspection(other)


def test_a_cycle_cannot_hang_the_layout():
    """A written container has none; a damaged one must not lock the viewer up."""
    from chisurf.plugins.core.pto_inspector.core import ArtifactInfo

    a = ArtifactInfo(uid=1, name="a", kind="x", parents=[2])
    b = ArtifactInfo(uid=2, name="b", kind="x", parents=[1])
    graph = provenance_graph([a, b])
    assert len(graph["nodes"]) == 2


def test_settings_text_is_sorted_and_readable():
    assert settings_text({"b": 2, "a": 1}) == "a = 1\nb = 2"
    assert settings_text({}) == ""


def test_short_uid_keeps_a_short_one_whole():
    assert short_uid(42) == "42"
    assert short_uid(1234567890123456).endswith("…")
