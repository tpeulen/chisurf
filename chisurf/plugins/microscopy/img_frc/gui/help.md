# FRC resolution

**What it answers.** How fine a detail this image actually resolves — not what
the pixel size or the objective would allow, but what the photons you collected
support.

## How it works

Split one acquisition into two halves that are statistically independent, and
compare them ring by ring in Fourier space. Low spatial frequencies — the coarse
structure — are reproducible, so the two halves agree and the correlation is
near 1. High frequencies are dominated by shot noise, which is different in the
two halves, so the correlation falls to 0. The frequency at which it falls
through a threshold is the finest detail the measurement supports; its inverse
is the resolution.

## The split is the measurement

Everything depends on the two halves being **independent measurements of the
same object**. Correlating an image with itself gives 1 everywhere and no
resolution at all; correlating it with a smoothed copy measures the smoothing.

* **Even / odd frames** — the default. Both halves span the whole acquisition,
  so slow drift affects them equally.
* **First / second half** — for detectors whose consecutive frames are *not*
  independent, or when you want to see whether the second half degraded.
* **Two channels** — two detectors that saw the same structure. Not two labels
  on *different* structures: those correlate nowhere, and the tool will report
  the field of view as the resolution.
* **Two files** — two repeated acquisitions of the same field of view.

## Reading the result

* The **criterion** belongs with the number. Fixed 1/7 (Nieuwenhuizen et al.
  2013) is the usual convention for fluorescence images. ½-bit (van Heel &
  Schatz 2005) and 2σ depend on how many Fourier pixels each ring holds, so they
  also depend on the image size; on the same data the three disagree by tens of
  per cent.
* Without a **pixel size** the answer is in pixels. The conversion is linear, so
  an uncertain pixel size makes an equally uncertain resolution.
* **No crossing** is a real answer, not an error. Either the halves agree at
  every frequency the sampling can show — the image is oversampled relative to
  its resolution — or they agree nowhere, which means too few photons or a split
  whose halves were not independent.
* The resolution is a property of *this acquisition*, not of the microscope.
  More frames, a brighter label or a longer dwell all move it.

## References

* R. P. J. Nieuwenhuizen et al., *Measuring image resolution in optical
  nanoscopy*, Nature Methods **10** (2013) 557–562.
* M. van Heel, M. Schatz, *Fourier shell correlation threshold criteria*,
  J. Struct. Biol. **151** (2005) 250–262.
