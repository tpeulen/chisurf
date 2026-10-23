"""The macro recorder writes code for what the user does (actions + console)."""

from __future__ import annotations

import time
from types import SimpleNamespace

from chisurf.emtk.macro_recorder import DEDUPE_SECONDS, MacroRecorder


def _spec(name, *, replayable=True, debounce_ms=0):
    return SimpleNamespace(name=name, replayable=replayable, debounce_ms=debounce_ms)


class _Dispatcher:
    """The dispatcher surface the recorder taps: execute + registry."""

    def __init__(self, specs):
        self.specs = dict(specs)
        self.calls = []

    @property
    def registry(self):
        recorder = self

        class _Registry:
            def resolve_name(self, name):
                return name

            def get(self, name):
                return recorder.specs.get(name)

        return _Registry()

    def execute(self, name, payload=None, summary=None, **kwargs):
        self.calls.append((name, payload, summary))
        return {"ok": name}


def test_a_replayable_action_becomes_a_cs_dispatch_line():
    d = _Dispatcher({"dataset.add": _spec("dataset.add")})
    rec = MacroRecorder()
    rec.attach(d)
    d.execute("dataset.add", {"filename": "m000.pto"}, summary="add m000.pto")
    rec.detach()
    (entry,) = rec.entries
    assert entry.code == "cs_dispatch('dataset.add', {'filename': 'm000.pto'})"
    assert entry.comment == "add m000.pto"
    # the wrapped call passed through and its result survived
    assert d.calls == [("dataset.add", {"filename": "m000.pto"}, "add m000.pto")]
    assert d.execute("dataset.add", {}) == {"ok": "dataset.add"}  # unwrapped again


def test_non_replayable_actions_are_not_recorded():
    d = _Dispatcher({"view.scroll": _spec("view.scroll", replayable=False)})
    rec = MacroRecorder()
    rec.attach(d)
    d.execute("view.scroll", {"row": 3})
    rec.detach()
    assert rec.entries == [] and d.calls, "executed, just not macro material"


def test_debounce_duplicates_collapse_into_one_step():
    d = _Dispatcher({"parameter.set": _spec("parameter.set", debounce_ms=300)})
    rec = MacroRecorder()
    rec.attach(d)
    payload = {"name": "gamma", "value": 0.35}
    d.execute("parameter.set", payload)
    d.execute("parameter.set", payload)  # the trailing edge of the same edit
    rec.detach()
    assert len(rec.entries) == 1
    # but a later, separate edit of the same parameter records again
    rec2 = MacroRecorder()
    rec2.attach(d)
    d.execute("parameter.set", payload)
    stale = time.time() - DEDUPE_SECONDS - 1  # long after: a new interaction
    name, value, _ = rec2._last_action
    rec2._last_action = (name, value, stale)
    d.execute("parameter.set", payload)
    rec2.detach()
    assert len(rec2.entries) == 2


def test_the_script_is_runnable_python():
    d = _Dispatcher({"dataset.add": _spec("dataset.add")})
    rec = MacroRecorder()
    rec.attach(d)
    d.execute("dataset.add", {"filename": "a.pto", "n": 2})
    rec.detach()
    script = rec.script
    assert script.startswith('"""ChiSurf macro, recorded')
    assert "from chisurf.core.actions import dispatch as cs_dispatch" in script
    compile(script, "macro.cm.py", "exec")  # valid Python, editable by hand
    assert "cs_dispatch('dataset.add', {'filename': 'a.pto', 'n': 2})" in script


def test_multiline_payloads_stay_readable_and_valid():
    d = _Dispatcher({"model.update": _spec("model.update")})
    rec = MacroRecorder()
    rec.attach(d)
    d.execute("model.update", {f"parameter_{i}": i for i in range(12)})
    rec.detach()
    compile(rec.script, "macro.cm.py", "exec")
    # pprint wrapped the long dict over lines, still one call
    assert rec.entries[0].code.count("\n") > 1 and rec.entries[0].code.count("cs_dispatch") == 1


def test_detaching_restores_execute_only_if_still_ours():
    d = _Dispatcher({"dataset.add": _spec("dataset.add")})
    rec = MacroRecorder()
    rec.attach(d)
    original = rec._original_execute
    def someone_elses(*a, **k):  # the point of the test: a foreign replacement
        return None

    d.execute = someone_elses
    rec.detach()
    assert d.execute is someone_elses  # never clobbered a foreign replacement
    rec2 = MacroRecorder()
    rec2.attach(d)
    rec2.detach()
    assert d.execute is someone_elses or d.execute is original


def test_unknown_actions_are_recorded_with_their_name():
    d = _Dispatcher({})  # a registry that knows nothing
    rec = MacroRecorder()
    rec.attach(d)
    d.execute("something.new", {"x": 1})
    rec.detach()
    assert rec.entries[0].code.startswith("cs_dispatch('something.new'")
    assert rec.entries[0].comment == "something.new"


def test_save_writes_the_script(tmp_path):
    d = _Dispatcher({"dataset.add": _spec("dataset.add")})
    rec = MacroRecorder()
    rec.attach(d)
    d.execute("dataset.add", {"filename": "a.pto"})
    rec.detach()
    target = tmp_path / "macro.cm.py"
    assert rec.save(target) == str(target)
    assert "cs_dispatch" in target.read_text()
