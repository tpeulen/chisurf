# Overview

Your data stays on your computer. All processing happens in your browser: the file you open is read and analysed on this computer, by tttrlib compiled to WebAssembly and running inside the page. Nothing is uploaded. No data, result or file name is sent to or stored on any server.

The web server only delivers the page itself, like any static website. After that, opening a file, the analysis, the plots and the downloads all happen locally. Downloads are made by the browser from memory.

This page checks and analyses confocal single-molecule FRET (smFRET) measurements: diffusing molecules recorded with time-tagged photon counting (TTTR).

Two modes:

- Simple: open a file and read the quality verdict. The page detects the experiment, finds the bursts and checks the measurement with default settings.
- Advanced: also lets you check and edit the detector channels, the burst search and the FRET corrections. It adds the time trace, and ndX for exploring the burst table.

Press Guide for a step-by-step tour.

# Opening data

Drop a file on the window. Any format tttrlib reads works: PicoQuant PTU, HT3, T3R and T2; Becker & Hickl SPC; SM; PTO. The container is recognised from the file.

No file at hand? Under Measurement > Try it without a file, pick an example and press Simulate. The examples are simulated with tttrlib's photon simulator: cw, PIE and µsALEX, with and without polarization, with noise channels, and one-colour data.

The analysis runs in the background: the page stays usable, shows its progress, and Cancel stops it. Files above 256 MB are read from your disk in chunks as the analysis goes: the page holds no copy of them, so their size is not limited by the browser's memory. Large files simply take longer (a 1 GB file: a few minutes).

# What is detected

The page reads the photons to find out how the measurement was made. Every guess is shown in the Measurement window, and you can change it under Channels in advanced mode.

- Excitation.
  - PIE / nsALEX: two laser pulses within each period, seen as two separate rises in the micro-time histogram.
  - µsALEX: lasers alternating every few to hundreds of microseconds. The alternation shows either in the micro time, or only as a periodic count rate, which is then folded at its period.
  - cw: a single excitation.
- Donor and acceptor detectors.
  - *ALEX/PIE*: the donor detectors are the ones that go dark while the acceptor laser is on.
  - *cw*: channels of one colour rise and fall together from burst to burst. The donor colour is the one with bursts of its colour alone (donor-only molecules); the acceptor is only excited through FRET.
- Polarization. Two channels per colour count as parallel and perpendicular, the brighter one taken as parallel. A G factor far from 1 can swap them, so check.
- Unassigned channels. A channel that counts as fast outside bursts as inside them carries no single-molecule signal: dark counts, scatter, a marker line, an unused detector. It is left out, with a warning.

Lines starting with ! are warnings: something the data could not settle. Check them.

# Quality checks

Each check gets OK, WARN or BAD, or INFO when it only reports a number. Hover a check for its explanation.

Basic quality (needs no ALEX):

- bursts: how many bursts were found, and how many per second.
- burst density: the mean number of molecules in the observation volume, the burst rate times the mean burst duration. Single-molecule measurements need this well below 0.1.
- multi-molecule events: the share of bursts that contain two or more molecules. It is estimated twice: from the burst density (Poisson statistics), and from the gaps between bursts. Molecules arrive at random, so the long gaps follow an exponential whose rate gives the arrival rate, and from that the chance that a second molecule arrives during a burst. Above about 5 %, coincident molecules bridge populations in E/S histograms.
- short gaps: gaps shorter than two burst durations, compared with what random arrivals would give. Many more than expected means bursts are fragmented (blinking, or a strict burst search) or molecules come back to the focus.
- concentration and dilution: the concentration implied by the burst density for the observation volume V_eff (set it under Burst search), and how much to dilute to reach 2 % multi-molecule events.
- time in bursts: high means the sample is too concentrated, or it is not single-molecule data.
- brightness, signal / background, background: the in-burst count rate above background, and the out-of-burst rates per stream.
- signal stability: drift and spikes of the count rate over the measurement (evaporation, bleaching, focus drift, aggregates).
- bright / long bursts: bursts far brighter or longer than the rest (more than 3 interquartile ranges, on a log scale), typically aggregates or sticking molecules.

Two-colour:

- donor-only / acceptor-only: with ALEX/PIE, from the stoichiometry S. With cw, only the low-E fraction can be given, because donor-only molecules and very low FRET look the same.
- FRET-2CDE: high values mean E changes within a burst, from dynamics or two molecules.
- ALEX-2CDE: high values mean acceptor blinking or bleaching, or a donor-only and an acceptor-only molecule together.

Suspicious bursts are flagged individually. Drop QC-flagged bursts (Corrections) leaves them out of the plots, ndX and the export.

# Plots

- Quality: the checks, the count rate in 1 s bins, and the histogram of gaps between bursts with the fitted random-arrival curve. An excess on the left means short gaps.
- E / S: the proximity ratio E against the stoichiometry S (ALEX/PIE), with both marginals. With cw only E is shown. In advanced mode with corrections, E and S are the corrected values.
- Bursts: burst size, duration and count rate. Also E against the donor lifetime when the micro time allows it (FRET lines), else FRET-2CDE against E.
- Time trace (advanced): the count rates of each stream in 1 ms bins with the bursts shaded. Choose where the 10 s stretch starts with From; zoom and drag in the plot.
- Channels (advanced): the micro-time histogram of every channel (log scale), with the excitation windows marked. This is where to check the PIE windows.

# The burst table and ndX

For every burst the analysis records:

- photon counts per stream and per detector
- duration, count rates and mean macro time
- proximity ratio and stoichiometry, plus corrected FRET efficiency and stoichiometry in advanced mode
- donor and acceptor lifetimes: the mean arrival time after the rise of the decay (TCSPC data)
- anisotropies (polarization)
- TGX−TRR (ALEX/PIE)
- FRET-2CDE and ALEX-2CDE
- the QC flags

Columns carry ChiSurf's .bur names, so ChiSurf and ndX read them directly.

ndX (advanced) shows this table: choose any two columns, histogram them, gate populations and see them in every other dimension. Bursts (.csv) downloads the same table.

# Corrections

In advanced mode, E and S are corrected with γ (detection and quantum yield), α (leakage), δ (direct excitation) and β (excitation).

Auto-calibrate:

- *ALEX/PIE*: finds every factor from the measurement itself, using the donor-only and acceptor-only populations and the FRET populations' 1/S against E.
- *cw*: the data only tell the leakage, from the donor-only bursts. γ and β need a reference sample.

# Settings

- Burst search: all-photon sliding window. A burst is where m consecutive photons arrive within T, and it is kept when it has at least *Min photons*. 2CDE τ is the kernel width of the 2CDE filters. V_eff only enters the concentration estimate.
- Channels: donor and acceptor routing channels, comma separated, with polarization parallel first. With ALEX/PIE, the donor- and acceptor-excitation windows are given as start-stop. Re-detect goes back to what the data say.

# Privacy: everything stays in your browser

- Processing: reading the file, detecting the experiment, the burst search, the quality checks, corrections, plots and ndX all run inside this browser tab, in WebAssembly. No part of the analysis runs on a server.
- Your data: the file is read from your disk into the page's memory. It is never uploaded, and neither are the bursts, the results or the file name.
- Downloads: the CSV and JSON files are created by the browser from memory and saved directly to your computer.
- What is loaded from the network: only the page itself (from peulen.xyz) and the Python runtime, Pyodide (from the jsDelivr CDN). These are the same for every visitor and carry nothing of yours.
- Closing the tab removes everything the page held.
- Enforced, not only promised: the page is served with a Content-Security-Policy that lets the browser run code only from this site and the Pyodide CDN, and send requests only to those two. Any other destination is blocked by the browser itself, including analytics or other scripts a network proxy might inject.

You can check this yourself: open the browser's developer tools (Network tab) and watch that opening and analysing a file sends no request.
