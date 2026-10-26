"""The TTTR→PTO importer's example: the shared generator's stream, converted."""

from pathlib import Path

from chisurf.plugins.core.tttr_to_pto.demo import make_demo
from chisurf.plugins.core.tttr_to_pto.gui.app import make_app


def test_make_demo_writes_a_photon_stream():
    """The synthetic SPC stream exists and is more than a header."""
    path = make_demo()
    assert path.suffix == ".spc"
    assert path.stat().st_size > 1000


def test_load_example_converts_to_pto():
    """The affordance adds the stream to the workspace and hands it over; the worker writes the
    container, which comes back into the workspace as the example's child."""
    import time

    from chisurf.core.api import dataset_container

    held = dataset_container()
    before = list(held)
    app = make_app()
    model = app.model
    try:
        model.load_example()
        example = next(d for d in held if d not in before)
        deadline = time.monotonic() + 60.0
        while (model.job.running or model.pending) and time.monotonic() < deadline:
            model.poll()
            time.sleep(0.05)
        model.poll()
        rows = model.rows
        assert rows
        outputs = rows[0].get("outputs") or []
        assert outputs, rows[0]
        container = Path(outputs[0])
        assert container.suffix == ".pto"
        assert container.is_file() and container.stat().st_size > 0
        children = [d for d in held if getattr(d, "result_of", "") == example.unique_identifier]
        assert children and children[0].data_kind == "photons"
    finally:
        app.close()
        held[:] = before
