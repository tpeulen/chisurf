"""Matrix Vision frame-grabber source without a vendor driver."""

import ctypes

import numpy as np
import pytest

from chisurf.plugins.core.acq.live.video import MatrixVisionSource


class FakeSDK:
    def __init__(self):
        self.buffer = ctypes.create_string_buffer(bytes([1, 2, 3, 4]))
        self.closed = []

    def DMR_Init(self, manager):
        return 0

    def DMR_GetDeviceCount(self, count):
        count._obj.value = 1
        return 0

    def DMR_GetDevice(self, device, mode, pattern, index, wildcard):
        device._obj.value = 42
        return 0

    def DMR_OpenDevice(self, device, driver):
        driver._obj.value = 7
        return 0

    def DMR_ImageRequestSingle(self, driver, control, request):
        return 0

    def DMR_ImageRequestWaitFor(self, driver, timeout, queue, request):
        request._obj.value = 9
        return 0

    def DMR_GetImageRequestResultEx(self, driver, request, result, size, r1, r2):
        result[0] = 0
        return 0

    def DMR_GetImageRequestBufferData(self, driver, request, *args):
        for arg, value in zip(args[:6], (1, 1, 2, 2, 4, 1)):
            arg._obj.value = value
        args[6]._obj.value = ctypes.addressof(self.buffer)
        return 0

    def DMR_ImageRequestUnlock(self, driver, request):
        self.closed.append("unlock")
        return 0

    def DMR_CloseDevice(self, driver, device):
        self.closed.append("device")
        return 0

    def DMR_Close(self):
        self.closed.append("manager")
        return 0


def test_matrix_capture_copies_mono_before_unlock():
    sdk = FakeSDK()
    source = MatrixVisionSource(library=sdk)
    source.open()
    frame = source.read()
    sdk.buffer[0] = b'\x00'
    assert frame.image.shape == (2, 2, 3)
    np.testing.assert_array_equal(frame.image[:, :, 0], [[1, 2], [3, 4]])
    source.close()
    assert sdk.closed == ["unlock", "device", "manager"]


def test_matrix_invalid_device_closes_manager():
    sdk = FakeSDK()
    source = MatrixVisionSource(1, library=sdk)
    with pytest.raises(RuntimeError, match="unavailable"):
        source.open()
    assert sdk.closed == ["manager"]
