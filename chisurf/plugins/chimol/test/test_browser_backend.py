"""chimol's renderer survives emtk's browser backend.

The backend itself -- ``emtk.gpu.browser``, the translation from
``create_buffer(size=..., usage=...)`` to ``createBuffer({size, usage})`` -- is
emtk's and tested there (``emtk/tests/test_gpu_browser.py``). What is chimol's
is the set of calls its engine makes, checked below against the same recording
stand-in for ``js``.

Why this can be tested without a browser
----------------------------------------
The backend's whole job is a translation: ``create_buffer(size=..., usage=...)``
becomes ``createBuffer({size, usage})``. That is a property of the *mapping*,
not of the GPU, so it can be checked against a recording stand-in for ``js`` --
and it is worth checking that way, because the mistakes it makes are silent.
A descriptor key left in ``snake_case`` arrives as ``undefined`` and surfaces as
a validation error naming a field the caller did pass; a nested key missed one
level down passes the outer validation and drops the inner value.

What still needs a browser is whether the frame *looks* right, and that is a
different question asked with a screenshot.
"""

from __future__ import annotations

import sys
import types

import pytest
from emtk.gpu import browser


class _Recorder:
    """Stands in for a JavaScript object, remembering what was called on it."""

    def __init__(self, name="root", log=None):
        self.name = name
        self.log = log if log is not None else []

    def __getattr__(self, item):
        if item.startswith("_"):
            raise AttributeError(item)

        def call(*args, **kwargs):
            self.log.append((f"{self.name}.{item}", args, kwargs))
            return _Recorder(f"{self.name}.{item}()", self.log)

        call.__name__ = item
        return call


@pytest.fixture
def fake_js(monkeypatch):
    """Install a fake ``js`` and ``pyodide.ffi`` so the backend can be driven."""
    js = types.ModuleType("js")

    class _Object:
        @staticmethod
        def fromEntries(pairs):  # noqa: N802 - JavaScript's spelling
            return dict(pairs)

    js.Object = _Object
    js.navigator = types.SimpleNamespace(gpu=_Recorder("navigator.gpu"))

    ffi = types.ModuleType("pyodide.ffi")

    def _to_js(value, dict_converter=None, **_kwargs):
        # Mirror Pyodide: a dict becomes whatever `dict_converter` makes of its
        # items. The default there is a Map, which is exactly the trap the
        # backend passes `Object.fromEntries` to avoid.
        if isinstance(value, dict):
            items = [(k, _to_js(v, dict_converter=dict_converter)) for k, v in value.items()]
            return dict_converter(items) if dict_converter else dict(items)
        if isinstance(value, (list, tuple)):
            return [_to_js(v, dict_converter=dict_converter) for v in value]
        return value

    ffi.to_js = _to_js
    pyodide = types.ModuleType("pyodide")
    pyodide.ffi = ffi

    monkeypatch.setitem(sys.modules, "js", js)
    monkeypatch.setitem(sys.modules, "pyodide", pyodide)
    monkeypatch.setitem(sys.modules, "pyodide.ffi", ffi)
    return js


def test_the_real_engine_survives_the_translation(fake_js):
    """The renderer builds its pipelines through the browser backend.

    The tests above check the mapping on calls written for them. This one
    checks the mapping on the calls the **engine actually makes** -- the ones a
    hand-written fixture would not think to include. Constructing
    ``WgpuMeshRenderer`` builds a bind-group layout, a pipeline layout, four
    shader modules and eight render pipelines, and every descriptor among them
    goes through :func:`browser._descriptor`.

    It cannot say whether the frame is *right* -- that needs a GPU and a
    screenshot. It says that nothing the engine sends arrives mangled, which is
    the failure this layer actually risks: a key left in ``snake_case`` is
    ``undefined`` on the other side, and WebGPU reports it as a missing field
    rather than as a wrong one.
    """
    from chimol.render.wgpu_backend import WgpuMeshRenderer

    log: list = []
    device = browser._Js(_Recorder("device", log))
    device.js.adapter = None

    WgpuMeshRenderer(320, 240, format="rgba8unorm", device=device)

    made = [entry[0].rsplit(".", 1)[-1] for entry in log]
    assert "createShaderModule" in made
    assert "createRenderPipeline" in made
    assert "createBindGroupLayout" in made
    assert "createPipelineLayout" in made

    # Nothing may reach JavaScript still carrying an underscore: that is what a
    # missed translation looks like, at every depth.
    def keys_of(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                yield key
                yield from keys_of(nested)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from keys_of(item)

    snake = sorted(
        {
            key
            for _name, args, _kwargs in log
            for arg in args
            for key in keys_of(arg)
            if isinstance(key, str) and "_" in key
        }
    )
    assert not snake, f"these descriptor keys were never camel-cased: {snake}"

    # The shader text itself must arrive -- the same WGSL the desktop compiles.
    shaders = [
        args[0]["code"] for name, args, _kwargs in log if name.endswith("createShaderModule")
    ]
    assert shaders, "no shader module was created"
    assert all("fn shade(" in code for code in shaders), (
        "the shared prelude is missing, so these are not the composed shaders"
    )
