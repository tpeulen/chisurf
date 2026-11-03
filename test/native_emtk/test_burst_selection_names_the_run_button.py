"""Burst Selection's texts name the button that is there: Run standalone, Next in the pipeline.

The pipeline step has no Run button (Next runs the step), but its preview said "press Run to search every
photon", sending the user looking for a button that does not exist.
"""

from chisurf.plugins.burst.burst_selection.gui.native import create_app


def test_standalone_texts_say_run():
    app = create_app(restore=False)
    assert app.model.run_word == "Run"
    assert "press Run" in app.model.status_text


def test_pipeline_texts_say_next_never_run():
    app = create_app(restore=False, pipeline=True)
    assert app.model.run_word == "Next"
    assert "Run" not in app.model.status_text and "Next" in app.model.status_text
