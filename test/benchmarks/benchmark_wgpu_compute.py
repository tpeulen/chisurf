"""When is a WGSL compute kernel worth dispatching, and when is numpy faster?

ChiSurf already has a GPU compute seam (`chimol.render.compute`), and it
guards every kernel with a work-item floor: below `MIN_WORK_ITEMS` the CPU route
is taken instead. That floor is the whole design, because the naive reading of
"the GPU is fifty times faster" is wrong in the way that matters -- it is fifty
times faster *at the arithmetic*, and the arithmetic is usually not what you are
paying for.

This measures both numbers so the floor can be justified rather than asserted:

* **kernel only** -- dispatch and execute, with the data already resident. This
  is the number that flatters the GPU, and it is the honest one for a pipeline
  that keeps its buffers on the device between passes (a renderer).
* **round trip** -- upload, dispatch, read back. This is the honest one for
  anything called from numpy and returning to numpy, which is nearly everything
  in a scientific package.

Run it::

    pixi run python test/benchmarks/benchmark_wgpu_compute.py
"""

from __future__ import annotations

import argparse
import sys
import time

import numpy as np

#: Elements to sweep. The top end is bounded by the dispatch limit rather than
#: by memory: WebGPU allows at most 65535 workgroups per dimension, so a 1-D
#: dispatch at 64 invocations each tops out at 4.19 M elements. Beyond that a
#: kernel has to dispatch in 2-D, which is a real constraint worth knowing
#: before designing around a 1-D launch.
SIZES = (1 << 12, 1 << 14, 1 << 16, 1 << 18, 1 << 20, 1 << 21)

#: Invocations per workgroup. 64 is the usual choice: a multiple of the wave
#: size on every backend, and small enough that the tail of a partial dispatch
#: is cheap.
WORKGROUP = 64

#: The kernel. Deliberately transcendental-heavy: a kernel that only copies
#: memory measures the bus, not the processor, and would make every GPU on
#: earth look useless.
SHADER = """
@group(0) @binding(0) var<storage, read>       src : array<f32>;
@group(0) @binding(1) var<storage, read_write> dst : array<f32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid : vec3<u32>) {
    let i = gid.x;
    if (i >= arrayLength(&src)) { return; }
    let x = src[i];
    dst[i] = sqrt(x) * sin(x) + cos(x * 0.5);
}
"""


def reference(values: np.ndarray) -> np.ndarray:
    """The same arithmetic the shader does, in numpy.

    Parameters
    ----------
    values : numpy.ndarray
        Input.

    Returns
    -------
    numpy.ndarray
        Expected output.
    """
    return np.sqrt(values) * np.sin(values) + np.cos(values * 0.5)


class Kernel:
    """A compiled compute pipeline and the buffers to run it.

    Parameters
    ----------
    device : object
        A ``wgpu`` device.
    """

    def __init__(self, device) -> None:
        import wgpu

        self.wgpu = wgpu
        self.device = device
        self.layout = device.create_bind_group_layout(
            entries=[
                {
                    "binding": 0,
                    "visibility": wgpu.ShaderStage.COMPUTE,
                    "buffer": {"type": wgpu.BufferBindingType.read_only_storage},
                },
                {
                    "binding": 1,
                    "visibility": wgpu.ShaderStage.COMPUTE,
                    "buffer": {"type": wgpu.BufferBindingType.storage},
                },
            ]
        )
        self.pipeline = device.create_compute_pipeline(
            layout=device.create_pipeline_layout(bind_group_layouts=[self.layout]),
            compute={"module": device.create_shader_module(code=SHADER), "entry_point": "main"},
        )

    def buffers(self, values: np.ndarray):
        """Allocate device buffers for one input.

        Parameters
        ----------
        values : numpy.ndarray
            Input, float32.

        Returns
        -------
        tuple
            ``(source, destination, bind group)``.
        """
        wgpu = self.wgpu
        source = self.device.create_buffer_with_data(data=values, usage=wgpu.BufferUsage.STORAGE)
        destination = self.device.create_buffer(
            size=values.nbytes, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC
        )
        bind = self.device.create_bind_group(
            layout=self.layout,
            entries=[
                {"binding": 0, "resource": {"buffer": source, "offset": 0, "size": values.nbytes}},
                {
                    "binding": 1,
                    "resource": {"buffer": destination, "offset": 0, "size": values.nbytes},
                },
            ],
        )
        return source, destination, bind

    def dispatch(self, bind, count: int) -> None:
        """Submit one dispatch.

        Parameters
        ----------
        bind : object
            The bind group.
        count : int
            Elements.
        """
        encoder = self.device.create_command_encoder()
        pass_ = encoder.begin_compute_pass()
        pass_.set_pipeline(self.pipeline)
        pass_.set_bind_group(0, bind)
        pass_.dispatch_workgroups(-(-count // WORKGROUP))
        pass_.end()
        self.device.queue.submit([encoder.finish()])


def measure(kernel: Kernel, count: int, repeats: int) -> tuple[float, float, float, float]:
    """Time one problem size three ways.

    Parameters
    ----------
    kernel : Kernel
        The pipeline.
    count : int
        Elements.
    repeats : int
        Timed iterations.

    Returns
    -------
    tuple of float
        ``(kernel ms, round-trip ms, numpy ms, max abs error)``.
    """
    values = (np.arange(count, dtype=np.float32) + 1.0) * 1e-3
    source, destination, bind = kernel.buffers(values)

    kernel.dispatch(bind, count)
    got = np.frombuffer(kernel.device.queue.read_buffer(destination), dtype=np.float32)
    error = float(np.max(np.abs(got - reference(values))))

    start = time.perf_counter()
    for _ in range(repeats):
        kernel.dispatch(bind, count)
    # One tiny read forces the queue to drain without paying for the transfer.
    kernel.device.queue.read_buffer(destination, buffer_offset=0, size=4)
    kernel_ms = (time.perf_counter() - start) / repeats * 1e3

    start = time.perf_counter()
    for _ in range(repeats):
        source, destination, bind = kernel.buffers(values)
        kernel.dispatch(bind, count)
        np.frombuffer(kernel.device.queue.read_buffer(destination), dtype=np.float32)
    trip_ms = (time.perf_counter() - start) / repeats * 1e3

    start = time.perf_counter()
    for _ in range(repeats):
        reference(values)
    numpy_ms = (time.perf_counter() - start) / repeats * 1e3
    return kernel_ms, trip_ms, numpy_ms, error


def main(argv: list[str]) -> int:
    """Print the table.

    Parameters
    ----------
    argv : list of str
        Command line.

    Returns
    -------
    int
        Process status; 1 when no GPU adapter could be obtained.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=20)
    options = parser.parse_args(argv)

    try:
        import wgpu

        adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
        device = adapter.request_device_sync()
    except Exception as problem:
        print(f"no GPU adapter: {problem}")
        return 1

    info = adapter.info
    print(f"adapter: {info.get('device')} ({info.get('backend_type')}), wgpu {wgpu.__version__}")
    limits = device.limits
    print(
        "limits: workgroup <= "
        f"{limits.get('max-compute-invocations-per-workgroup')} invocations, "
        f"{limits.get('max-compute-workgroups-per-dimension')} workgroups/dimension, "
        f"{limits.get('max-compute-workgroup-storage-size')} B workgroup storage"
    )
    print()

    kernel = Kernel(device)
    print(
        "| elements | kernel [ms] | round trip [ms] | numpy [ms] | kernel vs numpy "
        "| round trip vs numpy |"
    )
    print("| ---: | ---: | ---: | ---: | ---: | ---: |")
    for count in SIZES:
        kernel_ms, trip_ms, numpy_ms, error = measure(kernel, count, options.repeats)
        print(
            f"| {count:,} | {kernel_ms:.3f} | {trip_ms:.3f} | {numpy_ms:.3f} "
            f"| {numpy_ms / max(kernel_ms, 1e-9):.1f}x "
            f"| {numpy_ms / max(trip_ms, 1e-9):.1f}x |"
        )
        assert error < 1e-1, f"kernel disagrees with numpy by {error}"
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
