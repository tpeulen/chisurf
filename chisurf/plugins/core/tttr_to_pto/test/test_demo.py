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
    """The affordance queues the stream; the worker writes the container file."""
    import time

    app = make_app()
    model = app.model
    model.load_example()
    deadline = 60.0
    while model.job and deadline > 0:
        model.poll()
        time.sleep(0.1)
        deadline -= 0.1
    model.poll()
    rows = model.rows
    assert rows
    outputs = rows[0].get("outputs") or []
    assert outputs, rows[0]
    container = Path(outputs[0])
    assert container.suffix == ".pto"
    assert container.is_file() and container.stat().st_size > 0
