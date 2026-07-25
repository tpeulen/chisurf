---
name: burst-selection
description: >-
  Compute burst-wise quantities — above all the proximity ratio — and select a
  population from them. Use when the user asks for a PR histogram, for bursts
  in a given ratio window, for a FRET population, or for the donor-only
  fraction of a single-molecule measurement.
triggers:
  - proximity ratio
  - prox ratio
  - pr histogram
  - burst selection
  - select bursts
  - fret population
  - donor only
  - donor-only
  - low fret
  - high fret
  - stoichiometry
  - alex
  - burst wise
  - burst-wise
experiments: [TCSPC, TTTR]
uses:
  - burst-search
tools:
  - run_python
---

# Selecting a population of molecules

Bursts are molecules. Selecting bursts is choosing **which molecules the rest
of the analysis is about**, so the selection is part of the result and has to
be reported with it.

Get the bursts first — see `burst-search`, including its check that the photon
indices and detector roles are what you think.

## Proximity ratio

```python
green = bursts["Number of Photons (green)"].to_numpy(float)
red = bursts["Number of Photons (red)"].to_numpy(float)
bursts["PR"] = red / (green + red)
```

**PR is not the FRET efficiency.** It is the raw photon ratio, uncorrected
for:

* background in either channel — worst for dim bursts,
* spectral crosstalk, donor emission leaking into the acceptor detector,
* direct excitation of the acceptor by the donor's laser,
* γ, the ratio of detection efficiency × quantum yield between channels.

Uncorrected, the scale is compressed: true efficiencies of 0 and 1 show up
near 0.05 and 0.95. So PR is an excellent **selection coordinate** and a wrong
**reported efficiency**. Say "proximity ratio", not E.

## Show the histogram before selecting

```python
counts, edges = np.histogram(bursts["PR"], bins=20, range=(0, 1))
for i, n in enumerate(counts):
    print("%.2f-%.2f %s %d" % (edges[i], edges[i + 1], "#" * int(40 * n / counts.max()), n))
```

The populations in that histogram *are* the result of the measurement. Show
them, and read the selection boundaries off them rather than assuming round
numbers.

## Selecting

Use exactly the window the user asked for — they know their sample:

```python
fret = (bursts.PR >= 0.5) & (bursts.PR <= 0.7)
```

Then take the **donor-only population** as well, whether or not it was asked
for, because almost every downstream quantity needs a reference:

```python
donor_only = bursts.PR < 0.2      # read the threshold off the histogram
```

The low-PR peak is molecules whose acceptor is missing, bleached or dark.
Their donor is unquenched, and they come from the same sample, buffer,
instrument and day as the FRET population — a better reference than a
separately prepared donor-only sample, and free.

## Say how many you kept

```python
print(len(bursts[fret]), "bursts,", int(bursts[fret]["Number of Photons (green)"].sum()), "donor photons")
```

Both numbers matter, and the photon count matters more. A narrow window on a
sparse measurement can leave too few photons for anything downstream, and the
useful answer then is to widen the window or say the data does not support the
question — not to proceed quietly.

Other burst-wise coordinates select populations too — stoichiometry (with
alternating excitation), burst duration, count rate, ALEX-2CDE for dynamics.
The same rules hold: show the distribution, report the window, keep the
reference population.
