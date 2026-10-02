---
type: Guide
title: Aligning detectors in micro time (Micro-time Shifter)
description: Bringing the detectors of one TCSPC measurement onto a common micro-time axis with the Micro-time Shifter — queue files, align on the rising edge, fine-tune per-channel shifts, write shifted copies or archive them in MMFDB — in the window, from the command line and from Python.
tags: [guides, tttr, tcspc, micro-time, detectors, python, cli]
---

# Aligning detectors in micro time (Micro-time Shifter)

**What you get:** shifted copies of your photon files in which every routing
channel (detector) has its response on the same micro-time bin, ready for a
common IRF, PIE windows or a combined decay. The inputs are never changed.

Theory: why detectors are offset, what the cyclic shift does and how the
rising edge fixes the offset is in {ref}`concept-microtime-shift`; the decay
analysis that follows is {doc}`76_decay_analysis_tools` and
{doc}`73_tttr_decay_and_correlation`; the detector setup that names the
channels is {doc}`87_channel_definition`.

## 1. Open the tool

**Tools → TTTR → Microtime Shifter**. The window has three docks: **Files**
(the queue, top left), **Micro-time shift** (the controls, below it; a
**Status** tab beside them) and the **Micro-time histograms** (right), which
gets the room. Buttons use a pictogram and a caption; every control has a
tooltip, **Help** explains the window and **Guide** walks through it.

```{figure} figures/88_microtime_shifter.png
:name: fig-microtime-shifter
:width: 100%

The Micro-time Shifter on a demo file whose two detectors (routing channels 0
and 8) carry the same sharp response, 400 bins apart. After **Auto align** the
shifts are 3904 and 3504 bins (the edges, found at bins 601 and 1001, land on
the target bin 409), the two histograms lie on top of each other, and the
green (target bin) and yellow (trigger level) lines are the draggable
settings.
```

## 2. Queue files

- **Files…** picks photon files, **Folder…** queues every supported file of a
  folder (recursively), **Database…** picks inputs from the MMFDB object
  store. You can also drop files or a folder on the window.
- All queued files must have the **same number of micro-time bins**; the
  histograms of a file sum its photons by routing channel. A mixed queue is
  refused with a message in the Files dock.
- Selecting a file in the list reloads it (its shifts are reset);
  **Remove** (or right-click → *Remove from queue*) takes the selected file
  off the queue — it stays on disk — and **Clear** empties the queue.

## 3. Align on the rising edge

The yellow line is the **trigger level** (a count threshold), the green line
the **target bin**. Set them in the fields (**Trigger level**, **Target
bin**, with their spin arrows or by typing and Enter) or by dragging the lines
in the histogram; **Auto align** sets every channel's shift so that its rising
edge — the first bin up to its peak at or above the level — lands on the
target. Editing a field or releasing a dragged line aligns again, so the plot
always shows the aligned state. Pick the level above the background and where
the edge is steep; with **Log Y** the background is easier to see. **Show
trigger lines** hides the lines.

## 4. Fine-tune the shifts

**Global shift** moves every channel; each **Channel** row adds its own shift
(typed, stepped with the arrows or wheel, bounded by the bin count) and the
↺ button next to it sets that row back to zero. The histogram follows
immediately.

## 5. Save

- **Save shifted…** with one queued file asks for the name of the shifted file
  (suggested `<name>_shifted.<ext>`); with several it asks for a folder and
  writes one file per input. A name that exists is not overwritten without
  asking.
- **Batch folder** + **Save batch** do the same into a folder you typed or
  chose with **Browse…**.
- In the folded **MMFDB** panel, **Register shifts in MMFDB** writes the
  shifted files into the object store with their provenance under a sample:
  choose one from the list (**Refresh samples**) or define one with **New
  sample…** (name, entity, probes; the full record is under *Advanced sample
  definition*). It needs a verified MMFDB session.

## Headless

```bash
csc microtime-shift apply measurement.spc --global-shift 0 \
    --channel-shift 0 3904 --channel-shift 8 3504 --output-dir shifted/
```

```python
from chisurf.plugins.tttr.tttr_microtime_shifter.api.shift import shift_file

out_path, applied = shift_file(
    "measurement.spc", global_shift=0, channel_shifts={0: 3904, 8: 3504}, output_dir="shifted",
)
```

The command line takes the shifts you give it; the rising-edge search is part
of the window (it is a judgement about your data), so find the numbers there
and reuse them for the rest of a series.

## Using it well

- Align only detectors that see the **same excitation**; align by the edge of a
  prompt component, not by the peak of a long decay.
- Check the result by the overlay of the histograms, not by the numbers.
- Keep the shifts you used (the Status tab shows them; the MMFDB registration
  records them): the shifted files no longer carry the original offsets.

## Known defects

- The Qt version of the tool (legacy) shows 0 in its Level and Pos boxes after
  a load although the state holds the trigger values; the emtk window shows the
  real ones.

## See also

{doc}`87_channel_definition` · {doc}`12_handling_tttr_files` ·
{doc}`/concepts/microtime_shift`
