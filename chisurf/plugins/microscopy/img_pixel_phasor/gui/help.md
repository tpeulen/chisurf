# Phasor-FLIM

Open or drop a TTTR scanner image, import the detector setup if needed, and press Run. The estimator, channels, microtime windows and per-detector reference IRFs are shared with the Qt workflow. Each detector remains a separate set of persisted columns. Use Detector calibration to edit channels, JSON microtime ranges and a reference IRF path. A blank reference computes raw phasors. Frequency is in MHz; -1 derives the frequency from the TTTR header. Min photons excludes undersampled pixels.

The g/s maps are dimensionless. The phasor plot places g horizontally and s vertically, overlays the universal semicircle, and shows log-density or individual valid pixels. Ellipse, rectangle and polygon cursors select lifetime populations. Move or resize cursors in the plot, or edit their geometry in Gate regions. Enable, invert, duplicate, rename, combine, save and load cursors. Selected pixels shows the corresponding intensity image.

Photon, g, s and density movies use acquisition frames. Play, Stop, Loop, frame selection and FPS control playback. This is temporal scanner data, not axial slices. Image views offer colormap, gamma and intensity-level controls.

Create imaging HDF5 merges all detector columns. Save container stores the phasor artifact and provenance in PTO. MMFDB uses the authenticated shared source picker and existing provenance registration. ndX explores the live per-pixel table. Next advances an attached native imaging pipeline and retains source/output paths.

Ctrl/Cmd+Enter runs the calculation. Escape requests cancellation. Cancellation is cooperative at compute checkpoints; an active tttrlib calculation may finish its current detector before stopping. Cancelled snapshots never replace displayed results. Settings restore scientific parameters before scheduling recomputation.
