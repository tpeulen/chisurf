"""While a batch runs, the MLE wizard must not change underneath it.

Both long runs read their configuration once — the batch ships it to worker
processes, the hyperparameter search writes it into the wizard per trial — and
both pump the event loop while they run. An edit landing in between applies to
part of the work and not the rest, silently, and the result is a table nobody
can reproduce.
"""

import pytest

from chisurf.gui import QtWidgets


@pytest.fixture
def wizard(qtbot):
    """A constructed MLE wizard."""
    from chisurf.plugins.burst.burst_mle_analysis.wizard import MLELifetimeAnalysisWizard

    w = MLELifetimeAnalysisWizard()
    qtbot.addWidget(w)
    return w


class TestFrozenInputs:

    def test_freezing_reaches_every_control_and_restores_it(self, wizard):
        """Not just the container: every editable control, and back again.

        Counting them is the point — the action row at the top of this wizard is
        inside the central widget rather than in a `QToolBar`, so a check on the
        container alone would have passed while `Opt` and `Auto IRF` stayed
        clickable.
        """
        buttons = wizard.findChildren(QtWidgets.QToolButton)
        spins = wizard.findChildren(QtWidgets.QDoubleSpinBox)
        assert buttons and spins
        live_before = sum(w.isEnabled() for w in buttons + spins)
        assert live_before > 0

        wizard._set_inputs_frozen(True)
        assert not wizard.centralWidget().isEnabled()
        assert sum(w.isEnabled() for w in buttons + spins) == 0

        wizard._set_inputs_frozen(False)
        assert wizard.centralWidget().isEnabled()
        # exactly what was live before, no more: disabling a parent must not
        # clobber a child's own disabled state
        assert sum(w.isEnabled() for w in buttons + spins) == live_before

    def test_the_hpo_freezes_for_its_duration(self, wizard, monkeypatch):
        """The search drives the wizard; a click between trials must not land."""
        from chisurf.plugins.burst.burst_mle_analysis import utils

        seen = []
        monkeypatch.setattr(
            utils, "optimize_hyperparameters",
            lambda wiz, **kw: seen.append(wiz.centralWidget().isEnabled()),
        )
        wizard.optimize_hyperparameters(n_iter=1)
        assert seen == [False]                       # frozen while it ran
        assert wizard.centralWidget().isEnabled()    # and released after

    def test_a_failed_hpo_does_not_leave_the_wizard_disabled(self, wizard, monkeypatch):
        """The `finally` matters as much as the freeze."""
        from chisurf.plugins.burst.burst_mle_analysis import utils

        def boom(wiz, **kw):
            raise RuntimeError("search blew up")

        monkeypatch.setattr(utils, "optimize_hyperparameters", boom)
        monkeypatch.setattr(
            "chisurf.plugins.burst.burst_mle_analysis.wizard.dialogs.error",
            lambda *a, **k: None,
        )
        wizard.optimize_hyperparameters(n_iter=1)
        assert wizard.centralWidget().isEnabled()

    def test_a_batch_with_no_data_does_not_freeze(self, wizard):
        """The early return must not disable a wizard that never started."""
        wizard.df_bursts = None
        wizard.process_bursts()
        assert wizard.centralWidget().isEnabled()


class TestDeadCodeStaysGone:

    def test_the_irf_cache_builder_has_no_unreachable_tail(self):
        """220 lines of an orphaned burst-processing routine sat after its return."""
        import ast
        import inspect
        import textwrap

        from chisurf.plugins.burst.burst_mle_analysis.wizard import MLELifetimeAnalysisWizard

        source = textwrap.dedent(inspect.getsource(
            MLELifetimeAnalysisWizard._build_irf_bg_cache))
        body = ast.parse(source).body[0].body
        returns = [i for i, st in enumerate(body) if isinstance(st, ast.Return)]
        assert returns, "expected a return"
        assert returns[-1] == len(body) - 1, "statements after the final return are unreachable"
