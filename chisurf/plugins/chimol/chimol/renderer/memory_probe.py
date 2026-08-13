"""Find the blocks of memory a running chimol holds, in RAM and in VRAM.

Why by reflection
-----------------
The obvious design is a registry: every place that allocates a buffer also
records it. That design is only correct while *every* place remembers, and the
allocations are spread across the backend, the compute passes, the chrome
texture and the atlas -- so the registry would be wrong the first time somebody
added a buffer without it, and wrong silently, which is the worst way for an
inspector to be wrong.

So this walks the live object graph instead and reports what it *finds*. The
result is honest about its own limits: it can miss a buffer nothing holds a
Python reference to, and it says so rather than presenting a total as complete.

RAM and VRAM are not symmetrical
--------------------------------
A host array is memory Python can already address, so :class:`ArraySource`
slices it and costs nothing. A GPU buffer is not addressable at all: reading it
means asking the graphics API to copy it back across the bus, which costs real
time and requires the buffer to have been created with ``COPY_SRC`` usage. A
buffer without that usage is *listed* -- its size is the interesting number
either way -- and reads from it return zeros with :attr:`GpuBufferSource.error`
set, rather than raising into the middle of a repaint.

The consumer is :class:`~chimol.renderer.ui.memory_editor.MemoryEditor`, which
knows nothing about any of this: it asks a source for its size and its bytes.
"""
from __future__ import annotations

from collections.abc import Iterator

__all__ = [
    "ArraySource",
    "GpuBufferSource",
    "MemoryReport",
    "collect_sources",
    "report",
]

#: How deep the object walk goes. Four levels reaches a backend's buffers and
#: a scene's arrays; deeper mostly finds the same objects by longer paths and
#: costs time on every open of the inspector.
_MAX_DEPTH = 4

#: Attribute names never followed. ``device`` and ``adapter`` reach the whole
#: wgpu object graph, which is large, cyclic, and none of it is chimol's
#: memory; the parent/back-references are how a walk of a scene ends up in the
#: application.
_SKIP = frozenset(
    {
        "adapter",
        "app",
        "device",
        "gui",
        "main_window",
        "parent",
        "queue",
        "session",
        "window",
    }
)


class ArraySource:
    """A NumPy array (or any buffer-protocol object) as inspectable memory.

    Parameters
    ----------
    array : numpy.ndarray
    name : str
        Where it was found, e.g. ``"scene.objects[0].xyz"``. The path is the
        useful half -- "a 24 MB float32 array" is not actionable, "the instance
        buffer of the object you just loaded" is.
    """

    #: What kind of memory this is, for a picker that groups them.
    kind = "RAM"

    def __init__(self, array, name: str) -> None:
        self._array = array
        self.name = str(name)
        self.base_address = 0
        self.error = ""
        self.detail = f"{getattr(array, 'dtype', '?')} {getattr(array, 'shape', '')}"

    def size(self) -> int:
        """Bytes the array occupies."""
        return int(getattr(self._array, "nbytes", 0) or 0)

    def read(self, offset: int, length: int) -> bytes:
        """Return the bytes in ``[offset, offset + length)``."""
        raw = memoryview(self._array).cast("B") if self._is_contiguous() else None
        if raw is None:
            # A view with gaps has no single byte range to show. Copying it
            # would show bytes that are not what the GPU would read, so the
            # copy is made explicit and the array is reported as what it is.
            raw = memoryview(bytes(self._array.tobytes()))
        offset = max(int(offset), 0)
        return bytes(raw[offset: offset + max(int(length), 0)])

    def _is_contiguous(self) -> bool:
        """Whether the array's bytes are one contiguous run."""
        flags = getattr(self._array, "flags", None)
        return bool(getattr(flags, "c_contiguous", True))


class GpuBufferSource:
    """A GPU buffer, read back through the graphics queue.

    Parameters
    ----------
    buffer : wgpu.GPUBuffer
    device : wgpu.GPUDevice
        Whose queue does the readback.
    name : str
        Where it was found.
    """

    kind = "VRAM"

    def __init__(self, buffer, device, name: str) -> None:
        self._buffer = buffer
        self._device = device
        self.name = str(name)
        self.base_address = 0
        self.error = ""
        label = getattr(buffer, "label", "") or ""
        usage = getattr(buffer, "usage", 0)
        self.detail = f"usage 0x{int(usage):x}" + (f" '{label}'" if label else "")

    def size(self) -> int:
        """Bytes the buffer occupies on the device."""
        return int(getattr(self._buffer, "size", 0) or 0)

    def read(self, offset: int, length: int) -> bytes:
        """Copy a range back from the device.

        Returns
        -------
        bytes
            The range, or zeros if the buffer cannot be read -- in which case
            :attr:`error` says why. A repaint calls this once per visible row,
            so raising here would take the window down for a buffer that is
            merely not copyable.
        """
        offset = max(int(offset), 0)
        length = max(int(length), 0)
        room = max(self.size() - offset, 0)
        length = min(length, room)
        if length <= 0:
            return b""
        try:
            # read_buffer wants 4-byte aligned offsets and sizes on most
            # backends, so the range is widened and the surplus trimmed here
            # rather than showing the caller a shifted dump.
            low = offset - (offset % 4)
            high = min(self.size(), ((offset + length + 3) // 4) * 4)
            raw = bytes(self._device.queue.read_buffer(self._buffer, low, high - low))
        except Exception as problem:  # noqa: BLE001 -- reported, not raised
            self.error = str(problem)
            return b"\x00" * length
        self.error = ""
        return raw[offset - low: offset - low + length]


class MemoryReport:
    """What one probe found: the sources, and the totals by kind."""

    def __init__(self, sources: list) -> None:
        self.sources = sources

    @property
    def ram_bytes(self) -> int:
        """Total bytes of host arrays found."""
        return sum(one.size() for one in self.sources if one.kind == "RAM")

    @property
    def vram_bytes(self) -> int:
        """Total bytes of device buffers found."""
        return sum(one.size() for one in self.sources if one.kind == "VRAM")

    def largest(self, count: int = 10) -> list:
        """The *count* biggest sources, largest first."""
        return sorted(self.sources, key=lambda one: one.size(), reverse=True)[:count]

    def summary(self) -> str:
        """One line naming both totals and how many blocks they came from.

        Deliberately says "found", not "total": see the module docstring.
        """
        return (
            f"found {len(self.sources)} blocks -- "
            f"RAM {_human(self.ram_bytes)} in "
            f"{sum(1 for one in self.sources if one.kind == 'RAM')}, "
            f"VRAM {_human(self.vram_bytes)} in "
            f"{sum(1 for one in self.sources if one.kind == 'VRAM')}"
        )


def _human(count: int) -> str:
    """Bytes as a short human-readable string."""
    size = float(count)
    for unit in ("B", "kB", "MB", "GB"):
        if size < 1024.0 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} GB"


def collect_sources(root, device=None, minimum: int = 1024) -> list:
    """Walk *root* and return every block of memory reachable from it.

    Parameters
    ----------
    root : object
        Where to start -- a view, a backend, a scene. Anything with attributes.
    device : wgpu.GPUDevice, optional
        Needed to read GPU buffers back. Without it, buffers are still listed
        (their sizes are the point) and read as zeros.
    minimum : int, optional
        Blocks smaller than this are skipped. A uniform buffer is 64 bytes and
        there are dozens; listing them buries the 20 MB one that matters.

    Returns
    -------
    list of MemorySource
        Largest first, de-duplicated by object identity -- the same array is
        typically reachable by several paths and each would otherwise be a
        separate row showing the same bytes.
    """
    found: dict[int, object] = {}
    for path, value in _walk(root, "", set(), 0):
        key = id(value)
        if key in found:
            continue
        source = _as_source(value, path, device)
        if source is not None and source.size() >= minimum:
            found[key] = source
    return sorted(found.values(), key=lambda one: one.size(), reverse=True)


def report(root, device=None, minimum: int = 1024) -> MemoryReport:
    """:func:`collect_sources`, wrapped so the totals come with it."""
    return MemoryReport(collect_sources(root, device, minimum))


def _as_source(value, path: str, device):
    """Return the right source for *value*, or ``None`` if it is not memory."""
    if hasattr(value, "nbytes") and hasattr(value, "dtype"):
        return ArraySource(value, path)
    name = type(value).__name__
    if "Buffer" in name and hasattr(value, "size") and not callable(value.size):
        return GpuBufferSource(value, device, path)
    return None


def _walk(value, path: str, seen: set, depth: int) -> Iterator[tuple[str, object]]:
    """Yield ``(path, object)`` for everything reachable within the depth cap."""
    if depth > _MAX_DEPTH or value is None:
        return
    key = id(value)
    if key in seen:
        return
    seen.add(key)

    if isinstance(value, (str, bytes, int, float, bool)):
        return
    if hasattr(value, "nbytes") or "Buffer" in type(value).__name__:
        yield path, value
        return
    if isinstance(value, dict):
        for name, item in list(value.items())[:256]:
            yield from _walk(item, f"{path}[{name!r}]", seen, depth + 1)
        return
    if isinstance(value, (list, tuple, set)):
        for index, item in enumerate(list(value)[:256]):
            yield from _walk(item, f"{path}[{index}]", seen, depth + 1)
        return

    members = getattr(value, "__dict__", None)
    if not members:
        return
    for name, item in list(members.items()):
        if name.startswith("__") or name in _SKIP:
            continue
        yield from _walk(item, f"{path}.{name}" if path else name, seen, depth + 1)
