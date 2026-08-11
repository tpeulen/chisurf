"""The browser target: a loader, a demo, and a dev server.

There is no renderer here. chimol's engine is eighteen WGSL shaders and the
Python that hands them to a driver, and the browser runs *that* -- through
Pyodide, with :mod:`chimol.renderer.gpu.browser` in place of ``wgpu-py``.
``boot.js`` starts the interpreter and resolves the GPU device; every frame
after that is the same Python the desktop runs.
"""
from __future__ import annotations

__all__: list[str] = []
