"""A caption padded to a shared label column is still translated, and the column fits it.

``chisurf.plugins.emtk_layout.LabelColumn`` pads field captions with spaces so separate grids
start their fields at one x. The padded source was in no catalogue, so the 19 tools using it
drew every padded caption in English in a French or German session (found by the real-use
language matrix, okf/workflows/testing.md "Real-use QA matrix": irf_estimator's
"Regularization").
"""

from __future__ import annotations

from emtk.i18n.testing import isolated
from emtk.testing import Driver


def test_irf_estimator_draws_its_padded_captions_in_french():
    from chisurf.core.support.i18n import register_catalogues
    from chisurf.emtk.plugins import load_plugin

    with isolated(language=None):
        toolkit = register_catalogues()
        toolkit.set_language("fr")
        app = load_plugin("irf_estimator", persist=False)
        try:
            painter = Driver(app, (1100, 720)).frame(3)
            shown = {s.strip() for s in painter.strings}
            assert "Régularisation" in shown, sorted(s for s in shown if "gulari" in s)
            assert "Regularization" not in shown
            caption = next(
                (x, w)
                for ((x, _y, w, _h, _a, s, _c, _b),) in zip(painter.visible_texts)
                if s.strip() == "Régularisation"
            )
            assert caption[1] > 0, "the translated caption is not clipped away"
        finally:
            app.close()
