# Audifier: photon streams as sound and as a waterfall

**Tool:** *Tools -> TTTR -> Audifier* (`tttr_audifier`). It turns a photon stream into sound (louder = more photons) and
shows the same stream as a **waterfall**: macro-time horizontally, micro-time (or lifetime) vertically, each detector in its
own colour. Hearing a burst, a blink or a drift is often faster than finding it in a trace.

```{figure} figures/94_audifier_waterfall.png
:width: 100%

A Becker & Hickl SPC-132 measurement (62 s, 183,657 photons): the micro-time waterfall with its axes, the detectors and
the transport row.
```

## 1. Load a stream
**Load TTTR** (or drop a file on the window). How a file is read is set in **Detector setup**, the shared
[detector setup editor](87_channel_definition.md); a Becker & Hickl `.spc` file needs its subtype chosen there (File Type
`SPC-130`, ...) before loading, otherwise the status line says so. **Update channels** rebuilds the detectors and channels
from the setup.

## 2. Mix
| Window | Control | What it does |
|---|---|---|
| **Detector colours** | **Show**, **Colour** (type `#rrggbb`) | Which detectors enter the waterfall and in which hue. |
| **Channel notes** | **On**, **Pitch**, **Gain**, **Micro first / last**, the **Chord** choice under the table | Which routing channels are played and exported, their chord (major, minor, ...), transposition (-24..24 semitones), amplitude (0..10) and micro-time gate. |
| **Audio parameters** | Bin width, Envelope, Sample rate, Master gain, Env floor / scale, Attack, Release | How photon counts become an amplitude envelope. |
| **Waterfall parameters** | Mode (microtime, lifetime), Micro-time and Lifetime groups | Bins of the micro-time waterfall, or the lifetime grid and regularization of the inverse-Laplace waterfall. |

## 3. Waterfall and sound
**Range start / end** (seconds from the first photon; end 0 = to the end) select the part that is rendered. **Update**
computes the waterfall in the background; the plot has axes, the wheel zooms and a drag pans. **Play / Resume** renders the
selected channels and range and plays them; **Pause** freezes the playback, **Stop** returns to the start, **Revert**
restarts; a white line follows the playback in the waterfall. **Save WAV** writes the same sound as 16-bit mono WAV.
**Guide** walks through all of this; **Help** is the reference.

Concept: [lifetime from photon streams](../concepts/fret.md) for the lifetime waterfall's inverse-Laplace model.
