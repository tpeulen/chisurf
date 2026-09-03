# MFD Prepare

Takes a folder of burst-analysis results and prepares it for multi-frequency
density (MFD) analysis: it verifies the channel layout, checks that the photon
counts agree across the files the folder carries, resolves where each
measurement's source data lives, and collects the diagnostics in one report.

The tool talks to the MMFDB service over RPC — nothing is computed in the
window itself, so preparing a large folder does not block the interface.

## When to use it

Run this after burst search has produced a folder of `.bur` companions and
before any MFD fitting session opens that folder. Preparation is what turns "a
directory with files in it" into a folder the analysis can trust: a channel
that lost its photons, a file whose counts disagree with its companions, or a
source that cannot be resolved are all cheaper to find here than mid-fit.

## How to use it

1. **Browse** to the burst folder.
2. Press **Prepare**. The tool asks the service to walk the folder.
3. Read the result panel: which channels were verified, whether the photon
   counts agree, where the sources resolved, and any diagnostics raised along
   the way.

## What the checks mean

- **Verified channels** — every detector channel the setup declares is present
  in the data and carries photons.
- **Count agreement** — the per-file photon counts are consistent with the
  companions they were measured with; a mismatch usually means a truncated
  write or a file from a different run mixed into the folder.
- **Source resolution** — each measurement can be traced back to the raw file
  it came from. An unresolved source means the analysis can display the bursts
  but cannot re-read the photons behind them.

Press **Guide** for the walk-through.
