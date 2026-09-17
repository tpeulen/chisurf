"""Every imaging tool writes into the measurement's file, through one seam.

`<source>.imaging.h5` can hold exactly one thing: a per-pixel table. A curve,
a vector field, a track table or a stack has nowhere to go in it, which is why
each of those grew an output of its own beside it. In the container a map is a
table at `pixel` grain and everything else is a table at *its* grain, so
nothing has to leave the file.

The tools share one base, so these tests drive one of them and cover all of
them.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chisurf.core.datastore import column_names, row_count
from chisurf.core.fio.pto import Measurement

PTU = Path(__file__).resolve().parents[5] / "test" / "data" / "clsm" / "Leica_SP5.ptu"

pytestmark = pytest.mark.skipif(not PTU.exists(), reason="no CLSM test data")


@pytest.fixture
def computed(tmp_path: Path):
    """An N&B view model that has run over a real CLSM measurement."""
    from chisurf.plugins.microscopy.img_pixel_nb.gui.view_model import NBViewModel

    source = tmp_path / PTU.name
    source.write_bytes(PTU.read_bytes())
    model = NBViewModel()
    model.load_file(str(source))
    model.compute()
    return model, source


def test_the_maps_land_in_the_measurements_own_file(computed):
    model, source = computed
    written = Path(model.write_container())
    assert written == source.with_suffix(".pto")

    with Measurement.open(written) as m:
        table = m.get_store("nb")
        assert row_count(table) > 0
        assert {"X pixel", "Y pixel"} <= set(column_names(table))
        uid = m._resolve("nb")
        assert m.tag(uid, "_mmfdb_artifact.row_grain") == "pixel"
        assert m.tag(uid, "_mmfdb_operation.operation_type") == "number_and_brightness"


def test_a_channel_suffix_does_not_hide_the_unit(computed):
    """The columns are `N (ch0)`, not `N`.

    Every imaging column is suffixed with the channel it came from, so a units
    table matched on the whole name matches nothing and every column comes back
    unitless — silently, because no unit and an unknown unit are written the
    same way.
    """
    model, _ = computed
    written = model.write_container()
    with Measurement.open(written) as m:
        table = m.get_store("nb")
        units = {c: m.column_units(table, c) for c in column_names(table)}
    suffixed = [c for c in units if c.startswith(("N (", "B ("))]
    assert suffixed, "the fixture produced no channel-suffixed column to check"
    for name in suffixed:
        # N is a molecule number, B a count per dwell
        assert units[name] == ("dimensionless" if name.startswith("N (") else "counts")
    assert units["X pixel"] == "pixels"


def test_recomputing_does_not_add_a_second_map(computed):
    model, _ = computed
    written = model.write_container()
    with Measurement.open(written) as m:
        before = m._f.n_objects()
    for _ in range(3):
        model.write_container()
    with Measurement.open(written) as m:
        assert m._f.n_objects() == before


def test_nothing_is_written_without_a_source_file():
    """A tool with no file has no measurement to belong to, and inventing one
    would put results next to nothing.
    """
    from chisurf.plugins.microscopy.img_pixel_nb.gui.view_model import NBViewModel

    model = NBViewModel()
    assert model.write_container() == ""
