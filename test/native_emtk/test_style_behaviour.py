"""Behavioural feature parity: drive the native app through each Qt feature.

The surface sweep (test_settings_feature_parity) proves each Qt feature has a
native implementation path. This file goes further for the highest-risk panels:
it *drives* the real workflow through the native app and asserts the same
observable outcome the Qt widget produces. Panels are added here as their
behaviour is audited; presence in the surface sweep alone does not count.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from chisurf.plugins.core.style_manager.gui.app import StyleManagerApp, StyleManagerModel


@pytest.fixture
def style_app():
    tmp = pathlib.Path(tempfile.mkdtemp())
    app = StyleManagerApp(model=StyleManagerModel(styles_dir=tmp, package_dir=tmp / "defaults"))
    return app, tmp


def test_style_new_save_apply_reset_flow(style_app):
    """The Qt StyleManager flow: new -> save -> load -> apply -> reset."""
    app, styles_dir = style_app
    applied = []
    app.model.apply_callback = applied.append

    app.model.new("parity_test", discard=True)
    target = styles_dir / "parity_test.css"
    app.model.save(target, overwrite=True)
    assert target.exists(), "save wrote no style file"

    app.request_load(target)  # app-level delegate, including the discard guard
    assert pathlib.Path(app.model.current_file).resolve() == target.resolve()

    app.model.apply()
    assert applied, "apply did not reach the application style callback"

    app.model.reset(discard=True)  # discard uncommitted edits


def test_style_new_creates_the_css_file(style_app):
    """new() writes <name>.css into the styles directory."""
    app, styles_dir = style_app
    ok = app.model.new("session", discard=True)
    assert ok is not False
    assert (styles_dir / "session.css").exists(), (
        "new() must create the .css file"
    )
    # Recreating over an existing file is refused.
    assert app.model.new("session", discard=False) is False
