"""The memory probe: what chimol offers the hex editor to look at.

The editor itself is emtk's, and its arithmetic is proved in emtk's own suite.
What belongs here is the half chimol owns -- walking a viewer-shaped object for
host arrays and device buffers, splitting RAM from VRAM, reading a GPU buffer
back through the queue, and not looping forever on a cycle.
"""
from __future__ import annotations

import pytest

from chimol.core.services import memory_probe

numpy = pytest.importorskip("numpy")


class _FakeBuffer:
    """Stands in for a ``wgpu.GPUBuffer``: a size, a usage and a label."""

    def __init__(self, size: int) -> None:
        self.size = size
        self.usage = 0x8
        self.label = "instances"


class _FakeQueue:
    """Answers a readback with a recognisable pattern."""

    @staticmethod
    def read_buffer(buffer, offset, size):
        """Return *size* bytes of 0xAB."""
        return b"\xab" * size


class _FakeDevice:
    """Has a queue, which is all the probe needs of a device."""

    queue = _FakeQueue()


class _FakeScene:
    """A viewer-shaped object holding one host array and one device buffer."""

    def __init__(self) -> None:
        self.xyz = numpy.zeros(4096, dtype=numpy.float32)
        self.instances = _FakeBuffer(8192)
        self.name = "scene"          # not memory
        self.tiny = numpy.zeros(4)   # below the minimum


def test_the_probe_finds_host_arrays_and_device_buffers_and_separates_them():
    """The headline number is RAM against VRAM, so the split must be right."""
    found = memory_probe.report(_FakeScene(), _FakeDevice())
    kinds = {one.kind for one in found.sources}
    assert kinds == {"RAM", "VRAM"}
    assert found.ram_bytes == 4096 * 4
    assert found.vram_bytes == 8192
    assert "RAM" in found.summary() and "VRAM" in found.summary()


def test_the_probe_skips_blocks_under_the_minimum():
    """A hundred 64-byte uniforms bury the 20 MB one that matters."""
    found = memory_probe.report(_FakeScene(), _FakeDevice(), minimum=1024)
    assert all(one.size() >= 1024 for one in found.sources)


def test_the_probe_names_a_block_by_the_path_it_was_found_at():
    """"A 24 MB float32 array" is not actionable; the attribute path is."""
    found = memory_probe.report(_FakeScene(), _FakeDevice())
    assert {one.name for one in found.sources} == {"xyz", "instances"}


def test_a_device_buffer_reads_back_through_the_queue():
    """And the surplus of the 4-byte-aligned request is trimmed off."""
    source = memory_probe.GpuBufferSource(_FakeBuffer(64), _FakeDevice(), "b")
    assert source.read(2, 4) == b"\xab" * 4
    assert source.error == ""


def test_an_unreadable_device_buffer_returns_zeros_and_says_why():
    """A repaint calls read() once per row; raising would take the window down."""

    class _Angry:
        queue = type("q", (), {"read_buffer": staticmethod(
            lambda *a: (_ for _ in ()).throw(RuntimeError("no COPY_SRC"))
        )})()

    source = memory_probe.GpuBufferSource(_FakeBuffer(64), _Angry(), "b")
    assert source.read(0, 8) == b"\x00" * 8
    assert "COPY_SRC" in source.error


def test_the_probe_does_not_follow_a_cycle_forever():
    """An object graph with a parent pointer is the normal case, not the odd one."""

    class _Node:
        pass

    a, b = _Node(), _Node()
    a.child, b.parent_node = b, a
    b.data = numpy.zeros(1024, dtype=numpy.uint8)
    found = memory_probe.report(a, None, minimum=512)
    assert len(found.sources) == 1
