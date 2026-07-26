---
name: kappa2-from-anisotropy
description: >-
  Turn measured anisotropy decays into an orientation factor (kappa^2)
  distribution, and carry it into a FRET distance as an honest uncertainty.
  Use when the user mentions kappa squared, orientation factor, dye rotation,
  residual anisotropy, VV/VH data, or asks how reliable a FRET distance is.
triggers:
  - kappa2
  - kappa squared
  - kappa^2
  - k2
  - orientation factor
  - residual anisotropy
  - r_inf
  - anisotropy decay
  - vv/vh
  - vv vh
  - polarisation
  - polarization
  - dye rotation
  - wobbling
  - cone model
  - how reliable is the distance
  - distance uncertainty
experiments: [TCSPC]
uses:
  - fit-decay
tools:
  - list_files
  - load_data
  - run_python
  - create_fit
  - set_irf
  - run_fit
  - get_fit
  - list_plugins
---

# From anisotropy to kappa^2 to a distance range

Every FRET distance rests on an assumption almost nobody measures: that the
dyes rotate freely, so the orientation factor is **kappa^2 = 2/3**. Anisotropy
data tests that assumption and replaces it with a distribution. This is the
difference between "R = 51 Å" and "R = 51 Å, and the dye orientation allows
46–55 Å".

The chain:

```
VV / VH decays -> anisotropy r(t) -> residual anisotropy r_inf -> order parameter S^2
              -> kappa^2 distribution -> range of possible R
```

## 1. The anisotropy decay

A polarised measurement gives two decays, parallel (VV) and perpendicular
(VH). With the instrument's G factor:

```python
import numpy as np

total = vv + 2.0 * G * vh                       # the isotropic sum
r = np.divide(vv - G * vh, total, out=np.zeros_like(total), where=total > 0)
```

Fit the tail of `r(t)` with `r(t) = (r_0 - r_inf) exp(-t/rho) + r_inf`:

* `r_0` — fundamental anisotropy (about 0.38 for common dyes; fit it or fix it),
* `rho` — rotational correlation time: how fast the dye tumbles,
* **`r_inf` — the residual anisotropy, and the number this whole procedure
  needs.** It is what the anisotropy settles to: zero means the dye explores
  every orientation, non-zero means it is held.

`G` is a property of the detection path, not of the sample. Take it from a
calibration; do not fit it alongside `r_inf`, because the two trade against
each other and both become meaningless.

## 2. Order parameters

```
S^2 = sqrt(r_inf / r_0)
```

by convention negative for the donor and positive for the acceptor. `S^2 = 0`
is a freely rotating dye; `S^2 -> 1` is a rigidly fixed one.

**Three anisotropies are needed, not one:** the donor's, the *directly
excited* acceptor's, and the FRET-*sensitised* acceptor's (`r_ADinf`, which
carries the relative geometry of the two dipoles). With only the donor you can
still run the calculation, but say plainly that the acceptor values were
assumed — the result is a sensitivity study, not a measurement.

## 3. The kappa^2 distribution

ChiSurf ships this as a plugin; find it with
`list_plugins(query="kappa")` and drive its computation directly:

```python
from chisurf.plugins.calculator.kappa2_dist.core.algorithms import compute_kappa2_dist

k2 = compute_kappa2_dist(
    model_type="cone",        # wobbling-in-a-cone; "diffusion" and "isotropic" also exist
    r_0=0.38,
    r_Dinf=0.045,             # from the donor anisotropy fit
    r_Ainf=0.10,              # from the acceptor anisotropy fit
    r_ADinf=0.005,            # from the sensitised-emission anisotropy
    kappa2_true=2.0 / 3.0,    # what the distance you are correcting assumed
)
print(k2["k2_mean"], k2["k2_sd"], k2["Rapp_mean"], k2["RappSD"])
```

The same computation is exposed as the RPC method `kappa2_dist.compute`, which
is how a client reaches it over the server.

**The mean is always close to 2/3** — that is a property of the physics, not a
sign the calculation ignored your inputs. Restraining the dyes widens the
distribution rather than shifting it. What you are after is `k2_sd` and the
spread of `Rapp`.

## 4. Into the distance

`R_app / R_DA = (kappa^2 / kappa^2_assumed)^(1/6)`, and the sixth root is the
saving grace: even a factor-of-two error in kappa^2 moves the distance by only
12 %. Report it as a range:

```python
R = 51.0                                   # the distance you fitted assuming 2/3
low  = R * (np.percentile(k2["k2_values"], 2.5) / (2 / 3)) ** (1 / 6)
high = R * (np.percentile(k2["k2_values"], 97.5) / (2 / 3)) ** (1 / 6)
```

Then feed it back into the decay analysis: the FRET-derived distances from
`fret-from-decays` or `fret-from-bursts` carry a fitting uncertainty, and this
is the *systematic* on top of it. Quote both, and say which is which — they
are usually of similar size, and a paper that quotes only the fitting error is
understating what it knows.

## What to say

The residual anisotropies used and where each came from, the model
(`cone` / `diffusion` / `isotropic`), the kappa^2 mean and spread, and the
resulting distance range. If any anisotropy was assumed rather than measured,
say so in the same sentence as the number.

A large `r_inf` on either dye is itself the finding: a dye that cannot rotate
is a dye whose FRET distance carries real orientation uncertainty, and it is
worth telling the user before they design more measurements around it.
