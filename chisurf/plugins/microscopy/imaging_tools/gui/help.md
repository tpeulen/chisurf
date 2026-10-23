# Imaging Tools

The imaging pipeline in one window: the steps that share one context, a list on the left, the chosen step on the right.

## The list

Setup and Browser come first, then Resolution, Flow and Colocalization, which read the Browser's source with the Setup's detector windows. The numbered steps, 1. Intensity to 6. Pixel-wise MLE, build per-pixel maps in one shared imaging HDF5. CLSM Draw, Spot Finder and Region MLE follow below the rule; they take the Setup's detectors and, Region MLE, the source and the IRF & BG calibration. Search keeps the tools whose name or description contains the text. A tool marked pending has no native version yet.

Tools that read their own input and take none of this context are ribbon entries of their own, in **Spectroscopy › Imaging**: Drift Correction (align a stack before the maps are built), Particle Tracking, PSF Determination and CLSM Simulator.

## What is shared

Begin in Browser to select a photon image: it becomes the Source of every step. Define detector channels and PIE windows in Setup once; every imaging step receives that definition and reapplies it when it changes. Intensity creates the shared imaging HDF5. Number and Brightness, Mean Micro-Time and Phasor enrich that same measurement. IRF and BG supplies optional per-detector calibration to Phasor and MLE; it can be skipped.

## Moving between tools

Click a tool, or use Previous and Next. Next walks Browser, Resolution, then the numbered steps; when a source is known the per-pixel steps compute on arrival. Each opened tool keeps its settings, drawn regions and results while you move between them. Jobs, progress, cancellation and errors are shown within each tool. A file dropped on the window goes to the open tool.

## Further reading

- [Imaging Tools guide](docs/guides/98_imaging_tools.md)
- [Plugin reference: Image Tools](docs/reference/plugins/imaging_tools.md)
