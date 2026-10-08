---
type: Concept
title: 'Detector setups: routing, windows, timing and calibration'
description: How a portable detector definition associates routing channels with logical detectors, raw micro-time windows, timing units, calibration and TAC corrections.
tags: [concepts, detector, setup, tttr, tcspc, calibration]
anchor: concept-detector-setup
---

(concept-detector-setup)=
# Detector setups: routing, windows, timing and calibration

A detector setup declares how photon records belong to an analysis. It names
logical detectors and their routing channels, excitation windows on the
micro-time axis, the reading format and timing, calibration values, and optional
TAC linearization tables and shifts. The portable definition also retains
optical settings, identities and additional metadata. A name in a setup library
selects that definition; it does not by itself establish instrument calibration.

## Routing and raw micro-time windows

Routing-channel integers identify records in the photon stream. Logical names
such as green or red depend on the acquisition wiring and setup; they cannot
be inferred from the integer alone. For polarization-resolved detectors, the
declared channel order alternates parallel and perpendicular entries. Without
polarization resolution, the selected detector channels form one stream.

PIE windows and detector micro-time ranges use **raw micro-time channels**,
before histogram binning. Endpoint inclusion follows the documented boundary
semantics of the owning reader or analysis; it is not universal across consumers.
Binning groups samples for computation
and display; it does not change the stored raw gate endpoints. Definitions
should therefore retain raw ranges such as `0:4095` even when an analysis
groups several bins. The derived window-by-detector channel map comes from
these declarations; it is not a separate manually maintained calibration.

## Timing units and provenance

The setup's macro-time resolution and excitation period are in ns. Its raw
and effective micro-time resolutions are in ps; the effective value includes
the micro-time binning factor. A consumer that needs ns must convert a ps
getter once. A provider/header getter already expressed in ns uses that unit
directly. Mixing the two paths creates a factor-of-1000 error.

Timing read from a provider or header is distinct from independently known
acquisition calibration. An unsaved initializer is not provenance. For the
headerless measured BH132 fixture, the provider-derived micro-time step is
3.2958984375 ps; it is not an independently verified instrument calibration.
An explicit manual or saved timing override must be based on its own stated
purpose. The 25 ps setting used in legacy histogram validation establishes
count/control comparison, not a new acquisition clock. See the
[microtime histogram workflow](../guides/89_microtime_histogram.md).

## Calibration and TAC corrections

The G-factor and channel-mixing values describe detection/polarization
corrections, not routing identities. Their interpretation and assumptions are
explained in [anisotropy](anisotropy.md). The independent reference workflow
retains its raw-channel tail, uncertainty and source/calibration identifiers;
a quick loaded-preview G estimate is a different operation and has no such
reference archival. A missing valid mixing estimate does not justify erasing
stored mixing, while an explicit manual zero is an intentional update.

A channel LUT corrects the micro-time response of the declared channel. Its
application flag and per-channel shifts travel with the setup. Keep those
associations with the raw-channel definition and verify them for the instrument;
a shifted or linearized preview is not proof of a newly calibrated clock.
See [TAC linearization](../guides/37_tttr_microtime_lut.md).

## Working definition, named setup and library

The working definition is one complete portable object. A named setup stores
that object through the existing identity/ownership-aware store. A setup
library contains multiple named objects and their last-used selection. Export
of one complete definition and export of the entire library are distinct file
operations; saving a name is another persistence action. Additional scientific
metadata must survive each operation rather than being reduced to visible
detector columns.

The native editor uses this same portable model in standalone and hosted
pages. Existing wizard navigation can require successful definition export
before completion; cancelled or failed export does not satisfy that policy.
The current controls and Python interfaces are described in
[the detector-definition guide](../guides/87_channel_definition.md).

## See also

- [Micro-time histograms](microtime_histogram.md) and [micro-time shifts](microtime_shift.md).
- [Measurement and provenance](measurement_database.md).
- Portable model: {src}`chisurf/core/setup_channel_definition.py`.
- Reading/LUT adapter: {src}`chisurf/core/data_io/detector_setups.py`.

Native preset-editor geometry is declared alongside its controls. Restoring a
window retains the selected detector setup and correlation pairs; changing its
size does not modify the instrument definition or saved presets. See the
[channel workflow](../guides/87_channel_definition.md).
