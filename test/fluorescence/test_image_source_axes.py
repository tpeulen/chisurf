"""Axis interpretation of the shared image-source seam.

A 3-D image file is ambiguous: the leading axis can be frames or channels, and
the answer changes what every downstream analysis sees. These pin the labelled
cases, the heuristic for unlabelled ones, and both overrides.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.imaging.image_source import _stack_from_axes


def test_labelled_axes_are_taken_at_their_word():
    """``T``/``Z`` are frames, ``C``/``S`` channels — no guessing needed."""
    data, _ = _stack_from_axes(np.zeros((7, 3, 16, 32)), "TCYX", None)
    assert data.shape == (7, 3, 16, 32)

    data, _ = _stack_from_axes(np.zeros((3, 7, 16, 32)), "CTYX", None)
    assert data.shape == (7, 3, 16, 32)


def test_a_short_unlabelled_axis_is_guessed_to_be_channels():
    """Up to four planes reads as a colour image, which is the common case."""
    data, _ = _stack_from_axes(np.zeros((3, 16, 32)), "QYX", None)
    assert data.shape == (1, 3, 16, 32)


def test_a_long_unlabelled_axis_is_guessed_to_be_frames():
    """Beyond four planes a stack is a time series, not a colour image."""
    data, _ = _stack_from_axes(np.zeros((9, 16, 32)), "QYX", None)
    assert data.shape == (9, 1, 16, 32)


def test_the_guess_can_be_overridden_towards_channels():
    """A caller who knows the file forces the channel axis by index."""
    data, _ = _stack_from_axes(np.zeros((9, 16, 32)), "QYX", 0)
    assert data.shape == (1, 9, 16, 32)


def test_a_file_can_declare_that_it_has_no_channel_axis():
    """``"none"`` is the case the index override cannot express.

    A four-plane stack whose axes say ``"SYX"`` — colour samples — becomes one
    four-channel frame, so any frame-wise analysis (FRC, drift, N&B) rejects it
    for having one frame. There is no integer that means "there is no channel
    axis", hence the sentinel.
    """
    data, _ = _stack_from_axes(np.zeros((4, 16, 32)), "SYX", None)
    assert data.shape == (1, 4, 16, 32)  # the guess, which is wrong here

    data, _ = _stack_from_axes(np.zeros((4, 16, 32)), "SYX", "none")
    assert data.shape == (4, 1, 16, 32)


def test_a_missing_image_plane_is_an_error_not_a_reshape():
    """Without Y/X there is no image; silently reshaping would invent one."""
    with pytest.raises(ValueError, match="no Y/X plane"):
        _stack_from_axes(np.zeros((4, 16)), "TC", None)
