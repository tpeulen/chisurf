# TTTR Audifier

Load or drop a TTTR file, then define detectors and update channels. If no
detectors are defined, routing channels receive separate default detectors.
A Becker & Hickl .spc file needs its subtype chosen in the detector setup (File Type) first.
Detector Show and colour (#rrggbb in the table) control the waterfall; channel enable, chord,
pitch, gain and micro-time gates control audio. Micro-time gate endpoints are
inclusive first bin and exclusive last bin.

Range start/end are elapsed macro-time seconds relative to the source's first
event; zero end includes the remainder. Update recomputes a micro-time or
regularized inverse Laplace lifetime waterfall in the background. Lifetime
limits use nanoseconds and are converted to seconds before fitting.

Audio parameters control photon-count binning, compression, sample rate, gain,
floor/scale and attack/release smoothing. Play renders current parameters;
Pause freezes actual playback, Resume continues at that position, Stop returns
to the beginning, and Revert restarts if playing. Save WAV uses the same synthesis
parameters as playback, writing 16-bit mono PCM. Rendering remains available
when no OS audio device/player is available.

The waterfall has elapsed time horizontally and micro-time or lifetime vertically,
increasing upward, on a plot with axes (the wheel zooms, a drag pans). Detector hue and normalized amplitude brightness encode
the contributing stream. The white line follows playback position. Lifetime
diagnostics use an ILT model and are not a substitute for calibrated fitting.

## Further reading

[Audifier guide](docs/guides/94_tttr_audifier.md) · [Detector setup](docs/guides/87_channel_definition.md)
