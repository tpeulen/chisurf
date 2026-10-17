---
type: Reference
title: ndX headless CLI recipes
description: NdX's two core workflows — burst filtering and imaging — run without a window.
tags: [reference, headless, cli, bursts, imaging]
---

# ndX headless CLI recipes

ndX's two core workflows — **burst filtering** and **imaging** — run without
a window. Each prints JSON to stdout so pipelines can chain on it. There are two
layers:

- **`ndxplorer filter|image`** — the pure primitives (in `modules/ndxplorer`,
  chisurf-free): operate on a burst folder / image file on disk.
- **`csc ndxplorer filter|image`** — the chisurf MMFDB wrappers: resolve an MMFDB
  artifact to a local path, run the primitive, and optionally register the result
  back under a sample.

All commands run headless.

## 1. ndX as a burst filter

### Local (primitive)

```bash
# Filter a burst folder by parameter gates (AND across --select; range per param).
ndxplorer filter --folder bursts/ \
    --select "Number of Photons:50-" \
    --select "Duration (ms):0.5-5" \
    --out bursts_filtered/
# => {"input": …, "n_in": N, "n_out": M, "out": "bursts_filtered/"}

# Or a boolean expression over the columns (& | ~ are and, or, not):
ndxplorer filter --folder bursts/ --query "(E > 0.2) & (S < 0.8)" \
    --out bursts_filtered/
```

The filtered folder writes `<tttr>.bst` files that reference photons **by index in
the original TTTR file** — the selection stays next to the same raw data, it is
never copied.

### MMFDB round trip

```bash
# 1) raw + sample -> Burst Selection
csc burst-selection analyze m000.spc m001.spc \
    --filetype SPC-130 --detectors-json det.json \
    --mmfdb --db mmfdb.sqlite --sample-name "DNA burst sample"
#   => prints the output-folder artifact id.

# 2) Burst Selection -> ndX filter
csc ndxplorer filter --from-mmfdb <output_folder_artifact_id> --db mmfdb.sqlite \
    --select "Number of Photons:50-" \
    --to-mmfdb --sample-id <sample_id>
#   => writes a FILTERED burst folder beside the same TTTR and registers it as a
#      new burst selection (operation_type="burst_filtering", parent=source).
```

`--from-mmfdb`/`--db` resolve against the configured database by default; pass the
**same** DB to both CLIs for a real round trip. With `--to-mmfdb` omitted, the
command only writes the filtered folder and prints its path.

## 2. ndX headless imaging

### Local (primitive)

```bash
# Render a per-pixel parameter map. "intensity" = photon count per pixel;
# any other name = mean of that column per pixel (e.g. lifetime).
ndxplorer image --file clsm.h5 --map lifetime --out lifetime_map.tiff
# => {"input": …, "map": "lifetime", "shape": [h, w], "n_selected_px": K, "out": …}
```

- `.tiff`/`.tif` out preserves the quantitative float32 map; `.png`/`.jpg` writes
  a normalized 8-bit preview.
- Restrict the render with parameter gates and/or a pixel ROI; export the kept
  photons/bursts as a sub-selection beside the source TTTR:

```bash
ndxplorer image --file clsm.h5 --map intensity \
    --select "lifetime:1.0-3.0" --roi roi_mask.tiff \
    --out roi_intensity.tiff --out-selection roi_bursts/
```

The ROI is a TIFF class mask (nonzero = selected); it is binarized and resized to
the pixel grid if needed.

### MMFDB round trip

```bash
csc ndxplorer image --from-mmfdb <tttr_or_image_artifact_id> --db mmfdb.sqlite \
    --map lifetime --roi roi_mask.tiff \
    --out lifetime_map.tiff \
    --to-mmfdb --sample-id <sample_id>
#   => registers the exported map (and any masked sub-selection) under the sample,
#      parented to the source artifact.
```

## `--select` parameters

`--select "<param>:<min>-<max>"` (open-ended `min-` or `-max` allowed). `param`
matches a column name case-insensitively — the whole name, or the part before
`|` of an annotated column — as it appears in the burst files, for example
`Number of Photons`, `Duration (ms)`, `Count Rate (KHz)`, `Number of Photons (green)`.
Columns derived by ndX's equations are available once computed. An unknown name
is logged and the gate skipped, so check the reported `n_out`. Use `--query`
for expressions over any loaded column.

## Round-trip parity

Outputs re-open identically in the GUI and resolve through `mmfdb.datasets.open`,
so `raw+sample → BS → ndX filter` and `raw(+sample) → ndX image` work
the same in scripts and by hand.
