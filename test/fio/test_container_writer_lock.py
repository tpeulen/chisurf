"""One writer at a time, per container, across processes.

Nothing stopped two processes opening the same container for writing at once.
Both succeeded instantly, neither was told, and the last to commit decided what
the file said. A running ChiSurf and a script reaching the same measurement is
not an exotic case — it is what happens when someone re-runs an analysis while
the app that produced it is still open.

Readers are deliberately unaffected: a viewer must not be locked out by an
analysis, and reading a container mid-write is the pre-existing behaviour that
the commit-on-exit design already accounts for.
"""

from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

import pytest

from chisurf.core.fio.pto import Measurement, PtoMfdbError

DATA = (
    Path(__file__).resolve().parents[2]
    / "chisurf" / "plugins" / "burst" / "burst_selection"
    / "tests" / "data" / "bh_spc132_sm_dna"
)
SPC = DATA / "m000.spc"

pytestmark = pytest.mark.skipif(not SPC.exists(), reason="no BH SPC test data")


@pytest.fixture
def container(tmp_path: Path) -> Path:
    from chisurf.plugins.core.tttr_to_pto import api as pto_api

    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    return pto_api.convert(source)


def _open_writable(path, queue):
    """Open for writing in a *separate process*, and report what happened."""
    try:
        from chisurf.core.fio.pto import Measurement as M

        with M.open(path, writable=True):
            queue.put(("ok", ""))
    except Exception as exc:  # noqa: BLE001
        queue.put((type(exc).__name__, str(exc)))


def test_a_second_writer_is_refused_and_told_who_has_it(container: Path):
    """And refused *immediately*: a writer that waits looks like one that hung."""
    ctx = mp.get_context("spawn")
    queue = ctx.Queue()

    with Measurement.open(container, writable=True):
        process = ctx.Process(target=_open_writable, args=(str(container), queue))
        process.start()
        process.join(60)
        assert not process.is_alive(), "the second writer blocked instead of failing"
        kind, message = queue.get(timeout=10)

    assert kind == "PtoMfdbError", f"expected a refusal, got {kind}: {message}"
    assert "open for writing by" in message
    assert "pid" in message, "the refusal must name the holder"


def test_a_reader_is_never_locked_out(container: Path):
    """A viewer must not be blocked by an analysis writing beside it."""
    with Measurement.open(container, writable=True):
        with Measurement.open(container, writable=False) as reader:
            assert reader.artifacts()


def test_the_lock_is_released_when_the_writer_finishes(container: Path):
    """A lock outliving its handle blocks the next writer for the process's life."""
    with Measurement.open(container, writable=True):
        pass
    with Measurement.open(container, writable=True):
        pass  # would raise if the first had not released

    assert not Path(str(container) + ".lock").exists(), "the sidecar was left behind"


def test_the_lock_is_released_when_the_writer_raises(container: Path):
    """The failure path is the one that strands a lock."""
    with pytest.raises(RuntimeError):
        with Measurement.open(container, writable=True):
            raise RuntimeError("boom")

    with Measurement.open(container, writable=True):
        pass


def test_two_analyses_of_one_measurement_do_not_race(container: Path):
    """The case this came from: a re-run while the first is still writing."""
    from chisurf.core.datastore import store_from_arrays

    import numpy as np

    with Measurement.open(container, writable=True) as first:
        first.put_table(
            "probe",
            store_from_arrays({"n": np.arange(10, dtype=np.int64)}),
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
        )
        ctx = mp.get_context("spawn")
        queue = ctx.Queue()
        process = ctx.Process(target=_open_writable, args=(str(container), queue))
        process.start()
        process.join(60)
        kind, _message = queue.get(timeout=10)
    assert kind == "PtoMfdbError"

    # And the first writer's own result survived, which is the point.
    with Measurement.open(container, writable=False) as reader:
        assert reader.get_store("probe") is not None
