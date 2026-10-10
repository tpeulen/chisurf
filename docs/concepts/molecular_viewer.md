---
type: Concept
title: 'ChiMOL: why the analysis session has its own molecular viewer'
description: What the ChiMOL viewer is for, where its command language and selection algebra come from, and what it is deliberately not.
tags: [concepts, molecular, viewer]
anchor: concept-molecular-viewer
---

(concept-molecular-viewer)=
# ChiMOL: why the analysis session has its own molecular viewer

Many fluorescence questions have a structural half: is a labelling site exposed, where can the dye sit
({ref}`concept-accessible-volume`), which chain does a distance restraint belong to. ChiMOL
(`chisurf/plugins/chimol/`) answers these inside the analysis session so the 3-D view is not a second application. It
loads structures, trajectories, maps and RMF models, draws, selects and measures them, and writes them back out. It
computes no photophysics.

## Where it comes from

Chimol borrows deliberately. Its **command language, selection algebra and representation model follow PyMOL**
(`show sticks, sele`, `select resi 54`, `png`), so PyMOL scripts and habits largely carry over. Its handling of volumes,
surfaces and large assemblies follows UCSF ChimeraX. The interface is drawn inside the viewport rather than assembled
from toolkit widgets, and the renderer targets WebGPU, which lets one renderer sit behind several hosts (a Qt widget, a
toolkit-free desktop window, a browser canvas).

## What it is for, and not for

It is built to scale to large integrative models (assemblies with many copies of a few shapes), which decides its
architecture. It is not a PyMOL or ChimeraX replacement; use those where they are stronger. Surface definitions and
areas are in [Molecular surfaces](molecular_surfaces.md); input formats in
[Structures and trajectories](structure_trajectories.md).

## Workflow

[The molecular viewer (ChiMOL)](../guides/44_molecular_viewer.md): opening a structure, the mouse modes, the command
prompt, the object list and its menus, and rendering to an image.
