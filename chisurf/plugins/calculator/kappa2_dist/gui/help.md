# κ² distribution — what this calculator is for

A FRET distance is only as good as the orientation factor κ² that went into
R₀, and κ² is not measured directly. This tool turns anisotropies you *can*
measure into the distribution of κ² consistent with them, and from that into the
range of distances your measurement actually supports.

If you have not run it before, press **🧭** for the guided tour.

The output to take away is not the mean κ² — it is **SD R_app/R_DA**, the
relative systematic uncertainty on the distance.

## What you need to measure first

| Input | Where it comes from |
|---|---|
| **r₀** | Fundamental anisotropy of the dye, at your excitation wavelength |
| **r_D∞** | Residual anisotropy of the **donor**, donor-only sample |
| **r_A∞** | Residual anisotropy of the **directly excited acceptor** |
| **r_AD∞** | Residual anisotropy of the **FRET-sensitized acceptor** |

The first three come from ordinary time-resolved anisotropy fits. The fourth is
the hard one — it needs sensitized acceptor emission separated from directly
excited acceptor emission and from donor leakage. **If you do not have it,
leave `r_AD known` unchecked**: the tool then drops the δ angle and returns the
wider, honest bound instead of a falsely tight one.

The order parameters follow as S² = r_∞/r₀: zero for a freely reorienting dye,
one for a rigidly fixed one.

## The three models

**WIC (Cone)** — each dye reorients freely inside a cone whose half-angle
follows from its order parameter, with the two cone axes separated by δ. This is
the right model when the dyes are on flexible linkers and simply restricted.
Setting both order parameters to zero returns κ² = 2/3 exactly, which is the
sanity check to run when a number looks wrong.

**DWT (Diffusion)** — a fraction of molecules has the dye *trapped* in a fixed
orientation while the rest reorients freely; S² is read as that trapped
fraction. Four sub-populations result (both free, donor trapped, acceptor
trapped, both trapped), each with its own transfer rate. Use it when you suspect
dye sticking rather than uniform restriction.

DWT is the only model that needs **FRET E**, because it averages *efficiencies*
rather than rates, and efficiency is non-linear in distance — so it has to know
where on the E(R) curve you are. Leaving E at its default while using DWT gives
a meaningless answer.

**Isotropic** — dipoles randomly but rigidly oriented, no reorientation at all.
Its mean is exactly 2/3 but its distribution is broad and peaked near zero. It
is the worst-case reference, not a model of a real sample.

## Reading the result

* **Mean κ²** near 2/3 does **not** mean the assumption is safe. A broad
  distribution with the right mean still spreads distances.
* **SD R_app/R_DA** is the number to quote. Under ~0.10 is the usual outcome for
  long flexible linkers, and it is why κ² = 2/3 has survived as a convention.
* **δ (deg)** near 0 with large order parameters is the bad case: both dyes
  restricted *and* mutually aligned.
* Changing **Bins** must not change the reported mean. If it does, the result is
  a binning artefact.

## Further reading

* [The orientation factor κ² and what it costs](docs/concepts/kappa2_orientation.md)
  — the models, the δ angle, and how the bound is derived.
* [Resonance energy transfer](docs/fundamentals/energy_transfer.md) — where κ²
  enters R₀ in the first place.
* [Photoselection, depolarization, and rotation](docs/fundamentals/polarization_and_rotation.md)
  — where r₀, r_∞ and S² come from.
* [Time-resolved fluorescence anisotropy](docs/concepts/anisotropy.md) — fitting
  the decays that produce the inputs above.
* [Guide: κ² distributions](docs/guides/61_kappa2_distribution.md)
* {cite}`dale1979` — that measured depolarization bounds κ² at all.
* {cite}`sindbert2011` — the order-parameter expression this tool evaluates.
