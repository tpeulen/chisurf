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

#: Prelude for every shader that casts a ray: the BVH layout, its traversal, and
#: the two primitive intersections. Bindings 0-6 belong to it, so an entry point
#: that uses it starts its own at 7.
RAY_PRELUDE = "bvh.wgsl"

#: Threads per workgroup. 64 is the portable choice: it is a multiple of both
#: the 32-lane and 64-lane wave sizes in circulation, so no backend runs a
#: partly-empty wave.
WORKGROUP = 64

#: Below this many work items the dispatch is not worth its own setup — buffer
#: creation, submission and readback are a fixed cost of roughly a millisecond,
#: which is more than the NumPy route takes on a small mesh.
MIN_WORK_ITEMS = 20_000

#: The floor for the three **per-vertex shading** kernels: the colour gather,
#: the hemispherical occlusion and the cast shadows.
#:
#: :data:`MIN_WORK_ITEMS` is a general guess and it was badly wrong for these.
#: Measured on an M1 Pro, best of three, against their own NumPy routes (which
#: enumerate vertex/atom pairs, so they grow with the product while the kernel
#: grows with the vertices):
#:
#: ===========  =========  =========  =========
#: vertices     CPU        GPU        speed-up
#: ===========  =========  =========  =========
#: 250          15 ms      3.7 ms     4x
#: 1,000        42 ms      3.6 ms     12x
#: 5,000        201 ms     5.8 ms     35x
#: 20,000       1,242 ms   11.8 ms    105x
#: 40,000       3,328 ms   15.9 ms    210x
#: ===========  =========  =========  =========
#:
#: The GPU is flat -- it is dispatch-bound until tens of thousands of vertices --
#: so the break-even is around 100-250 and everything above it is a rout. At the
#: old floor of 20,000 a **cartoon of T4 lysozyme (19,908 vertices) missed the
#: GPU by 92 vertices and took 4.4 seconds instead of 0.08**.
#:
#: 512 rather than 250: the first dispatch in a process also compiles the
#: shader, which is ~950 ms once, and a floor at the exact break-even would pay
#: it for a case that gains a millisecond.
SHADING_MIN_ITEMS = 512

#: Environment override, for tests and for a machine whose driver misbehaves.
#: ``cpu`` disables every kernel here; ``gpu`` skips the size threshold so a
#: small case still dispatches, which is what makes a parity test meaningful.
BACKEND_ENV = "CHIMOL_COMPUTE"

class ShaderError(RuntimeError):
    """A WGSL shader failed to compile.

    Notes
    -----
    Never caught by the kernels here, on purpose. Everything else they can fail
    at -- no adapter, an allocation that will not fit -- is a legitimate reason
    to hand the work back to NumPy, and the ``except`` clauses do exactly that.
    A shader that does not compile is not that: it is a bug in code that was
    edited, and letting it become a quiet CPU fallback is how a broken shader
    survives a full test run. Two reserved-keyword collisions (`meta`, `active`)
    were found this way and would otherwise have been found by nobody.
    """


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


def _declines(work_items: int, minimum: int | None = None) -> bool:
    """Whether the GPU route should stand aside for this problem size.

    Parameters
    ----------
    work_items : int
        Number of invocations the dispatch would launch.
    minimum : int, optional
        Override :data:`MIN_WORK_ITEMS` for a kernel whose CPU route is unusually
        strong. The distance transform is the case: scipy's is compiled and
        separable, so it stays ahead until the grid is large.

    Returns
    -------
    bool
    """
    choice = backend()
    if choice == "cpu":
        return True
    if device() is None:
        return True
    floor = MIN_WORK_ITEMS if minimum is None else int(minimum)
    return choice != "gpu" and work_items < floor


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
        from .gpu import api as wgpu

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


def load_ray_wgsl(name: str) -> str:
    """Read a ray shader, prefixed with the BVH prelude.

    Parameters
    ----------
    name : str
        File name inside the ``wgsl`` directory.

    Returns
    -------
    str
    """
    return (WGSL_DIR / RAY_PRELUDE).read_text() + "\n" + (WGSL_DIR / name).read_text()


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
        try:
            module = dev.create_shader_module(code=shader)
        except Exception as failure:
            raise ShaderError(str(failure)) from failure
        _MODULES[key] = module
    return module


def shader_compiled(name: str) -> bool:
    """Whether a shader has already been compiled in this process.

    Parameters
    ----------
    name : str
        File name inside the ``wgsl`` directory.

    Returns
    -------
    bool
        False before the first dispatch that uses it, and after nothing else.

    Notes
    -----
    Only useful for telling a user that the wait they are about to have is a
    compile rather than the work -- which is worth saying, because the first
    dispatch of a process is the slowest thing this module does.
    """
    try:
        source = load_ray_wgsl(name) if name != COMPUTE_PRELUDE else load_compute_wgsl(name)
    except OSError:
        return False
    if hash(source) in _MODULES:
        return True
    return hash(load_compute_wgsl(name)) in _MODULES


class _Job:
    """One compute dispatch: buffers in, one buffer out, read back.

    Parameters
    ----------
    shader : str
        WGSL source, prelude already applied.
    entry_point : str
        Compute entry point name.

    Notes
    -----
    Bindings may be given explicitly, because the ray shaders share a prelude
    that fixes bindings 0-6 for the scene and the tree, and each entry point adds
    its own above that. :meth:`add_input` and :meth:`add_uniform` keep the simple
    sequential form for the kernels that do not.
    """

    def __init__(self, shader: str, entry_point: str) -> None:
        from .gpu import api as wgpu

        self._wgpu = wgpu
        self.device = device()
        self.module = _module(self.device, shader)
        self.entry_point = entry_point
        self._bound: list = []
        self._next_slot = 0
        self._output = None
        self._output_slot = -1
        self._skip_read = False
        self._output_shape: tuple = ()
        self._output_dtype = np.float32

    def bind(self, slot: int, array: np.ndarray, *, uniform: bool = False) -> "_Job":
        """Upload one buffer at an explicit binding slot.

        Parameters
        ----------
        slot : int
            Binding index, matching the shader.
        array : numpy.ndarray
            Contiguous data; its dtype and layout must match the shader's.
        uniform : bool, optional
            Whether this is a uniform rather than a read-only storage buffer.

        Returns
        -------
        _Job
        """
        wgpu = self._wgpu
        usage = wgpu.BufferUsage.UNIFORM if uniform else wgpu.BufferUsage.STORAGE
        # A zero-length storage array cannot be bound, and an empty scene is a
        # perfectly ordinary thing to trace -- one padding element keeps the
        # binding valid while the counts in the uniform keep the shader off it.
        data = np.ascontiguousarray(array)
        if data.size == 0:
            data = np.zeros((1,) + data.shape[1:], dtype=data.dtype)
        buffer = self.device.create_buffer_with_data(data=data, usage=usage)
        self._bound.append((int(slot), buffer, uniform))
        self._next_slot = max(self._next_slot, int(slot) + 1)
        return self

    def add_input(self, array: np.ndarray) -> "_Job":
        """Upload a read-only storage buffer at the next free slot.

        Parameters
        ----------
        array : numpy.ndarray
            Contiguous data.

        Returns
        -------
        _Job
        """
        return self.bind(self._next_slot, array)

    def add_uniform(self, array: np.ndarray) -> "_Job":
        """Upload a uniform buffer at the next free slot.

        Parameters
        ----------
        array : numpy.ndarray
            Contiguous struct data, already padded to WGSL's alignment rules.

        Returns
        -------
        _Job
        """
        return self.bind(self._next_slot, array, uniform=True)

    def output(self, shape: tuple, dtype=np.float32, slot: int | None = None) -> "_Job":
        """Declare the writable storage buffer the shader fills.

        Parameters
        ----------
        shape : tuple
            Shape of the result.
        dtype : numpy.dtype
            Element type.
        slot : int, optional
            Binding index; defaults to the next free slot.

        Returns
        -------
        _Job
        """
        wgpu = self._wgpu
        self._output_shape = shape
        self._output_dtype = dtype
        self._output_slot = self._next_slot if slot is None else int(slot)
        self._next_slot = max(self._next_slot, self._output_slot + 1)
        size = max(int(np.prod(shape)), 1) * np.dtype(dtype).itemsize
        self._output = self.device.create_buffer(
            size=size,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
        )
        return self

    def into(self, volume: "GpuVolume", slot: int) -> "_Job":
        """Write into an existing resident buffer and skip the readback.

        Parameters
        ----------
        volume : GpuVolume
            Destination; must be large enough for what the shader writes.
        slot : int
            Binding index of the shader's output.

        Returns
        -------
        _Job
        """
        self._output = volume.buffer
        self._output_slot = int(slot)
        self._next_slot = max(self._next_slot, int(slot) + 1)
        self._skip_read = True
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
        for slot, buffer, uniform in self._bound:
            kind = (
                wgpu.BufferBindingType.uniform if uniform
                else wgpu.BufferBindingType.read_only_storage
            )
            layout_entries.append({
                "binding": slot,
                "visibility": wgpu.ShaderStage.COMPUTE,
                "buffer": {"type": kind},
            })
            entries.append({"binding": slot, "resource": {"buffer": buffer}})
        layout_entries.append({
            "binding": self._output_slot,
            "visibility": wgpu.ShaderStage.COMPUTE,
            "buffer": {"type": wgpu.BufferBindingType.storage},
        })
        entries.append({
            "binding": self._output_slot, "resource": {"buffer": self._output}
        })

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

        if self._skip_read:
            return None
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
    if _declines(v.shape[0], SHADING_MIN_ITEMS) or v.shape[0] == 0 or a.shape[0] == 0:
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
    except ShaderError:
        raise
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
    if _declines(p.shape[0], SHADING_MIN_ITEMS) or p.shape[0] == 0 or c.shape[0] == 0:
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
    except ShaderError:
        raise
    except Exception:
        return None


#: Cell edge for the distance grid's spatial index, in Angstrom.
#:
#: Larger cells mean fewer rings to reach the horizon but more spheres to test
#: per cell, and the trade has a clear optimum: measured over 4/6/8/12 Å against
#: two structures, 6 Å won both. 4 Å is more than twice as slow at a 16 Å
#: horizon, because the ring count is what dominates, not the sphere count.
DISTANCE_CELL = 6.0


def distance_to_spheres(points, radii, shape, origin, spacing, horizon,
                        resident=False):
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
    resident : bool, optional
        Return a :class:`GpuVolume` instead of copying the grid back, so the
        next kernel in the chain can read it where it already is.

    Returns
    -------
    numpy.ndarray or GpuVolume or None
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
        )
        if resident:
            out = new_volume(shape)
            job.into(out, 5).run(count)
            return out
        job.output((count,), np.float32, slot=5)
        return np.asarray(job.run(count)).reshape(shape)
    except ShaderError:
        raise
    except Exception:
        return None



def directional_occlusion(points, normals, centers, radii, direction,
                          max_distance, softness, strength):
    """Shadowing of one key light, per vertex, on the GPU.

    Parameters
    ----------
    points, normals : numpy.ndarray
        ``(n, 3)`` vertices and unit normals.
    centers : numpy.ndarray
        ``(m, 3)`` occluder centres.
    radii : numpy.ndarray
        ``(m,)`` occluder radii.
    direction : numpy.ndarray
        Unit vector pointing **toward** the light.
    max_distance : float
        How far along the ray to look.
    softness : float
        Multiplies each occluder radius when deciding how near a graze counts.
    strength : float
        Scales the accumulated blockage before the exponential.

    Returns
    -------
    numpy.ndarray or None
        ``(n,)`` shadowing in ``[0, 1)``, or ``None`` when the GPU route is
        unavailable or not worth taking.
    """
    p = np.ascontiguousarray(points, dtype=np.float64)
    c = np.ascontiguousarray(centers, dtype=np.float64)
    r = np.ascontiguousarray(radii, dtype=np.float64).reshape(-1)
    if _declines(p.shape[0], SHADING_MIN_ITEMS) or p.shape[0] == 0 or c.shape[0] == 0:
        return None
    if not np.isfinite(max_distance) or max_distance <= 0.0:
        return None
    reach = float((r * softness).max())
    if reach <= 0.0:
        return None

    # The cell is *twice* the step, and that factor is the whole correctness
    # argument. A sphere claimed by step `s` sits up to one step further along
    # the ray and up to one reach off it, and the light is not axis-aligned -- so
    # its displacement from the sample point can be a full `step + reach` on
    # every axis at once. Only a cell at least that large keeps it inside the
    # sample's 3x3x3 neighbourhood. With cell = step this missed a handful of
    # occluders per frame: 20 vertices out of 40k, invisible in the mean and
    # 0.39 out of 1.0 on the vertices it hit.
    grid = build_grid(c, 2.0 * reach)
    info = np.zeros(12, dtype=np.uint32)
    info[0:3] = grid.origin.view(np.uint32)
    info[3] = np.float32(grid.inv_cell).view(np.uint32)
    info[4:7] = grid.dims.astype(np.uint32)
    info[7] = np.uint32(p.shape[0])

    light = np.asarray(direction, dtype=np.float64).reshape(3)
    ray = np.zeros(8, dtype=np.uint32)
    ray.view(np.float32)[0:3] = light
    ray.view(np.float32)[3] = np.float32(max_distance)
    ray.view(np.float32)[4] = np.float32(reach)
    ray[5] = np.uint32(int(np.ceil(max_distance / reach)))
    ray.view(np.float32)[6] = np.float32(softness)
    ray.view(np.float32)[7] = np.float32(strength)

    try:
        job = (
            _Job(load_compute_wgsl("shadow_rays.wgsl"), "main")
            .bind(0, _vec4(p, 0.0))
            .bind(1, _vec4(np.ascontiguousarray(normals, dtype=np.float64), 0.0))
            .bind(2, _vec4(c, r))
            .bind(3, grid.start)
            .bind(4, grid.order)
            .bind(5, info, uniform=True)
            .bind(6, ray, uniform=True)
            .output((p.shape[0],), np.float32, slot=7)
        )
        return np.asarray(job.run(p.shape[0]), dtype=np.float64)
    except ShaderError:
        raise
    except Exception:
        return None


#: Stands in for infinity in the distance transform, matching ``edt.wgsl``.
_EDT_BIG = 1.0e20

#: Voxels below which the distance transform stays on scipy. Its CPU route is
#: compiled and separable and therefore unusually strong: measured, the GPU is
#: 2x *slower* at 27k voxels and 12.9x faster at 2.1M, with the crossing well
#: above the module's usual threshold.
_EDT_MIN_VOXELS = 250_000


def distance_transform_edt(mask, resident=False):
    """Euclidean distance, in voxels, to the nearest zero voxel.

    Parameters
    ----------
    mask : numpy.ndarray or GpuVolume
        ``(nx, ny, nz)`` volume whose zeros are the seeds. A resident volume is
        read as a *seed field* already — zero where the transform measures from
        and :data:`_EDT_BIG` elsewhere — rather than as a mask, because that is
        the form the threshold kernel produces and re-deriving it would mean a
        round trip.
    resident : bool, optional
        Return the **squared** distances as a :class:`GpuVolume` instead of
        copying their root back. The root and the unit conversion are then one
        more pass rather than a host-side pass over the whole grid.

    Returns
    -------
    numpy.ndarray or GpuVolume or None
        Distances, or ``None`` when the GPU route is unavailable or not worth
        taking.

    Notes
    -----
    Three dispatches, one per axis, encoded into a single command buffer -- the
    passes are dependent, but a dependency inside one submission needs no host
    round trip and the driver orders them. Source and destination swap between
    axes because the transform cannot run in place: the parabola that wins at
    position ``q`` may be centred to the right of it.
    """
    from .gpu import api as wgpu

    if isinstance(mask, GpuVolume):
        dims = mask.shape
    else:
        volume = np.ascontiguousarray(mask)
        if volume.ndim != 3:
            return None
        dims = volume.shape
    count = int(np.prod(dims))
    if _declines(count, _EDT_MIN_VOXELS) or count == 0:
        return None

    dev = device()
    usage = (wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC
             | wgpu.BufferUsage.COPY_DST)
    try:
        if isinstance(mask, GpuVolume):
            first = mask.buffer
        else:
            seed = np.where(
                volume != 0, np.float32(_EDT_BIG), np.float32(0.0)
            ).astype(np.float32)
            first = dev.create_buffer_with_data(data=seed.reshape(-1), usage=usage)
        buffers = [first, dev.create_buffer(size=count * 4, usage=usage)]
        # One scratch pair, sized for the longest line any axis will ask for.
        widest = max(dims)
        lines = max(count // max(min(dims), 1), 1)
        slots = lines * (widest + 1)
        hull = dev.create_buffer(size=slots * 4, usage=wgpu.BufferUsage.STORAGE)
        boundary = dev.create_buffer(size=slots * 4, usage=wgpu.BufferUsage.STORAGE)

        module = _module(dev, load_compute_wgsl("edt.wgsl"))
        layout = dev.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE,
             "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
            {"binding": 1, "visibility": wgpu.ShaderStage.COMPUTE,
             "buffer": {"type": wgpu.BufferBindingType.storage}},
            {"binding": 2, "visibility": wgpu.ShaderStage.COMPUTE,
             "buffer": {"type": wgpu.BufferBindingType.storage}},
            {"binding": 3, "visibility": wgpu.ShaderStage.COMPUTE,
             "buffer": {"type": wgpu.BufferBindingType.uniform}},
            {"binding": 4, "visibility": wgpu.ShaderStage.COMPUTE,
             "buffer": {"type": wgpu.BufferBindingType.storage}},
        ])
        key = (id(module), "edt")
        pipeline = _PIPELINES.get(key)
        if pipeline is None:
            pipeline = dev.create_compute_pipeline(
                layout=dev.create_pipeline_layout(bind_group_layouts=[layout]),
                compute={"module": module, "entry_point": "main"},
            )
            _PIPELINES[key] = pipeline

        encoder = dev.create_command_encoder()
        for axis in range(3):
            length = int(dims[axis])
            axis_lines = count // max(length, 1)
            info = np.zeros(8, dtype=np.uint32)
            info[0:3] = np.asarray(dims, dtype=np.uint32)
            info[3] = np.uint32(axis)
            info[4] = np.uint32(length)
            info[5] = np.uint32(axis_lines)
            uniform = dev.create_buffer_with_data(
                data=info, usage=wgpu.BufferUsage.UNIFORM
            )
            group = dev.create_bind_group(layout=layout, entries=[
                {"binding": 0, "resource": {"buffer": buffers[axis % 2]}},
                {"binding": 1, "resource": {"buffer": hull}},
                {"binding": 2, "resource": {"buffer": boundary}},
                {"binding": 3, "resource": {"buffer": uniform}},
                {"binding": 4, "resource": {"buffer": buffers[(axis + 1) % 2]}},
            ])
            pass_ = encoder.begin_compute_pass()
            pass_.set_pipeline(pipeline)
            pass_.set_bind_group(0, group)
            pass_.dispatch_workgroups(
                (axis_lines + WORKGROUP - 1) // WORKGROUP
            )
            pass_.end()
        dev.queue.submit([encoder.finish()])

        if resident:
            return GpuVolume(buffers[3 % 2], dims)
        raw = dev.queue.read_buffer(buffers[3 % 2])
    except ShaderError:
        raise
    except Exception:
        return None
    squared = np.frombuffer(raw, dtype=np.float32).reshape(dims)
    return np.sqrt(squared)


#: Cells below which finding the crossings stays in NumPy. Eight shifted
#: comparisons over a small grid are already fast, and a dispatch plus two
#: readbacks is about a millisecond.
_MC_MIN_CELLS = 200_000


def marching_cubes_active(grid, level):
    """Indices of the cells the isosurface crosses, sorted.

    Parameters
    ----------
    grid : numpy.ndarray or GpuVolume
        ``(nx, ny, nz)`` scalar field.
    level : float
        Iso value; a corner counts as inside when its value is ``< level``.

    Returns
    -------
    tuple of numpy.ndarray or None
        ``(cells, cases)`` — flat indices into the ``(nx-1, ny-1, nz-1)`` cell
        array, ascending, and the corner-sign case of each. ``None`` when the GPU
        route is unavailable, not worth taking, or the surface turned out to
        cross more cells than the output was sized for.

        The case travels with the cell so the host never has to read the grid
        back to recover it, which is what makes the resident chain worth having.

    Notes
    -----
    **Not currently called.** It is correct, it is tested, and end to end it is
    *slower* than the NumPy pass it would replace: 132 ms against 114 ms for a
    128³ surface build, because the 8 MB grid has to be uploaded for it while
    eight shifted comparisons in NumPy are already fast, and because the host
    then has to recompute the case for the surviving cells that the full NumPy
    pass produced for free.

    It is kept because the *reason* it loses is one round trip, not the kernel.
    The distance grid and the distance transform both already run on the GPU, so
    the grid is produced there, read back, and uploaded again twice over. Chain
    those three with the grid resident and this becomes free rather than
    negative — that is the shape of the win, and this is its groundwork.

    Sorted on return because the compaction is an ``atomicAdd`` and therefore
    arbitrary in order. The mesh would be identical either way -- the triangles
    are the same set -- but the *vertex numbering* would change between runs, and
    a mesh that cannot be compared to a stored one is much less useful than one
    that can.

    Two sizes matter and both were got wrong first. The output buffer is sized to
    a fraction of the cell count, not to it: a surface crosses a few per cent of
    a volume, and allocating one slot per cell made this 8 MB. And only the
    *used* prefix is read back, which needs the counter read first -- reading the
    whole buffer cost more than the NumPy pass the dispatch replaces.
    """
    from .gpu import api as wgpu

    resident = isinstance(grid, GpuVolume)
    shape = grid.shape if resident else np.asarray(grid).shape
    if len(shape) != 3 or min(shape) < 2:
        return None
    cells_shape = tuple(n - 1 for n in shape)
    total = int(np.prod(cells_shape))
    if _declines(total, _MC_MIN_CELLS) or total == 0:
        return None

    dev = device()
    # A closed surface through a volume crosses O(n^2) of its O(n^3) cells, so a
    # quarter is generous -- but "generous" is a guess about the field, and a
    # porous one at coarse spacing beats it. Overflow is detected and retried at
    # the exact size the counter reported rather than dropped, because a
    # truncated surface is a hole nobody would notice.
    capacity = min(total, max(total // 4, 4096))
    for _ in range(2):
        found, cells = _scan_cells(dev, grid, resident, shape, cells_shape, level,
                                   total, capacity)
        if found is None:
            return None
        if found <= capacity:
            return cells
        capacity = min(total, found)
    return None


def _scan_cells(dev, grid, resident, shape, cells, level, total, capacity):
    """One marching-cubes scan dispatch.

    Parameters
    ----------
    dev : object
        The wgpu device.
    grid : numpy.ndarray or GpuVolume
        The field.
    resident : bool
        Whether ``grid`` is already on the device.
    shape : tuple of int
        Voxel counts.
    cells : tuple of int
        Cell counts, one fewer per axis.
    level : float
        Iso value.
    total : int
        ``prod(cells)``.
    capacity : int
        Crossings the output is sized for.

    Returns
    -------
    tuple
        ``(found, result)``. ``found`` is the number of crossings the shader
        counted, which may exceed ``capacity``; ``result`` is ``None`` in that
        case and the ``(cells, cases)`` pair otherwise. ``(None, None)`` on
        failure.
    """
    from .gpu import api as wgpu

    try:
        info = np.zeros(8, dtype=np.uint32)
        info[0:3] = np.asarray(shape, dtype=np.uint32)
        info.view(np.float32)[3] = np.float32(level)
        info[4:7] = np.asarray(cells, dtype=np.uint32)
        info[7] = np.uint32(capacity)

        if resident:
            grid_buffer = grid.buffer
        else:
            field = np.ascontiguousarray(grid, dtype=np.float32)
            grid_buffer = dev.create_buffer_with_data(
                data=field.reshape(-1), usage=wgpu.BufferUsage.STORAGE
            )
        info_buffer = dev.create_buffer_with_data(
            data=info, usage=wgpu.BufferUsage.UNIFORM
        )
        out_buffer = dev.create_buffer(
            size=(2 * capacity + 1) * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
        )

        module = _module(dev, load_compute_wgsl("mc_active.wgsl"))
        layout = dev.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE,
             "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
            {"binding": 1, "visibility": wgpu.ShaderStage.COMPUTE,
             "buffer": {"type": wgpu.BufferBindingType.uniform}},
            {"binding": 2, "visibility": wgpu.ShaderStage.COMPUTE,
             "buffer": {"type": wgpu.BufferBindingType.storage}},
        ])
        key = (id(module), "mc_active")
        pipeline = _PIPELINES.get(key)
        if pipeline is None:
            pipeline = dev.create_compute_pipeline(
                layout=dev.create_pipeline_layout(bind_group_layouts=[layout]),
                compute={"module": module, "entry_point": "main"},
            )
            _PIPELINES[key] = pipeline
        group = dev.create_bind_group(layout=layout, entries=[
            {"binding": 0, "resource": {"buffer": grid_buffer}},
            {"binding": 1, "resource": {"buffer": info_buffer}},
            {"binding": 2, "resource": {"buffer": out_buffer}},
        ])

        encoder = dev.create_command_encoder()
        pass_ = encoder.begin_compute_pass()
        pass_.set_pipeline(pipeline)
        pass_.set_bind_group(0, group)
        pass_.dispatch_workgroups((total + WORKGROUP - 1) // WORKGROUP)
        pass_.end()
        dev.queue.submit([encoder.finish()])

        found = int(np.frombuffer(
            dev.queue.read_buffer(out_buffer, 0, 4), dtype=np.uint32
        )[0])
        if found == 0:
            return 0, (np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64))
        if found > capacity:
            return found, None
        raw = dev.queue.read_buffer(out_buffer, 4, found * 8)
    except ShaderError:
        raise
    except Exception:
        return None, None
    pairs = np.frombuffer(raw, dtype=np.uint32).reshape(-1, 2).astype(np.int64)
    order = np.argsort(pairs[:, 0], kind="stable")
    return found, (pairs[order, 0].copy(), pairs[order, 1].copy())


# --------------------------------------------------------------------------- #
# Volumes that stay on the device
# --------------------------------------------------------------------------- #
class GpuVolume:
    """A scalar grid living in a GPU buffer, with its shape.

    Parameters
    ----------
    buffer : object
        A wgpu buffer holding ``prod(shape)`` float32 values in C order.
    shape : tuple of int
        ``(nx, ny, nz)``.

    Notes
    -----
    The surface pipeline is distance grid → threshold → distance transform →
    marching cubes, and each of those already ran on the GPU while the *grid*
    made the round trip between every pair: 8 MB back, 8 MB up, twice over. That
    transport is why the marching-cubes scan measured *slower* than the NumPy
    pass it replaced — the kernel was fine and the transfers were not. Passing
    this instead of an array is what removes them.

    :meth:`read` is the one place a volume comes back, and callers should treat
    it as expensive.
    """

    def __init__(self, buffer, shape) -> None:
        self.buffer = buffer
        self.shape = tuple(int(n) for n in shape)

    @property
    def count(self) -> int:
        """Number of voxels."""
        return int(np.prod(self.shape))

    def read(self) -> np.ndarray:
        """Copy the volume back to the host.

        Returns
        -------
        numpy.ndarray
            ``shape``-shaped float32.
        """
        raw = device().queue.read_buffer(self.buffer)
        return np.frombuffer(raw, dtype=np.float32).reshape(self.shape)


def _volume_usage():
    """Buffer usage flags a resident volume needs."""
    from .gpu import api as wgpu

    return (wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC
            | wgpu.BufferUsage.COPY_DST)


def new_volume(shape) -> GpuVolume:
    """Allocate an uninitialised resident volume.

    Parameters
    ----------
    shape : tuple of int
        ``(nx, ny, nz)``.

    Returns
    -------
    GpuVolume
    """
    count = int(np.prod(shape))
    return GpuVolume(
        device().create_buffer(size=max(count, 1) * 4, usage=_volume_usage()),
        shape,
    )


def upload_volume(array) -> GpuVolume:
    """Put a grid on the device.

    Parameters
    ----------
    array : numpy.ndarray
        ``(nx, ny, nz)`` scalar field.

    Returns
    -------
    GpuVolume
    """
    data = np.ascontiguousarray(array, dtype=np.float32)
    return GpuVolume(
        device().create_buffer_with_data(
            data=data.reshape(-1), usage=_volume_usage()
        ),
        data.shape,
    )


def as_volume(grid) -> GpuVolume:
    """Return ``grid`` as a resident volume, uploading only if it is an array.

    Parameters
    ----------
    grid : GpuVolume or numpy.ndarray

    Returns
    -------
    GpuVolume
    """
    return grid if isinstance(grid, GpuVolume) else upload_volume(grid)


def _volume_op(entry: str, volume: GpuVolume, params) -> GpuVolume:
    """Run one whole-volume kernel from ``volume_ops.wgsl``.

    Parameters
    ----------
    entry : str
        Entry point name.
    volume : GpuVolume
        Input.
    params : numpy.ndarray
        The eight-word ``VolumeInfo`` uniform.

    Returns
    -------
    GpuVolume
        A new volume; the input is left alone.
    """
    from .gpu import api as wgpu

    dev = device()
    out = new_volume(volume.shape)
    module = _module(dev, (WGSL_DIR / "volume_ops.wgsl").read_text())
    layout = dev.create_bind_group_layout(entries=[
        {"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE,
         "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
        {"binding": 1, "visibility": wgpu.ShaderStage.COMPUTE,
         "buffer": {"type": wgpu.BufferBindingType.uniform}},
        {"binding": 2, "visibility": wgpu.ShaderStage.COMPUTE,
         "buffer": {"type": wgpu.BufferBindingType.storage}},
    ])
    key = (id(module), entry)
    pipeline = _PIPELINES.get(key)
    if pipeline is None:
        pipeline = dev.create_compute_pipeline(
            layout=dev.create_pipeline_layout(bind_group_layouts=[layout]),
            compute={"module": module, "entry_point": entry},
        )
        _PIPELINES[key] = pipeline
    uniform = dev.create_buffer_with_data(data=params, usage=wgpu.BufferUsage.UNIFORM)
    group = dev.create_bind_group(layout=layout, entries=[
        {"binding": 0, "resource": {"buffer": volume.buffer}},
        {"binding": 1, "resource": {"buffer": uniform}},
        {"binding": 2, "resource": {"buffer": out.buffer}},
    ])
    encoder = dev.create_command_encoder()
    pass_ = encoder.begin_compute_pass()
    pass_.set_pipeline(pipeline)
    pass_.set_bind_group(0, group)
    pass_.dispatch_workgroups((volume.count + WORKGROUP - 1) // WORKGROUP)
    pass_.end()
    dev.queue.submit([encoder.finish()])
    return out


def threshold_volume(volume: GpuVolume, level, low, high) -> GpuVolume:
    """``low`` where the volume is below ``level``, ``high`` elsewhere.

    Parameters
    ----------
    volume : GpuVolume
        Input.
    level : float
        Comparison threshold.
    low, high : float
        Output values.

    Returns
    -------
    GpuVolume
    """
    params = np.zeros(8, dtype=np.uint32)
    params[0] = np.uint32(volume.count)
    params.view(np.float32)[1] = np.float32(level)
    params.view(np.float32)[2] = np.float32(low)
    params.view(np.float32)[3] = np.float32(high)
    return _volume_op("threshold", volume, params)


def scale_volume(volume: GpuVolume, factor, offset=0.0) -> GpuVolume:
    """``volume * factor + offset``.

    Parameters
    ----------
    volume : GpuVolume
        Input.
    factor, offset : float
        Affine coefficients.

    Returns
    -------
    GpuVolume
    """
    params = np.zeros(8, dtype=np.uint32)
    params[0] = np.uint32(volume.count)
    params.view(np.float32)[4] = np.float32(factor)
    params.view(np.float32)[5] = np.float32(offset)
    return _volume_op("scale", volume, params)


def root_scale_volume(volume: GpuVolume, factor, offset=0.0) -> GpuVolume:
    """``sqrt(volume) * factor + offset``, in one pass.

    Parameters
    ----------
    volume : GpuVolume
        Squared distances, as the transform produces them.
    factor, offset : float
        Affine coefficients applied after the root.

    Returns
    -------
    GpuVolume
    """
    params = np.zeros(8, dtype=np.uint32)
    params[0] = np.uint32(volume.count)
    params.view(np.float32)[4] = np.float32(factor)
    params.view(np.float32)[5] = np.float32(offset)
    return _volume_op("root_scale", volume, params)


def isosurface_vertices(volume: GpuVolume, edge_ids, level):
    """Position and gradient of each welded marching-cubes vertex.

    Parameters
    ----------
    volume : GpuVolume
        The scalar field the surface is extracted from.
    edge_ids : numpy.ndarray
        One grid-edge id per vertex, as ``axis * nx*ny*nz + flat lower node``.
    level : float
        Iso value.

    Returns
    -------
    tuple of numpy.ndarray or None
        ``(positions, gradients)`` in grid-index units, or ``None`` without a
        device.

    Notes
    -----
    This is what replaces ``numpy.gradient`` over the whole volume followed by a
    trilinear sample at the vertices — 31 ms of the 107 a 128³ marching cubes
    took, spent building three 8 MB arrays to read a few tens of thousands of
    values out of. The gradient is computed only where a vertex actually is.
    """
    if device() is None:
        return None
    ids = np.ascontiguousarray(edge_ids, dtype=np.uint32).reshape(-1)
    if ids.size == 0:
        return np.zeros((0, 3), dtype=np.float64), np.zeros((0, 3), dtype=np.float64)

    info = np.zeros(8, dtype=np.uint32)
    info[0:3] = np.asarray(volume.shape, dtype=np.uint32)
    info.view(np.float32)[3] = np.float32(level)
    info[4] = np.uint32(ids.size)
    try:
        job = _Job(load_compute_wgsl("mc_vertices.wgsl"), "main")
        job._bound.append((0, volume.buffer, False))
        job._next_slot = 1
        packed = (
            job.bind(1, ids)
            .bind(2, info, uniform=True)
            .output((ids.size, 8), np.float32, slot=3)
            .run(ids.size)
        )
    except ShaderError:
        raise
    except Exception:
        return None
    out = np.asarray(packed, dtype=np.float64)
    return out[:, 0:3].copy(), out[:, 4:7].copy()


# --------------------------------------------------------------------------- #
# Ray casting
# --------------------------------------------------------------------------- #
def _pack_triangles(tri_vertices) -> np.ndarray:
    """Flatten ``(T, 3, 3)`` corners into the ``(3T, 4)`` the shader indexes.

    Parameters
    ----------
    tri_vertices : numpy.ndarray
        ``(T, 3, 3)`` triangle corners.

    Returns
    -------
    numpy.ndarray
        ``(3T, 4)`` float32; ``w`` is unused padding, because a WGSL storage
        array of ``vec3<f32>`` has a 16-byte stride anyway.
    """
    tri = np.ascontiguousarray(tri_vertices, dtype=np.float64).reshape(-1, 3)
    out = np.zeros((tri.shape[0], 4), dtype=np.float32)
    out[:, :3] = tri
    return out


class RayScene:
    """A scene uploaded once and cast against many times.

    Parameters
    ----------
    centers : numpy.ndarray
        ``(S, 3)`` sphere centres.
    radii : numpy.ndarray
        ``(S,)`` sphere radii.
    tri_vertices : numpy.ndarray
        ``(T, 3, 3)`` triangle corners.
    tree : tuple
        The BVH, as :func:`chimol.renderer.bvh.build_bvh` returns it.

    Notes
    -----
    Holding the packed arrays rather than re-deriving them per dispatch is what
    lets the tracer and the traversal probe share one upload, and what keeps a
    progressive render from re-uploading the geometry per tile.
    """

    def __init__(self, centers, radii, tri_vertices, tree) -> None:
        node_min, node_max, node_left, node_start, node_count, prim_index = tree
        self.n_spheres = int(np.asarray(radii).reshape(-1).shape[0])
        self.n_prims = int(prim_index.shape[0])

        self.spheres = _vec4(
            np.asarray(centers, dtype=np.float64).reshape(-1, 3),
            np.asarray(radii, dtype=np.float64).reshape(-1),
        )
        self.tri_verts = _pack_triangles(tri_vertices)
        self.node_lo = np.zeros((node_min.shape[0], 4), dtype=np.float32)
        self.node_lo[:, :3] = node_min
        self.node_hi = np.zeros((node_max.shape[0], 4), dtype=np.float32)
        self.node_hi[:, :3] = node_max
        self.node_meta = np.zeros((node_left.shape[0], 4), dtype=np.int32)
        self.node_meta[:, 0] = node_left
        self.node_meta[:, 1] = node_start
        self.node_meta[:, 2] = node_count
        self.prim_index = prim_index.astype(np.uint32)

    def info(self, work_items: int, n_lights: int) -> np.ndarray:
        """The ``SceneInfo`` uniform for one dispatch.

        Parameters
        ----------
        work_items : int
            Invocations the dispatch will launch.
        n_lights : int
            Number of light directions bound.

        Returns
        -------
        numpy.ndarray
            Four ``uint32``.
        """
        return np.array(
            [self.n_spheres, self.n_prims, int(work_items), int(n_lights)],
            dtype=np.uint32,
        )

    def bind_into(self, job: "_Job", work_items: int, n_lights: int) -> "_Job":
        """Bind the scene and the tree at the prelude's fixed slots 0-6.

        Parameters
        ----------
        job : _Job
            The dispatch to bind into.
        work_items : int
            Invocations the dispatch will launch.
        n_lights : int
            Number of light directions bound.

        Returns
        -------
        _Job
        """
        return (
            job.bind(0, self.spheres)
            .bind(1, self.tri_verts)
            .bind(2, self.node_lo)
            .bind(3, self.node_hi)
            .bind(4, self.node_meta)
            .bind(5, self.prim_index)
            .bind(6, self.info(work_items, n_lights), uniform=True)
        )


def closest_hit(scene: RayScene, origins, directions, t_min=1e-6, skip=-1):
    """Nearest primitive each ray meets, through the shader the tracer uses.

    Parameters
    ----------
    scene : RayScene
        The uploaded scene and tree.
    origins : array_like
        ``(n, 3)`` ray origins.
    directions : array_like
        ``(n, 3)`` unit directions.
    t_min : float or array_like, optional
        Hits at or before this are ignored.
    skip : int or array_like, optional
        One primitive per ray to exclude, or ``-1``.

    Returns
    -------
    tuple of numpy.ndarray or None
        ``(t, prim)``; ``t`` is ``inf`` and ``prim`` is ``-1`` where nothing was
        met. ``None`` when there is no device.

    Notes
    -----
    This exists so the traversal can be checked against an exhaustive search
    directly rather than only through a rendered image — and because it shares
    ``closest_hit`` with the tracer through the prelude, checking it checks the
    real thing rather than a copy.
    """
    if device() is None:
        return None
    o = np.ascontiguousarray(origins, dtype=np.float64).reshape(-1, 3)
    d = np.ascontiguousarray(directions, dtype=np.float64).reshape(-1, 3)
    count = o.shape[0]
    if count == 0:
        return np.zeros(0), np.zeros(0, dtype=np.int64)

    job = _Job(load_ray_wgsl("bvh_probe.wgsl"), "main")
    scene.bind_into(job, count, 1)
    packed = (
        job.bind(7, _vec4(o, t_min))
        .bind(8, _vec4(d, skip))
        .output((count, 2), np.float32, slot=9)
        .run(count)
    )
    distance = packed[:, 0].astype(np.float64)
    prim = np.rint(packed[:, 1]).astype(np.int64)
    distance[prim < 0] = np.inf
    return distance, prim


#: Field order of the ``TraceInfo`` uniform, as 4-byte words. Written out rather
#: than derived, because WGSL's alignment rules put ``vec3`` on a 16-byte
#: boundary and a silently mismatched offset here shows up as a plausible but
#: wrong picture rather than as an error.
_TRACE_WORDS = 36


def raytrace(scene: RayScene, camera, lights, sphere_colors, tri_normals,
             tri_colors, settings):
    """Render the scene with the compute tracer.

    Parameters
    ----------
    scene : RayScene
        The uploaded scene and tree.
    camera : object
        Anything with ``origin``, ``forward``, ``up`` and ``fov_degrees``.
    lights : numpy.ndarray
        ``(L, 3)`` unit directions toward each light.
    sphere_colors : numpy.ndarray
        ``(S, 4)`` RGB plus alpha per sphere.
    tri_normals : numpy.ndarray
        ``(T, 3, 3)`` per-vertex normals.
    tri_colors : numpy.ndarray
        ``(T, 4)`` RGB plus alpha per triangle.
    settings : dict
        The shading and framing parameters; see the shader's ``TraceInfo``.

    Returns
    -------
    numpy.ndarray or None
        ``(height, width, 4)`` float32 — linear RGB and a hit mask — or ``None``
        when there is no device.
    """
    if device() is None:
        return None
    width = int(settings["width"])
    height = int(settings["height"])
    pixels = width * height
    if pixels == 0:
        return None

    light = np.ascontiguousarray(lights, dtype=np.float64).reshape(-1, 3)
    words = np.zeros(_TRACE_WORDS, dtype=np.uint32)
    as_float = words.view(np.float32)
    as_float[0:3] = np.asarray(camera.origin, dtype=np.float32)
    as_float[3] = np.radians(float(camera.fov_degrees))
    as_float[4:7] = np.asarray(camera.forward, dtype=np.float32)
    words[7] = np.uint32(max(int(settings["ssaa"]), 1))
    as_float[8:11] = np.asarray(camera.up, dtype=np.float32)
    words[11] = np.uint32(max(int(settings["max_layers"]), 1))
    as_float[12:15] = np.asarray(settings["background"], dtype=np.float32)
    as_float[15] = settings["ambient"]
    words[16] = np.uint32(width)
    words[17] = np.uint32(height)
    as_float[18] = settings["diffuse"]
    as_float[19] = settings["specular"]
    as_float[20] = settings["shininess"]
    as_float[21] = settings["direct_specular"]
    as_float[22] = settings["direct_specular_power"]
    as_float[23] = settings["reflect_power"]
    as_float[24] = settings["direct"]
    as_float[25] = settings["direct_power"]
    as_float[26] = settings["legacy"]
    as_float[27] = settings["shadow_fudge"]
    words[28] = np.uint32(bool(settings["shadow_enabled"]))
    words[29] = np.uint32(bool(settings["depth_cue_enabled"]))
    as_float[30] = settings["shadow_decay_factor"]
    as_float[31] = settings["shadow_decay_range"]
    as_float[32] = settings["fog_start"]
    as_float[33] = settings["fog_intensity"]
    as_float[34] = settings["fog_front"]
    as_float[35] = settings["fog_inv_range"]

    job = _Job(load_ray_wgsl("raytrace.wgsl"), "main")
    scene.bind_into(job, pixels, light.shape[0])
    out = (
        job.bind(7, np.ascontiguousarray(sphere_colors, dtype=np.float32).reshape(-1, 4))
        .bind(8, _pack_triangles(tri_normals))
        .bind(9, np.ascontiguousarray(tri_colors, dtype=np.float32).reshape(-1, 4))
        .bind(10, _vec4(light, 0.0))
        .bind(11, words, uniform=True)
        .output((pixels, 4), np.float32, slot=12)
        .run(pixels)
    )
    return np.asarray(out).reshape(height, width, 4)


__all__ = [
    "BACKEND_ENV",
    "GpuVolume",
    "as_volume",
    "isosurface_vertices",
    "new_volume",
    "root_scale_volume",
    "scale_volume",
    "threshold_volume",
    "upload_volume",
    "DISTANCE_CELL",
    "MIN_WORK_ITEMS",
    "SHADING_MIN_ITEMS",
    "RayScene",
    "backend",
    "closest_hit",
    "distance_to_spheres",
    "distance_transform_edt",
    "load_ray_wgsl",
    "marching_cubes_active",
    "raytrace",
    "shader_compiled",
    "UniformGrid",
    "available",
    "build_grid",
    "device",
    "directional_occlusion",
    "load_compute_wgsl",
    "occlusion_from_spheres",
    "shade_from_atoms",
]
