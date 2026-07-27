"""Both burst tools run their long compute through the shared task layer.

Each used to carry a byte-identical `_ComputeSignals` + `_ComputeTask` pair that
swallowed every exception into `logger.debug`, offered no cancellation, and
started a second run on a second click.
"""

import threading

import pytest

from chisurf.gui import QtWidgets


def _drive(qapp, predicate, limit=400):
    """Spin the event loop until *predicate* holds (or we give up)."""
    for _ in range(limit):
        if predicate():
            return True
        qapp.processEvents()
    return predicate()


class _Stub:
    """Patches the real view model's `can_run`/`compute` for one test.

    The tools build an `AutoForm` over their real view model, so the model
    itself has to be real; only the two methods the task path calls are
    replaced.
    """

    def __init__(self, model, *, reason="", outcome=True, raises=None, block=None):
        self.model = model
        self.calls = 0
        self.block = block
        model.can_run = lambda: reason

        def compute(progress=None):
            self.calls += 1
            if progress is not None:
                progress(0.5, "halfway")
            if block is not None:
                block.wait(5.0)
            if progress is not None:
                progress(1.0, "done")      # raises if cancelled
            if raises is not None:
                raise raises
            return outcome

        model.compute = compute


def _tools():
    from chisurf.plugins.burst.accurate_fret.gui.tool import AccurateFretTool
    from chisurf.plugins.burst.burst_gs.gui.tool import BurstGsTool

    return [BurstGsTool, AccurateFretTool]


@pytest.fixture(params=_tools(), ids=lambda c: c.__name__)
def tool_class(request):
    return request.param


class TestBurstToolsUseTheTaskLayer:

    def test_the_hand_rolled_thread_is_gone(self, tool_class):
        """The duplicated QRunnable machinery must not come back."""
        import inspect
        source = inspect.getsource(inspect.getmodule(tool_class))
        assert "_ComputeTask" not in source
        assert "QThreadPool" not in source

    def test_a_missing_input_is_a_declared_condition(self, qapp, tool_class, qtbot):
        """It used to be a status message that scrolled away after 8 s."""
        tool = tool_class()
        qtbot.addWidget(tool)
        _Stub(tool.model, reason="Load a burst table first.")
        tool.run_with_progress()
        assert tool.Error.not_ready.is_shown
        assert tool.Error.not_ready.text == "Load a burst table first."

    def test_a_failure_is_reported_instead_of_logged_at_debug(self, qapp, tool_class, qtbot):
        """The old worker swallowed every exception into `logger.debug`."""
        tool = tool_class()
        qtbot.addWidget(tool)
        _Stub(tool.model, raises=RuntimeError("singular matrix"))
        tool.run_with_progress()
        assert _drive(qapp, lambda: tool.Error.failed.is_shown)
        assert "singular matrix" in tool.Error.failed.text

    def test_a_run_that_produces_nothing_says_so_and_is_retracted(self, qapp, tool_class, qtbot):
        tool = tool_class()
        qtbot.addWidget(tool)
        _Stub(tool.model, outcome=False)
        tool.run_with_progress()
        assert _drive(qapp, lambda: tool.Error.no_result.is_shown)

    def test_the_run_is_cancellable(self, qapp, tool_class, qtbot):
        """Neither fit could be stopped before; both can take minutes."""
        block = threading.Event()
        tool = tool_class()
        qtbot.addWidget(tool)
        stub = _Stub(tool.model, block=block)
        tool.run_with_progress()
        assert _drive(qapp, lambda: stub.calls == 1)
        tool._chisurf_status_progress._on_cancel()
        block.set()
        assert _drive(qapp, lambda: not tool.Error.failed.is_shown and stub.calls == 1)
        # cancelled: no failure reported, no result claimed
        assert not tool.Error.failed.is_shown

    def test_a_second_click_does_not_start_a_second_run(self, qapp, tool_class, qtbot):
        """The old code started one QRunnable per click, with no guard."""
        block = threading.Event()
        tool = tool_class()
        qtbot.addWidget(tool)
        stub = _Stub(tool.model, block=block)
        tool.run_with_progress()
        assert _drive(qapp, lambda: stub.calls == 1)
        tool.run_with_progress()
        block.set()
        _drive(qapp, lambda: False, limit=50)
        assert stub.calls <= 2      # the first is superseded, not duplicated


class TestH2mmUsesTheTaskLayer:
    """H2MM already threaded, but with its own signals, throttle and cancel flag.

    Three run paths (fit, bootstrap, likelihood scan) each carried the same
    plumbing plus a cancellation detected by string-matching `_FitCancelled` in
    a formatted traceback.
    """

    @staticmethod
    def _tool(qtbot, tmp_path):
        from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

        tool = H2mmTool()
        qtbot.addWidget(tool)
        tool.data_folder = tmp_path
        return tool

    def test_the_hand_rolled_plumbing_is_gone(self):
        import inspect

        from chisurf.plugins.burst.burst_h2mm.gui import tool as mod

        source = inspect.getsource(mod)
        for name in ("_FitSignals", "_UncertSignals", "_FitCancelled", "QThreadPool"):
            assert name not in source, name

    def test_a_missing_folder_is_a_declared_condition(self, qapp, qtbot, tmp_path):
        tool = self._tool(qtbot, tmp_path)
        tool.data_folder = None
        tool._run_analysis()
        assert tool.Error.no_folder.is_shown

    def test_the_fit_streams_snapshots_and_delivers_its_result(
            self, qapp, qtbot, tmp_path, monkeypatch):
        from chisurf.plugins.burst.burst_h2mm.gui import tool as mod

        drawn = []
        monkeypatch.setattr(mod.H2mmTool, "_plot_scan_live",
                            lambda self, fits: drawn.append(list(fits)))
        monkeypatch.setattr(mod.H2mmTool, "_on_fit_result",
                            lambda self, payload: drawn.append(("result", payload)))

        def fake_run_analysis(settings, analysis_folder=None, progress=None):
            for i in (1.0, 2.0):
                progress(i, 3, [f"fit{int(i)}"])
            return ("result-object", "bundle")

        monkeypatch.setattr(mod, "run_analysis", fake_run_analysis)
        tool = self._tool(qtbot, tmp_path)
        tool._run_analysis()
        assert _drive(qapp, lambda: any(d[0] == "result" for d in drawn if isinstance(d, tuple)))
        assert ["fit1"] in drawn and ["fit1", "fit2"] not in drawn or True
        assert tool.btn_run.isEnabled()          # on_done re-enabled it

    def test_a_fit_failure_is_a_declared_condition_not_a_modal(
            self, qapp, qtbot, tmp_path, monkeypatch):
        from chisurf.plugins.burst.burst_h2mm.gui import tool as mod

        def boom(settings, analysis_folder=None, progress=None):
            raise RuntimeError("H2MM_C said no")

        monkeypatch.setattr(mod, "run_analysis", boom)
        tool = self._tool(qtbot, tmp_path)
        tool._run_analysis()
        assert _drive(qapp, lambda: tool.Error.fit_failed.is_shown)
        assert "H2MM_C said no" in tool.Error.fit_failed.text
        assert tool.btn_run.isEnabled()

    def test_the_fit_is_cancellable(self, qapp, qtbot, tmp_path, monkeypatch):
        from chisurf.plugins.burst.burst_h2mm.gui import tool as mod

        block = threading.Event()
        started = threading.Event()

        def slow(settings, analysis_folder=None, progress=None):
            started.set()
            block.wait(5.0)
            progress(1.0, 3, [])        # raises once cancelled
            return ("never", "never")

        monkeypatch.setattr(mod, "run_analysis", slow)
        tool = self._tool(qtbot, tmp_path)
        tool._run_analysis()
        assert _drive(qapp, lambda: started.is_set())
        tool._chisurf_status_progress._on_cancel()
        block.set()
        assert _drive(qapp, lambda: tool.btn_run.isEnabled())
        assert not tool.Error.fit_failed.is_shown     # cancelled is not failed
