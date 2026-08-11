"""The one place chimol reaches a GPU.

The engine draws with WGSL -- eighteen shaders, from the rasteriser's
``mesh``/``impostor``/``line`` pipelines to a ray tracer, a BVH build, marching
cubes and a distance transform. Reimplementing that anywhere else is not a
thing anyone should do, so when the engine has to run somewhere other than a
desktop, the part that moves is the few dozen calls that hand those shaders to
a driver -- not the shaders, and not the code around them.

Those calls live behind :mod:`chimol.renderer.gpu.api`, and the driver behind
:mod:`chimol.renderer.gpu.native`. A second backend is a second module beside
``native``; nothing else in the engine changes, and nothing else in the engine
is permitted to name a GPU binding.
"""
from __future__ import annotations

from .api import backend_name, gpu

__all__ = ["gpu", "backend_name"]
