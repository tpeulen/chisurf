"""Turn a downloaded CC0 audio pack into the clips chigame ships.

This is a **developer tool**, not a runtime path: it runs once when a pack is
adopted or updated, and its output is committed. Nothing in the game imports it.

What it does, and why each step is there:

* **Mono, 22.05 kHz.** The source is 44.1 kHz stereo; the mixer is mono and the
  material is chiptune, which has almost nothing above 11 kHz. Halving the rate
  is an exact 2:1 decimation, so it is a cheap FIR and a slice rather than a
  resampler.
* **IMA ADPCM** (:mod:`chisurf.gui.chigame.adpcm`), which is the four-to-one
  that makes the difference between 27 MB and 6.5 MB -- between a soundtrack
  that lives in the repository and one that is a download step.
* **One zip per pack**, stored uncompressed because the clips already are. 512
  sound effects as 512 committed files is a lot of git objects for no gain; as
  one archive it is one object and `zipfile` reads a named entry out of it in
  microseconds.
* **The author's own words are copied verbatim** into ``CREDITS.md``. CC0 asks
  for nothing, but a package that redistributes somebody's work should say
  whose it is, in their words, and keep the licence statement it was given
  under next to the files.

Usage::

    python -m build_tools.dev_utils.pack_game_audio <extracted-pack-dir> \\
        --out chisurf/gui/chigame/audio_assets
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import wave
import zipfile

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from chisurf.gui.chigame import adpcm  # noqa: E402

#: What the clips are stored at. Chiptune has almost nothing above 11 kHz, so
#: this is transparent for the material and exactly half the source rate.
TARGET_RATE = 22050

#: Longest music clip kept, in seconds. These loops run to 82 s; a game loop
#: does not need to be that long and every second is 11 kB.
MAX_MUSIC_SECONDS = 90.0

#: A gentle FIR before decimating. Dropping every other sample without it folds
#: everything above 11 kHz back down as aliasing -- the same mistake the old
#: synthesiser made, and it sounds the same way.
_HALFBAND = np.array([1.0, 4.0, 7.0, 4.0, 1.0])


def read_wav(path: pathlib.Path) -> tuple[np.ndarray, int]:
    """Read a PCM WAV as float samples.

    Parameters
    ----------
    path : pathlib.Path
        The file.

    Returns
    -------
    tuple
        ``(samples, rate)``; stereo is mixed down to mono.

    Raises
    ------
    ValueError
        If the file is not 16-bit PCM.
    """
    with wave.open(str(path), "rb") as handle:
        if handle.getsampwidth() != 2:
            raise ValueError(f"{path.name}: not 16-bit PCM")
        rate = handle.getframerate()
        channels = handle.getnchannels()
        raw = handle.readframes(handle.getnframes())
    data = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, rate


def to_target(samples: np.ndarray, rate: int) -> np.ndarray:
    """Bring one clip to the shipped rate.

    Parameters
    ----------
    samples : numpy.ndarray
        Mono float samples.
    rate : int
        Their rate.

    Returns
    -------
    numpy.ndarray
        Signed 16-bit mono at :data:`TARGET_RATE`.
    """
    if rate != TARGET_RATE and rate == TARGET_RATE * 2:
        window = _HALFBAND / _HALFBAND.sum()
        samples = np.convolve(samples, window, mode="same")[::2]
    elif rate != TARGET_RATE:
        # Anything that is not an exact halving gets linear resampling, which
        # is adequate for effects and never happens for the packs we ship.
        count = int(round(samples.size * TARGET_RATE / max(rate, 1)))
        samples = np.interp(
            np.linspace(0.0, samples.size - 1, count),
            np.arange(samples.size), samples,
        )
    return np.clip(samples, -32768, 32767).astype(np.int16)


def pack(sources: list[pathlib.Path], destination: pathlib.Path,
         limit: float | None = None) -> tuple[int, int]:
    """Convert a set of WAVs into one archive of clips.

    Parameters
    ----------
    sources : list of pathlib.Path
        The WAV files, in the order they should be listed.
    destination : pathlib.Path
        The zip to write.
    limit : float, optional
        Trim every clip to this many seconds.

    Returns
    -------
    tuple of int
        ``(clips written, bytes written)``.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_STORED) as archive:
        for path in sources:
            try:
                samples, rate = read_wav(path)
            except (ValueError, wave.Error) as problem:
                print(f"  skipped {path.name}: {problem}")
                continue
            data = to_target(samples, rate)
            if limit is not None:
                data = data[:int(limit * TARGET_RATE)]
            archive.writestr(f"{slug(path)}.snd", adpcm.encode(data, TARGET_RATE))
            written += 1
    return written, destination.stat().st_size


def slug(path: pathlib.Path) -> str:
    """A stable, tidy name for a source file.

    Parameters
    ----------
    path : pathlib.Path
        The source.

    Returns
    -------
    str
        Lower-case, spaces and brackets removed.
    """
    name = path.stem.lower()
    for junk in ("juhani junkala", "[retro game music pack]", "sfx_"):
        name = name.replace(junk, "")
    keep = [char if char.isalnum() else "_" for char in name.strip()]
    return "_".join("".join(keep).split("_")).strip("_") or path.stem.lower()


def main(argv: list[str]) -> int:
    """Pack a downloaded bundle.

    Parameters
    ----------
    argv : list of str
        Command line.

    Returns
    -------
    int
        Process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=pathlib.Path,
                        help="directory holding the extracted pack(s)")
    parser.add_argument("--out", type=pathlib.Path, required=True,
                        help="where the archives are written")
    parser.add_argument("--music-glob", default="*.wav")
    parser.add_argument("--sfx-glob", default="**/sfx_*.wav")
    options = parser.parse_args(argv)

    music = sorted(options.source.glob(options.music_glob))
    effects = sorted(options.source.glob(options.sfx_glob))
    if music:
        count, size = pack(music, options.out / "music.zip", MAX_MUSIC_SECONDS)
        print(f"music: {count} clips, {size / 1e6:.1f} MB")
    if effects:
        count, size = pack(effects, options.out / "sfx.zip")
        print(f"sfx:   {count} clips, {size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
