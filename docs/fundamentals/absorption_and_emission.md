(fundamentals-absorption-emission)=
# Absorption, the excited state, and emission

## Absorption

The absorbance of a dilute solution follows the Beer–Lambert law,
$A = \log_{10}(I_0/I) = \varepsilon c l$, with the molar extinction coefficient
$\varepsilon$ in M⁻¹ cm⁻¹, concentration in molar, path length in cm.

The extinction coefficient is proportional to the squared magnitude of the
transition dipole moment. That dipole is a vector fixed in the molecular frame.
It determines which polarization the molecule absorbs, which is the origin of
anisotropy ({ref}`fundamentals-polarization`), and it appears again as one of
the two dipoles in the orientation factor for energy transfer
({ref}`fundamentals-energy-transfer`).

Absorption takes about $10^{-15}$ s, shorter than a vibrational period. The
nuclei do not move during the transition, so the molecule arrives in the excited
electronic state carrying its ground-state geometry — the Franck–Condon
principle. The overlap of the vibrational wavefunctions decides which excited
vibrational level is reached, and gives absorption bands their vibronic
structure.

Two consequences are used repeatedly later. Beer's law is linear only while the
sample is optically dilute: once absorbance across the excitation path exceeds
roughly 0.1 the beam is attenuated inside the sample, and intensity stops being
proportional to concentration ({ref}`fundamentals-instrumentation`). And an
acceptor bright enough to be useful has a large extinction coefficient, so it
also absorbs some light at the donor excitation wavelength. Direct acceptor
excitation is a property of the dye pair, not an alignment fault, and it has to
be corrected rather than avoided ({ref}`concept-accurate-fret`).

## What happens before emission

Vibrational relaxation and internal conversion bring the molecule to the lowest
vibrational level of $S_1$ within about $10^{-12}$ s, roughly four orders of
magnitude faster than it emits. Emission is therefore from a thermally
equilibrated $S_1$ regardless of which state absorbed the photon.

The competing exit is intersystem crossing to the triplet state $T_1$. It is
spin-forbidden and therefore slow, but $T_1$ is also slow to empty — microseconds
to seconds. On the fluorescence timescale a molecule that crosses over is simply
dark. This is the dominant microsecond bunching term in a correlation curve
({ref}`concept-fcs-correlation`) and a main source of single-molecule blinking
({ref}`fundamentals-quenching`).

The separations between these timescales are what make the methods work:

| Process | Timescale |
|---|---|
| Light absorption | $10^{-15}$ s |
| Vibrational relaxation | $10^{-12}$–$10^{-10}$ s |
| Internal conversion to $S_1$ | $\sim 10^{-12}$ s |
| Solvent relaxation around the excited dipole | $10^{-12}$–$10^{-10}$ s |
| Fluorescence | $10^{-10}$–$10^{-7}$ s |
| Rotational diffusion of a dye or small protein | $10^{-11}$–$10^{-8}$ s |
| Intersystem crossing | $10^{-10}$–$10^{-8}$ s |
| Translational diffusion through a confocal spot | $10^{-5}$–$10^{-3}$ s |
| Phosphorescence, triplet lifetime | $10^{-6}$–$10^{0}$ s |

A fluorescence lifetime sits between rotation and translation. Rotation, solvent
reorganization and energy transfer all occur during it and leave a mark;
diffusion does not.

## Stokes shift

Emission is red-shifted relative to absorption, because the molecule relaxes
vibrationally in $S_1$ before emitting and again in $S_0$ afterwards. That part
is intrinsic and present even in the vapour phase. A second part comes from the
excited state having a different dipole moment than the ground state, so the
solvent shell reorganizes around it before emission. Only the second part is
strongly environment-dependent, and it is what makes some dyes usable as
polarity sensors ({ref}`fundamentals-solvent`).

A large Stokes shift is what lets a dichroic mirror separate excitation from
emission. A small one has two costs: poor spectral separation, and energy
transfer between identical labels (homo-FRET) with the self-quenching that
follows. Past a few dyes per molecule, adding labels reduces brightness instead
of raising it.

## Emission does not depend on the excitation wavelength

Because internal conversion finishes long before emission, the emission spectrum
and the quantum yield are independent of the excitation wavelength — Kasha's
rule {cite}`kasha1950`, with the quantum-yield half usually credited to Vavilov. Changing the
excitation source does not by itself change a measured lifetime.

The exceptions all amount to more than one emitting species being present. A dye
with a titratable group has two ground-state forms with different spectra, so
changing the excitation wavelength changes which one is selected. A molecule
whose $\mathrm{p}K_a$ shifts on excitation can deprotonate during the
excited-state lifetime and emit as a different species. Emission from $S_2$ is
genuinely rare and does not occur in the fluorophores used here.

An emission spectrum that shifts with excitation wavelength is therefore a
warning worth acting on: a multi-exponential decay fit will absorb that
heterogeneity into apparent conformational states
({ref}`concept-tcspc-lifetime`).

## The mirror-image rule and its units

The vibrational spacings of $S_0$ and $S_1$ are usually similar, since
excitation does not greatly change the nuclear geometry. Absorption climbs the
ladder of $S_1$ and emission descends the ladder of $S_0$, so the two spectra
tend to mirror each other about the $0$–$0$ transition.

The mirror is of the $S_0 \to S_1$ band alone. Higher absorption bands have no
counterpart in emission, which is why a dye with a structured near-UV absorption
can show a single smooth emission band and still be behaving normally.

The symmetry is also only exact in the right units — between
$\varepsilon(\bar\nu)/\bar\nu$ and $F(\bar\nu)/\bar\nu^3$ plotted against
wavenumber.

:::{warning}
A spectrum recorded per unit wavelength and the same spectrum recorded per unit
wavenumber have different shapes and different peak positions, because
$\mathrm{d}\lambda$ and $\mathrm{d}\bar\nu$ are not proportional. The overlap
integral that sets the Förster radius is defined on one convention. A spectrum
stored in the other convention changes $R_0$ without any error being raised
({ref}`fundamentals-energy-transfer`).
:::

Deviations that are not a units problem — a broad, structureless, strongly
shifted emission under a structured absorption — indicate emission from a
relaxed or chemically distinct state: excited-state proton transfer,
charge-transfer character, or excimer formation.

## See also

- Next: {ref}`fundamentals-lifetime-quantum-yield`.
- Concepts that rest on this page: {ref}`concept-tcspc-lifetime` ·
  {ref}`concept-fret` · {ref}`concept-imaging-flim-phasor`.
- Literature: {cite}`kasha1950` for the excitation-independence rule;
  {cite}`lakowicz2006` for the rest.
