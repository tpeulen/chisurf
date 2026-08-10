"""WGSL compute for the scene-building kernels, with the CPU route beside it.

The geometry kernels that used to be numba are now NumPy and scipy, which is
what makes them portable — but three of them are per-vertex gathers with no
cross-vertex dependence, which is what a GPU is for. This module runs those on
the same WebGPU stack the renderer draws with, in WGSL that a browser can
compile unchanged.

Two rules shape it.

**The CPU route is not a fallback, it is a requirement.** A standalone page
opened from ``file://`` may have no adapter at all, and a headless test machine
often has none either. Every entry point here answers ``None`` when it cannot
run, and every caller has a NumPy path that produces the same numbers. That is
also what makes the GPU path testable: the CPU result is the reference.

**One spatial index, built once, in NumPy.** All three kernels ask the same
question — "which points are near this one" — so they share a uniform grid whose
cell is the query radius, which puts every neighbour in the query cell or one of
its 26 adjacent cells. Building it on the CPU is a sort and a prefix sum; the
kernels then walk it without ever branching on data the host holds.

Precision: the GPU works in ``f32`` and the CPU route in ``f64``, so results
agree to about ``1e-6`` relative, not to the bit. Anything that must be exact
stays on the CPU.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Optional

import numpy as np

WGSL_DIR = pathlib.Path(__file__).with_name("wgsl")

#: Prepended to every compute shader here: the grid layout and the loop that
#: walks a point's 27 neighbouring cells. WGSL has no ``#include``, so
#: composition is concatenation — the same rule the render shaders use.
COMPUTE_PRELUDE = "grid.wgsl"

#: Threads per workgroup. 64 is the portable choice: it is a multiple of both
#: the 32-lane and 64-lane wave sizes in circulation, so no backend runs a
#: partly-empty wave.
WORKGROUP = 64

#: Below this many work items the dispatch is not worth its own setup — buffer
#: creation, submission and readback are a fixed cost of roughly a millisecond,
#: which is more than the NumPy route takes on a small mesh.
MIN_WORK_ITEMS = 20_000

#: Environment override, for tests and for a machine whose driver misbehaves.
#: ``cpu`` disables every kernel here; ``gpu`` skips the size threshold so a
#: small case still dispatches, which is what makes a parity test meaningful.
BACKEND_ENV = "CHIMOL_COMPUTE"

_DEVICE: object | None = None
_DEVICE_TRIED = False


def backend() -> str:
    """Which route the kernels here should take: ``auto``, ``gpu`` or ``cpu``.

    Returns
    -------
    str

    Notes
    -----
    The display config is the user-facing switch and the environment variable
    overrides it, because a test has to be able to force either side without
    writing to a settings file. Both are read per call: this is not a hot path,
    and caching it would make the setting take effect only after a restart.
    """
    import os

    override = os.environ.get(BACKEND_ENV, "").strip().lower()
    if override in ("auto", "gpu", "cpu"):
        return override
    try:
        from ..config import _DISPLAY_CONFIG  # noqa: PLC0415

        choice = str(_DISPLAY_CONFIG.get("compute", {}).get("backend", "auto")).lower()
    except Exception:
        return "auto"
    return choice if choice in ("auto", "gpu", "cpu") else "auto"


def _declines(work_items: int) -> bool:
    """Whether the GPU route should stand aside for this problem size.

    Parameters
    ----------
    work_items : int
        Number of invocations the dispatch would launch.

    Returns
    -------
    bool
    """
    choice = backend()
    if choice == "cpu":
        return True
    if device() is None:
        return True
    return choice != "gpu" and work_items < MIN_WORK_ITEMS


def device():
    """Return a compute device, or ``None`` when this machine has no adapter.

    Returns
    -------
    object or None
        A ``wgpu`` device, cached for the process.

    Notes
    -----
    Failure is normal and silent by design — no adapter is the expected state on
    a headless runner and in a page served from ``file://``. What must never
    happen is a *hidden* fallback in the other direction: a caller that quietly
    produces different numbers depending on whether this returned something.
    """
    global _DEVICE, _DEVICE_TRIED
    if _DEVICE_TRIED:
        return _DEVICE
    _DEVICE_TRIED = True
    try:
        import wgpu

        adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
        _DEVICE = adapter.request_device_sync()
    except Exception:
        _DEVICE = None
    return _DEVICE


def available() -> bool:
    """Whether a compute device could be obtained.

    Returns
    -------
    bool
    """
    return device() is not None


def load_compute_wgsl(name: str) -> str:
    """Read a compute shader, prefixed with the grid prelude.

    Parameters
    ----------
    name : str
        File name inside the ``wgsl`` directory.

    Returns
    -------
    str
    """
    source = (WGSL_DIR / name).read_text()
    if name == COMPUTE_PRELUDE:
        return source
    return (WGSL_DIR / COMPUTE_PRELUDE).read_text() + "\n" + source


@dataclass
class UniformGrid:
    """A cell list over a point set, sized so one cell equals the query radius.

    Attributes
    ----------
    origin : numpy.ndarray
        ``(3,)`` world position of cell ``(0, 0, 0)``'s lower corner.
    dims : numpy.ndarray
        ``(3,)`` int32 cell counts along each axis.
    inv_cell : float
        Reciprocal of the cell edge length.
    start : numpy.ndarray
        ``(n_cells + 1,)`` uint32 prefix sums into :attr:`order`.
    order : numpy.ndarray
        ``(n_points,)`` uint32 point indices, grouped by cell.
    """

    origin: np.ndarray
    dims: np.ndarray
    inv_cell: float
    start: np.ndarray
    order: np.ndarray


def build_grid(points: np.ndarray, cell: float) -> UniformGrid:
    """Bucket ``points`` into a uniform grid of edge ``cell``.

    Parameters
    ----------
    points : numpy.ndarray
        ``(n, 3)`` positions.
    cell : float
        Cell edge, normally the query radius.

    Returns
    -------
    UniformGrid

    Notes
    -----
    A sort and a prefix sum, both vectorised — this is not the part worth moving
    to the GPU, and building it host-side keeps the shaders free of any
    data-dependent host round trip.
    """
    pts = np.ascontiguousarray(points, dtype=np.float64)
    origin = pts.min(axis=0) - float(cell) * 0.5
    inv_cell = 1.0 / float(cell)
    index = np.floor((pts - origin) * inv_cell).astype(np.int64)
    dims = np.maximum(index.max(axis=0) + 2, 1)
    np.clip(index, 0, dims - 1, out=index)

    flat = (index[:, 0] * dims[1] + index[:, 1]) * dims[2] + index[:, 2]
    order = np.argsort(flat, kind="stable").astype(np.uint32)
    counts = np.bincount(flat, minlength=int(dims.prod()))
    start = np.zeros(counts.size + 1, dtype=np.uint32)
    np.cumsum(counts, out=start[1:], dtype=np.uint32)
    return UniformGrid(
        origin=origin.astype(np.float32),
        dims=dims.astype(np.int32),
        inv_cell=float(inv_cell),
        start=start,
        order=order,
    )


def _vec4(points: np.ndarray, fourth) -> np.ndarray:
    """Pack ``(n, 3)`` positions and a scalar into ``(n, 4)`` float32.

    Parameters
    ----------
    points : numpy.ndarray
        ``(n, 3)`` positions.
    fourth : array_like or float
        What to put in ``w``.

    Returns
    -------
    numpy.ndarray
        ``(n, 4)`` float32, contiguous. WGSL storage arrays of ``vec3<f32>``
        have a 16-byte stride anyway, so the padding costs nothing and the
        fourth lane carries a per-element scalar for free.
    """
    out = np.empty((points.shape[0], 4), dtype=np.float32)
    out[:, :3] = points
    out[:, 3] = fourth
    return out


_MODULES: dict = {}
_PIPELINES: dict = {}


def _module(dev, shader: str):
    """A shader module, compiled once per process.

    Parameters
    ----------
    dev : object
        The wgpu device.
    shader : str
        WGSL source.

    Returns
    -------
    object
        The compiled module.

    Notes
    -----
    Compiling per call is not a small waste: the first version of this recompiled
    the distance-grid shader on every invocation and the GPU route came out
    **2.4× slower than the CPU one it was meant to replace** — a result that
    reads as "the kernel is bad" and is really "the measurement included the
    compiler". Cached, the same kernel is faster than the CPU route.
    """
    key = hash(shader)
    module = _MODULES.get(key)
    if module is None:
        module = dev.create_shader_module(code=shader)
        _MODULES[key] = module
    return module


class _Job:
    """One compute dispatch: buffers in, one buffer out, read back.

    Parameters
    ----------
    shader : str
        WGSL source, prelude already applied.
    entry_point : str
        Compute entry point name.
    """

    def __init__(self, shader: str, entry_point: str) -> None:
        import wgpu

        self._wgpu = wgpu
        self.device = device()
        self.module = _module(self.device, shader)
        self.entry_point = entry_point
        self._inputs: list = []
        self._output = None
        self._output_shape: tuple = ()
        self._output_dtype = np.float32

    def add_input(self, array: np.ndarray) -> "_Job":
        """Upload a read-only storage buffer.

        Parameters
        ----------
        array : numpy.ndarray
            Contiguous data; its dtype and layout must match the shader's.

        Returns
        -------
        _Job
        """
        wgpu = self._wgpu
        data = np.ascontiguousarray(array)
        self._inputs.append(
            self.device.create_buffer_with_data(
                data=data, usage=wgpu.BufferUsage.STORAGE
            )
        )
        return self

    def add_uniform(self, array: np.ndarray) -> "_Job":
        """Upload a uniform buffer.

        Parameters
        ----------
        array : numpy.ndarray
            Contiguous struct data, already padded to WGSL's alignment rules.

        Returns
        -------
        _Job
        """
        wgpu = self._wgpu
        data = np.ascontiguousarray(array)
        self._inputs.append(
            self.device.create_buffer_with_data(
                data=data, usage=wgpu.BufferUsage.UNIFORM
            )
        )
        return self

    def output(self, shape: tuple, dtype=np.float32) -> "_Job":
        """Declare the writable storage buffer the shader fills.

        Parameters
        ----------
        shape : tuple
            Shape of the result.
        dtype : numpy.dtype
            Element type.

        Returns
        -------
        _Job
        """
        wgpu = self._wgpu
        self._output_shape = shape
        self._output_dtype = dtype
        size = int(np.prod(shape)) * np.dtype(dtype).itemsize
        self._output = self.device.create_buffer(
            size=size,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
        )
        return self

    def run(self, work_items: int) -> np.ndarray:
        """Dispatch and read the output back.

        Parameters
        ----------
        work_items : int
            Number of invocations; rounded up to whole workgroups, so the shader
            must guard against an index past the end.

        Returns
        -------
        numpy.ndarray
            The output buffer, reshaped.
        """
        wgpu = self._wgpu
        entries = []
        layout_entries = []
        for slot, buffer in enumerate(self._inputs):
            is_uniform = bool(buffer.usage & wgpu.BufferUsage.UNIFORM)
            kind = (
                wgpu.BufferBindingType.uniform if is_uniform
                else wgpu.BufferBindingType.read_only_storage
            )
            layout_entries.append({
                "binding": slot,
                "visibility": wgpu.ShaderStage.COMPUTE,
                "buffer": {"type": kind},
            })
            entries.append({"binding": slot, "resource": {"buffer": buffer}})
        slot = len(self._inputs)
        layout_entries.append({
            "binding": slot,
            "visibility": wgpu.ShaderStage.COMPUTE,
            "buffer": {"type": wgpu.BufferBindingType.storage},
        })
        entries.append({"binding": slot, "resource": {"buffer": self._output}})

        # The layout and the pipeline depend only on the *shape* of the
        # bindings, never on the data, so both are cached with the module.
        key = (id(self.module), self.entry_point, tuple(
            (e["binding"], e["buffer"]["type"]) for e in layout_entries
        ))
        cached = _PIPELINES.get(key)
        if cached is None:
            bind_layout = self.device.create_bind_group_layout(entries=layout_entries)
            pipeline = self.device.create_compute_pipeline(
                layout=self.device.create_pipeline_layout(
                    bind_group_layouts=[bind_layout]
                ),
                compute={"module": self.module, "entry_point": self.entry_point},
            )
            cached = (bind_layout, pipeline)
            _PIPELINES[key] = cached
        bind_layout, pipeline = cached
        bind_group = self.device.create_bind_group(layout=bind_layout, entries=entries)

        encoder = self.device.create_command_encoder()
        pass_ = encoder.begin_compute_pass()
        pass_.set_pipeline(pipeline)
        pass_.set_bind_group(0, bind_group)
        pass_.dispatch_workgroups((int(work_items) + WORKGROUP - 1) // WORKGROUP)
        pass_.end()
        self.device.queue.submit([encoder.finish()])

        raw = self.device.queue.read_buffer(self._output)
        return np.frombuffer(raw, dtype=self._output_dtype).reshape(self._output_shape)


def shade_from_atoms(verts, atoms, atom_colors, sigmas, cutoff) -> Optional[tuple]:
    """Gaussian-weighted colour and density gradient per vertex, on the GPU.

    Parameters
    ----------
    verts : numpy.ndarray
        ``(n, 3)`` mesh vertices.
    atoms : numpy.ndarray
        ``(m, 3)`` atom positions.
    atom_colors : numpy.ndarray
        ``(m, 4)`` RGBA per atom.
    sigmas : numpy.ndarray
        ``(m,)`` Gaussian width per atom.
    cutoff : float
        Atoms beyond this contribute nothing.

    Returns
    -------
    tuple or None
        ``(colors, wsum, grad)`` as float64 arrays, or ``None`` when there is no
        device, the problem is too small to be worth a dispatch, or the dispatch
        failed. ``nearest`` is deliberately not returned: it is a global
        nearest-neighbour query, the caller already has a k-d tree for it, and it
        is only read where ``wsum`` is zero.

    Notes
    -----
    This is the kernel the CPU port made 15× slower — 750k vertex/atom pairs
    enumerated into arrays, then eight scatter-adds over them. On the GPU there
    are no pairs at all: each vertex accumulates its own sums in registers, which
    is why the shape that is bad for NumPy is the natural one here.
    """
    v = np.ascontiguousarray(verts, dtype=np.float64)
    a = np.ascontiguousarray(atoms, dtype=np.float64)
    if v.ndim != 2 or v.shape[1] != 3 or a.ndim != 2 or a.shape[1] != 3:
        return None
    if _declines(v.shape[0]) or v.shape[0] == 0 or a.shape[0] == 0:
        return None
    if not np.isfinite(cutoff) or cutoff <= 0.0:
        return None

    colors = np.ascontiguousarray(atom_colors, dtype=np.float32).reshape(-1, 4)
    sigma = np.ascontiguousarray(sigmas, dtype=np.float64).reshape(-1)
    grid = build_grid(a, float(cutoff))

    uniform = np.zeros(12, dtype=np.uint32)
    uniform[0:3] = grid.origin.view(np.uint32)
    uniform[3] = np.float32(grid.inv_cell).view(np.uint32)
    uniform[4:7] = grid.dims.astype(np.uint32)
    uniform[7] = np.uint32(v.shape[0])
    uniform[8] = np.float32(cutoff).view(np.uint32)

    try:
        job = (
            _Job(load_compute_wgsl("shade_atoms.wgsl"), "main")
            .add_input(_vec4(v, 0.0))
            .add_input(_vec4(a, sigma))
            .add_input(colors)
            .add_input(grid.start)
            .add_input(grid.order)
            .add_uniform(uniform)
            .output((v.shape[0], 8), np.float32)
        )
        packed = job.run(v.shape[0])
    except Exception:
        return None

    out = np.asarray(packed, dtype=np.float64)
    return out[:, 0:4].copy(), out[:, 7].copy(), out[:, 4:7].copy()


def occlusion_from_spheres(points, normals, centers, radii, max_distance, strength):
    """Hemispherical ambient occlusion per vertex, on the GPU.

    Parameters
    ----------
    points, normals : numpy.ndarray
        ``(n, 3)`` vertices and unit normals.
    centers : numpy.ndarray
        ``(m, 3)`` occluder centres.
    radii : numpy.ndarray
        ``(m,)`` occluder radii.
    max_distance : float
        Occluders further away than this are ignored.
    strength : float
        Scales the accumulated coverage before the exponential.

    Returns
    -------
    numpy.ndarray or None
        ``(n,)`` occlusion in ``[0, 1)``, or ``None`` when the GPU route is
        unavailable or not worth taking.
    """
    p = np.ascontiguousarray(points, dtype=np.float64)
    c = np.ascontiguousarray(centers, dtype=np.float64)
    if _declines(p.shape[0]) or p.shape[0] == 0 or c.shape[0] == 0:
        return None
    if not np.isfinite(max_distance) or max_distance <= 0.0:
        return None

    grid = build_grid(c, float(max_distance))
    uniform = np.zeros(12, dtype=np.uint32)
    uniform[0:3] = grid.origin.view(np.uint32)
    uniform[3] = np.float32(grid.inv_cell).view(np.uint32)
    uniform[4:7] = grid.dims.astype(np.uint32)
    uniform[7] = np.uint32(p.shape[0])
    uniform[8] = np.float32(max_distance).view(np.uint32)
    uniform[9] = np.float32(strength).view(np.uint32)

    try:
        job = (
            _Job(load_compute_wgsl("occlusion.wgsl"), "main")
            .add_input(_vec4(p, 0.0))
            .add_input(_vec4(np.ascontiguousarray(normals, dtype=np.float64), 0.0))
            .add_input(_vec4(c, np.ascontiguousarray(radii, dtype=np.float64).reshape(-1)))
            .add_input(grid.start)
            .add_input(grid.order)
            .add_uniform(uniform)
            .output((p.shape[0],), np.float32)
        )
        return np.asarray(job.run(p.shape[0]), dtype=np.float64)
    except Exception:
        return None


#: Cell edge for the distance grid's spatial index, in Angstrom.
#:
#: Larger cells mean fewer rings to reach the horizon but more spheres to test
#: per cell, and the trade has a clear optimum: measured over 4/6/8/12 Å against
#: two structures, 6 Å won both. 4 Å is more than twice as slow at a 16 Å
#: horizon, because the ring count is what dominates, not the sphere count.
DISTANCE_CELL = 6.0


def distance_to_spheres(points, radii, shape, origin, spacing, horizon):
    """Signed distance from each voxel centre to the nearest sphere surface.

    Parameters
    ----------
    points : numpy.ndarray
        ``(n, 3)`` sphere centres.
    radii : numpy.ndarray
        ``(n,)`` sphere radii.
    shape : tuple of int
        ``(nx, ny, nz)`` voxel counts.
    origin : numpy.ndarray
        World position of voxel ``(0, 0, 0)``.
    spacing : float
        Voxel edge length.
    horizon : float
        Distances beyond this are reported as exactly this. The caller applies
        the same clamp to its own route, so the two agree by construction.

    Returns
    -------
    numpy.ndarray or None
        ``(nx, ny, nz)`` float32 distances, or ``None`` when the GPU route is
        unavailable or not worth taking.

    Notes
    -----
    The ring bound is what makes this exact rather than merely close: after
    searching every cell at Chebyshev distance ``r``, no unsearched sphere can
    score below ``r * cell - r_max``, so the scan stops the moment the best
    candidate beats that. The horizon is what stops that bound from needing
    fifteen rings for a voxel in an empty corner — see the shader for why that
    made the first version slower than the CPU route it replaces.
    """
    p = np.ascontiguousarray(points, dtype=np.float64)
    r = np.ascontiguousarray(radii, dtype=np.float64).reshape(-1)
    count = int(np.prod(shape))
    if _declines(count) or p.shape[0] == 0 or count == 0:
        return None

    grid = build_grid(p, DISTANCE_CELL)
    info = np.zeros(12, dtype=np.uint32)
    info[0:3] = grid.origin.view(np.uint32)
    info[3] = np.float32(grid.inv_cell).view(np.uint32)
    info[4:7] = grid.dims.astype(np.uint32)
    info[7] = np.uint32(count)

    voxel = np.zeros(12, dtype=np.uint32)
    voxel[0:3] = np.asarray(origin, dtype=np.float32).view(np.uint32)
    voxel[3] = np.float32(spacing).view(np.uint32)
    voxel[4:7] = np.asarray(shape, dtype=np.uint32)
    voxel[7] = np.uint32(count)
    voxel[8] = np.float32(r.max()).view(np.uint32)
    voxel[9] = np.float32(DISTANCE_CELL).view(np.uint32)
    voxel[10] = np.uint32(int(np.ceil((horizon + r.max()) / DISTANCE_CELL)) + 1)
    voxel[11] = np.float32(horizon).view(np.uint32)

    try:
        job = (
            _Job(load_compute_wgsl("distance_grid.wgsl"), "main")
            .add_input(_vec4(p, r))
            .add_input(grid.start)
            .add_input(grid.order)
            .add_uniform(info)
            .add_uniform(voxel)
            .output((count,), np.float32)
        )
        return np.asarray(job.run(count)).reshape(shape)
    except Exception:
        return None


__all__ = [
    "BACKEND_ENV",
    "DISTANCE_CELL",
    "MIN_WORK_ITEMS",
    "backend",
    "distance_to_spheres",
    "UniformGrid",
    "available",
    "build_grid",
    "device",
    "load_compute_wgsl",
    "occlusion_from_spheres",
    "shade_from_atoms",
]
