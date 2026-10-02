# Microtime histograms

Use the full Detector Definition editor for routing, PIE, reading, G-factor, TAC and optical parameters. Queue photon streams and optionally BID/BUR selections. Photon bounds are inclusive. Overlaps are counted once and bounds are clipped to the actual stream.

## Polarization and shifts
Interleaved detector channels split into VV/VH unless polarization resolution is disabled. Histogram offsets pad with zeros and clip the edge; the separate photon Microtime Shifter instead wraps events modulo the TAC period.

## Outputs
Export writes VV bins followed by VH bins as one integer column. The diagnostic combined trace is VV + 2G·VH and reports an integer-crossing FWHM. Transfer supplies the time step, G-factor and polarization to the TCSPC workspace. Autosave preserves the original workflow.
