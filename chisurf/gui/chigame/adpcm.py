"""Block-aligned IMA ADPCM, so a soundtrack can live in a source tree.

The games use real recorded audio now, and audio is large. The five music loops
and the 512 sound effects come to **27 MB** as the 44.1 kHz WAV they ship as,
and 26 MB even reduced to 22 kHz mono. At four bits a sample that is **6.5 MB**
-- the same order as the screenshots already committed -- which is the
difference between "the soundtrack is in the repository" and "the soundtrack is
a download step".

IMA ADPCM is the obvious codec for it: four bits per sample, no dependency, and
an algorithm short enough to be read in one sitting. It is also *lossy in a way
that suits this material* -- it tracks a signal's slope rather than its
spectrum, so chiptune square waves and short percussive effects survive it far
better than speech does.

**Blocks are what make it fast.** IMA is sequential by nature: each sample's
value depends on the predictor left by the one before, which is a Python loop
over millions of samples and far too slow to run at load. So the stream is cut
into independent blocks, each carrying its own starting predictor -- exactly as
the WAV variant of IMA does -- and then every block is decoded *in parallel*
with numpy. The loop that remains runs once per sample **within** a block, a
few hundred iterations over an array of thousands, and a minute of audio
decodes in milliseconds.
"""

from __future__ import annotations

import struct

import numpy as np

#: The IMA step table. 89 quantiser steps, geometric at about 1.1x.
STEP_TABLE = np.array([
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41,
    45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190,
    209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724,
    796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272,
    2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132,
    7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350,
    22385, 24623, 27086, 29794, 32767,
], dtype=np.int32)

#: How the step index moves after each nibble: down for small deltas, up for
#: large ones, which is the whole of the "adaptive" in ADPCM.
INDEX_TABLE = np.array([-1, -1, -1, -1, 2, 4, 6, 8], dtype=np.int32)

#: Samples per independent block. Every block restates its predictor, so this
#: is the unit of parallelism *and* the overhead: 505 costs four bytes in every
#: 256, under 2%, and gives numpy enough blocks to work on.
BLOCK = 505

#: File magic and version. A clip carries its own sample rate so nothing has to
#: agree with anything out of band.
MAGIC = b"CGSND1\0\0"


class ClipError(ValueError):
    """The bytes handed over are not a clip this decoder understands."""


def _blocks(count: int, block: int) -> int:
    """How many blocks a sample count needs.

    Parameters
    ----------
    count : int
        Samples.
    block : int
        Samples per block.

    Returns
    -------
    int
        Block count, at least one.
    """
    return max(1, -(-count // block))


def encode(samples: np.ndarray, rate: int, block: int = BLOCK) -> bytes:
    """Compress 16-bit mono samples into a clip.

    Parameters
    ----------
    samples : numpy.ndarray
        Signed 16-bit mono audio.
    rate : int
        Sample rate in Hz, stored in the clip.
    block : int, optional
        Samples per independent block.

    Returns
    -------
    bytes
        A clip, ready to write to disk.
    """
    data = np.asarray(samples, dtype=np.int32).reshape(-1)
    count = data.size
    total = _blocks(count, block) * block
    padded = np.zeros(total, np.int32)
    padded[:count] = data
    grid = padded.reshape(-1, block)

    # The first sample of every block is stored verbatim and becomes that
    # block's starting predictor, which is what makes the blocks independent.
    predictor = grid[:, 0].astype(np.int32)
    index = np.zeros(grid.shape[0], np.int32)
    nibbles = np.zeros((grid.shape[0], block - 1), np.uint8)

    for step_index in range(1, block):
        target = grid[:, step_index]
        delta = target - predictor
        sign = (delta < 0).astype(np.int32) * 8
        delta = np.abs(delta)

        step = STEP_TABLE[index]
        code = np.zeros_like(delta)
        difference = step >> 3

        big = delta >= step
        code = np.where(big, code + 4, code)
        delta = np.where(big, delta - step, delta)
        difference = np.where(big, difference + step, difference)

        half = delta >= (step >> 1)
        code = np.where(half, code + 2, code)
        delta = np.where(half, delta - (step >> 1), delta)
        difference = np.where(half, difference + (step >> 1), difference)

        quarter = delta >= (step >> 2)
        code = np.where(quarter, code + 1, code)
        difference = np.where(quarter, difference + (step >> 2), difference)

        predictor = np.where(sign > 0, predictor - difference, predictor + difference)
        predictor = np.clip(predictor, -32768, 32767)
        index = np.clip(index + INDEX_TABLE[code], 0, STEP_TABLE.size - 1)
        nibbles[:, step_index - 1] = (code | sign).astype(np.uint8)

    # Two nibbles to a byte, low nibble first -- the order every IMA
    # implementation uses, and the one thing that is silently wrong if you
    # guess it the other way round.
    pairs = nibbles.reshape(grid.shape[0], -1)
    if pairs.shape[1] % 2:
        pairs = np.concatenate([pairs, np.zeros((grid.shape[0], 1), np.uint8)], axis=1)
    packed = (pairs[:, 0::2] | (pairs[:, 1::2] << 4)).astype(np.uint8)

    header = struct.pack("<8sIIH2x", MAGIC, int(rate), int(count), int(block))
    heads = np.zeros((grid.shape[0], 4), np.uint8)
    starts = grid[:, 0].astype(np.int16).view(np.uint8).reshape(-1, 2)
    heads[:, 0:2] = starts
    heads[:, 2] = 0  # every block starts from step index zero
    return header + np.concatenate([heads, packed], axis=1).tobytes()


def decode(raw: bytes) -> tuple[np.ndarray, int]:
    """Expand a clip back to 16-bit mono samples.

    Parameters
    ----------
    raw : bytes
        A clip written by :func:`encode`.

    Returns
    -------
    tuple
        ``(samples, rate)`` -- signed 16-bit mono audio and its sample rate.

    Raises
    ------
    ClipError
        When the magic is wrong or the body is truncated.
    """
    if len(raw) < 20 or raw[:8] != MAGIC:
        raise ClipError("not a chigame clip")
    _, rate, count, block = struct.unpack("<8sIIH2x", raw[:20])
    if block < 2:
        raise ClipError("nonsensical block size")

    packed_per_block = (block - 1 + 1) // 2
    stride = 4 + packed_per_block
    body = np.frombuffer(raw, dtype=np.uint8, offset=20)
    blocks = body.size // stride
    if blocks < 1:
        raise ClipError("clip body is truncated")
    body = body[:blocks * stride].reshape(blocks, stride)

    predictor = body[:, 0:2].copy().view(np.int16).reshape(-1).astype(np.int32)
    index = body[:, 2].astype(np.int32)
    packed = body[:, 4:]
    nibbles = np.empty((blocks, packed.shape[1] * 2), np.uint8)
    nibbles[:, 0::2] = packed & 0x0F
    nibbles[:, 1::2] = packed >> 4

    out = np.zeros((blocks, block), np.int32)
    out[:, 0] = predictor
    for step_index in range(1, block):
        code = nibbles[:, step_index - 1].astype(np.int32)
        step = STEP_TABLE[index]
        magnitude = code & 7
        difference = step >> 3
        difference = np.where(magnitude & 4, difference + step, difference)
        difference = np.where(magnitude & 2, difference + (step >> 1), difference)
        difference = np.where(magnitude & 1, difference + (step >> 2), difference)
        predictor = np.where(code & 8, predictor - difference, predictor + difference)
        predictor = np.clip(predictor, -32768, 32767)
        index = np.clip(index + INDEX_TABLE[magnitude], 0, STEP_TABLE.size - 1)
        out[:, step_index] = predictor

    return out.reshape(-1)[:count].astype(np.int16), int(rate)


def to_pcm(raw: bytes) -> bytes:
    """Decode a clip straight to the little-endian PCM the mixer plays.

    Parameters
    ----------
    raw : bytes
        A clip.

    Returns
    -------
    bytes
        Little-endian signed 16-bit samples.
    """
    samples, _ = decode(raw)
    return samples.astype("<i2").tobytes()


def rate_of(raw: bytes) -> int:
    """The sample rate a clip was stored at, without decoding it.

    Parameters
    ----------
    raw : bytes
        A clip.

    Returns
    -------
    int
        Hertz.

    Raises
    ------
    ClipError
        When the magic is wrong.
    """
    if len(raw) < 20 or raw[:8] != MAGIC:
        raise ClipError("not a chigame clip")
    return int(struct.unpack("<8sIIH2x", raw[:20])[1])
