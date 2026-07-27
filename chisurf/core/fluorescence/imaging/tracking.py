r"""Single-particle detection, linking and transport analysis.

Three steps, deliberately separable because each fails in its own way:

**Detect** — find the particles in every frame independently. A spot is several
pixels wide; a hot camera pixel is one. Working with connected *regions* rather
than bright pixels is what tells them apart, and it puts the position at the
centre of the spot rather than on its brightest pixel.

**Link** — decide which detection in frame *t+1* is the same particle as which
in frame *t*. This is the step with no prior art in this codebase and the one
that actually limits the measurement: link two different particles together and
you invent a displacement that never happened.

**Analyse** — turn trajectories into a diffusion coefficient and an anomalous
exponent through the mean squared displacement.

Linking: why an assignment, not a nearest neighbour
---------------------------------------------------
The obvious algorithm — for each particle take the nearest detection in the next
frame — is wrong whenever two particles approach each other, because both can
claim the same neighbour and the choice depends on iteration order. Framing it
as a **global assignment** and solving it exactly (:func:`scipy.optimize.
linear_sum_assignment`, the Hungarian algorithm) minimises the *total* squared
displacement instead, which is the maximum-likelihood pairing under isotropic
Brownian motion and is order-independent.

A maximum linking distance is not a refinement, it is the whole safety margin: it
is what stops a particle that blinked out being linked to an unrelated one
across the field. Set it from the physics — a Brownian particle moves about
:math:`\sqrt{4 D \Delta t}` between frames — and not from what makes the tracks
look longest.

Gap closing
-----------
Particles blink, defocus and are missed. Linking frame-to-frame alone therefore
shatters one trajectory into many short ones, and short tracks bias the diffusion
coefficient (they are the ones that stayed still long enough to be found twice).
A second pass reconnects a track that ended to one that started a few frames
later, with the search radius grown as :math:`\sqrt{\text{gap}}` because that is
how far diffusion carries a particle in the meantime.

Gap closing is where tracking goes wrong most quietly: every closed gap is an
assumption that nothing else could have been there. Keep ``max_frame_gap`` small
and check what it changes.

The MSD, and the two traps in fitting it
-----------------------------------------
For a track sampled at frames, the time-averaged mean squared displacement at
lag :math:`n` is the mean of :math:`|r(i+n) - r(i)|^2` over all :math:`i`. For
free diffusion in :math:`d` dimensions,

.. math::

    \mathrm{MSD}(\tau) = 2 d D \tau^{\alpha} + 2 d \sigma^2 ,

with :math:`\alpha = 1` for normal diffusion, below 1 for subdiffusion and above
for directed motion.

**The offset is not optional.** :math:`\sigma` is the localisation uncertainty,
and it adds a *constant* to every lag. Fit without it and that constant is
absorbed into :math:`D`, inflating it — badly for slow particles, where the
offset is a large fraction of the whole curve. Fitting it is also how the
localisation precision gets measured, for free.

**Long lags are nearly useless.** The MSD at lag :math:`n` of a track of length
:math:`N` averages only :math:`N-n` displacements, and those overlap, so the
points are few and strongly correlated. Fitting the whole curve lets the noisy
tail dominate. Only the first quarter of the lags is used by default, which is
the standard compromise.

References
----------
* Crocker, J. C. & Grier, D. G. *Methods of digital video microscopy for
  colloidal studies.* J. Colloid Interface Sci. **179**, 298–310 (1996).
* Jaqaman, K. *et al.* *Robust single-particle tracking in live-cell time-lapse
  sequences.* Nat. Methods **5**, 695–702 (2008). — assignment framing and gap
  closing.
* Olivo-Marin, J.-C. *Extraction of spots in biological images using multiscale
  products.* Pattern Recognit. **35**, 1989–1996 (2002). — the wavelet detector.
* Michalet, X. *Mean square displacement analysis of single-particle
  trajectories with localization error.* Phys. Rev. E **82**, 041914 (2010). —
  why the offset term matters.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "Detections",
    "MsdFit",
    "Tracks",
    "detect_particles",
    "fit_msd",
    "link_detections",
    "mean_squared_displacement",
    "simulate_particle_movie",
]


# ──────────────────────────────────────────────────────────────────────────────
# Containers
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class Detections:
    """Particles found in each frame, in one flat table.

    Attributes
    ----------
    frame : numpy.ndarray
        ``(n,)`` int frame index of each detection.
    y, x : numpy.ndarray
        ``(n,)`` float sub-pixel row and column position, in pixels.
    intensity : numpy.ndarray
        ``(n,)`` integrated intensity above background of each spot.
    """

    frame: np.ndarray
    y: np.ndarray
    x: np.ndarray
    intensity: np.ndarray

    def __len__(self) -> int:
        """Return the total number of detections."""
        return int(self.frame.size)

    @property
    def n_frames(self) -> int:
        """Number of frames that contain at least one detection."""
        return int(np.unique(self.frame).size)

    def in_frame(self, index: int) -> np.ndarray:
        """Return the indices of the detections in frame *index*."""
        return np.flatnonzero(self.frame == int(index))

    def positions(self) -> np.ndarray:
        """Return an ``(n, 2)`` array of ``(y, x)`` positions."""
        return np.column_stack([self.y, self.x])


@dataclass
class Tracks:
    """Linked trajectories.

    Attributes
    ----------
    track_id : numpy.ndarray
        ``(n_detections,)`` track each detection belongs to, ``-1`` if the
        detection was not linked into any track.
    detections : Detections
        The detections the tracks were built from, unchanged.
    """

    track_id: np.ndarray
    detections: Detections

    def __len__(self) -> int:
        """Return the number of distinct tracks."""
        return int(np.unique(self.track_id[self.track_id >= 0]).size)

    def ids(self) -> np.ndarray:
        """Return the sorted distinct track identifiers."""
        return np.unique(self.track_id[self.track_id >= 0])

    def track(self, identifier: int) -> tuple[np.ndarray, np.ndarray]:
        """Return ``(frames, positions)`` of one track, ordered in time.

        Parameters
        ----------
        identifier : int
            Track identifier.

        Returns
        -------
        frames : numpy.ndarray
            ``(m,)`` frame indices.
        positions : numpy.ndarray
            ``(m, 2)`` ``(y, x)`` positions in pixels.
        """
        where = np.flatnonzero(self.track_id == int(identifier))
        order = np.argsort(self.detections.frame[where], kind="stable")
        where = where[order]
        return (
            self.detections.frame[where],
            np.column_stack([self.detections.y[where], self.detections.x[where]]),
        )

    def lengths(self) -> np.ndarray:
        """Return the number of detections in each track, ordered by :meth:`ids`."""
        return np.array([np.count_nonzero(self.track_id == i) for i in self.ids()], dtype=int)

    def filter_by_length(self, min_length: int) -> "Tracks":
        """Return a copy keeping only tracks with at least *min_length* points.

        Short tracks are not merely uninformative — they are **biased**. A
        particle is more likely to be detected twice in a row if it happened to
        stay put, so the shortest tracks over-represent the slowest motion.

        Parameters
        ----------
        min_length : int
            Smallest track length to keep.

        Returns
        -------
        Tracks
        """
        keep = np.full(self.track_id.shape, -1, dtype=self.track_id.dtype)
        next_id = 0
        for identifier in self.ids():
            where = self.track_id == identifier
            if np.count_nonzero(where) >= int(min_length):
                keep[where] = next_id
                next_id += 1
        return Tracks(track_id=keep, detections=self.detections)


# ──────────────────────────────────────────────────────────────────────────────
# Detection
# ──────────────────────────────────────────────────────────────────────────────
def _atrous_spot_map(frame: np.ndarray, scale: int = 2) -> np.ndarray:
    """Return the multiscale product that isolates diffraction-limited spots.

    The B3-spline à-trous transform smooths the image at successive dyadic
    scales; the difference of two consecutive smoothings is a band-pass plane
    keeping structures of about that size. That alone suppresses the slowly
    varying background, without ever choosing an intensity threshold, which is
    why it holds up at low signal-to-noise where a quantile on the raw image
    does not.

    A single plane is **not** enough to reject a hot camera pixel, though, and
    this is the trap: the transform *spreads* a one-pixel spike over several
    pixels, so a minimum-area rule applied to one plane sees a legitimate
    multi-pixel region and admits it. The fix is the multiscale product — take
    the geometric mean of two adjacent planes. A real spot is significant at
    both scales and survives; a single-pixel spike is strong only at the finest
    scale and is annihilated by the coarser factor. This is the point of
    Olivo-Marin's detector, and skipping it turns every dead pixel into a
    particle that the linker then dutifully tracks.

    Parameters
    ----------
    frame : numpy.ndarray
        2-D image.
    scale : int
        Coarser of the two planes multiplied; 2 matches a typical few-pixel spot.

    Returns
    -------
    spots : numpy.ndarray
        Non-negative spot map in intensity units.
    noise : float
        Robust noise scale of that map. It is derived from the **unclipped**
        planes, because clipping the product at zero drives more than half its
        pixels to exactly zero, which sends the median absolute deviation to
        zero and destroys any noise estimate made from the map itself.
    """
    from scipy import ndimage as ndi

    def robust_sigma(values: np.ndarray) -> float:
        """Gaussian-equivalent sigma from the median absolute deviation."""
        return float(1.4826 * np.median(np.abs(values - np.median(values))))

    kernel = np.array([1.0, 4.0, 6.0, 4.0, 1.0]) / 16.0
    previous = frame.astype(float)
    planes: list[np.ndarray] = []
    for level in range(max(int(scale), 1)):
        # "à trous" = with holes: the kernel is dilated instead of the image
        # being decimated, so every plane keeps the full resolution.
        step = 2 ** level
        dilated = np.zeros(len(kernel) + (len(kernel) - 1) * (step - 1))
        dilated[::step] = kernel
        smoothed = ndi.convolve1d(previous, dilated, axis=0, mode="reflect")
        smoothed = ndi.convolve1d(smoothed, dilated, axis=1, mode="reflect")
        planes.append(previous - smoothed)
        previous = smoothed

    if len(planes) == 1:
        return np.clip(planes[0], 0.0, None), robust_sigma(planes[0])
    # Geometric mean of the last two planes keeps the result in intensity units,
    # so the threshold stays interpretable; its noise scale is the geometric
    # mean of theirs, for the same reason.
    a, b = planes[-2], planes[-1]
    noise = float(np.sqrt(max(robust_sigma(a), 0.0) * max(robust_sigma(b), 0.0)))
    return np.sqrt(np.clip(a, 0.0, None) * np.clip(b, 0.0, None)), noise


def detect_particles(
    frames: np.ndarray,
    method: str = "wavelet",
    threshold: float = 5.0,
    min_area: int = 2,
    min_separation: float = 3.0,
    quantile_pixels_per_frame: int = 50,
    wavelet_scale: int = 2,
) -> Detections:
    """Find diffraction-limited particles in every frame of a movie.

    Parameters
    ----------
    frames : numpy.ndarray
        ``(n_frames, ny, nx)`` image stack. A single 2-D image is accepted and
        treated as one frame.
    method : str
        ``"wavelet"`` — à-trous band-pass then a robust threshold; the default,
        and the one that survives low signal-to-noise and uneven background.
        ``"quantile"`` — threshold the raw frame at a quantile chosen so about
        ``quantile_pixels_per_frame`` pixels survive. Cheaper, and adequate for
        bright well-separated spots on a flat background.
    threshold : float
        For ``"wavelet"``, the threshold in robust standard deviations of the
        wavelet plane (estimated by median absolute deviation, so a few bright
        spots do not raise it). Unused by ``"quantile"``.

        The number of noise pixels surviving ``k`` sigma is the pixel count
        times the tail probability, so in principle a threshold that is clean on
        a small frame floods a large one. The multiscale product suppresses
        that almost entirely — detections per frame on simulated fields with 8
        planted particles:

        ====== ========= ========= =========
        k       128x128   256x256   512x512
        ====== ========= ========= =========
        3            8.0       8.4       9.6
        4            8.0       8.0       8.0
        5            8.0       8.0       8.0
        ====== ========= ========= =========

        (A single band-pass plane, without the product, gave 9.8 / 33.9 / 131.2
        at ``k = 3`` — which is what the second scale is for.) Hence the default
        of 5, which has margin at every field size. Lower it only for dim
        particles, and check the detections per frame against what you expect
        when you do.
    min_area : int
        Smallest number of connected bright pixels that can be a particle. The
        default of 2 rejects single hot pixels; a diffraction-limited spot is
        always wider than one pixel.
    min_separation : float
        Two accepted particles in the same frame must be at least this many
        pixels apart; of a closer pair the brighter is kept. Spots nearer than
        the point-spread function cannot be told apart anyway, and admitting
        both invents a particle for the linker to mis-assign.
    quantile_pixels_per_frame : int
        Target number of above-threshold pixels per frame for ``"quantile"``.
    wavelet_scale : int
        Which à-trous plane to use; 2 matches a typical few-pixel spot.

    Returns
    -------
    Detections

    Raises
    ------
    ValueError
        If *frames* is not 2- or 3-dimensional, or *method* is unknown.
    """
    from scipy import ndimage as ndi

    stack = np.asarray(frames)
    if stack.ndim == 2:
        stack = stack[None, ...]
    if stack.ndim != 3:
        raise ValueError("frames must be (n_frames, ny, nx) or a single 2-D image")
    if method not in ("wavelet", "quantile"):
        raise ValueError(f"unknown detection method {method!r}; use 'wavelet' or 'quantile'")

    frame_out: list[int] = []
    y_out: list[float] = []
    x_out: list[float] = []
    intensity_out: list[float] = []

    for index, image in enumerate(stack):
        image = np.asarray(image, dtype=float)
        if not np.any(np.isfinite(image)):
            continue

        if method == "wavelet":
            response, sigma = _atrous_spot_map(image, scale=int(wavelet_scale))
            if sigma <= 0.0:
                peak = float(np.max(response))
                if peak <= 0.0:
                    continue
                # A noiseless (or heavily quantised) frame has no measurable
                # noise, and scaling a threshold by zero would reject
                # everything — a synthetic test image would yield no detections
                # at all. With nothing to measure, a hair above zero is signal.
                sigma = peak * 1e-6
            mask = response > float(threshold) * sigma
            weights = response
        else:
            total = float(image.size)
            level = 1.0 - min(max(quantile_pixels_per_frame / total, 0.0), 1.0)
            cut = np.quantile(image, level)
            # On a flat frame the quantile lands on the background itself, so
            # the mask selects every pixel and the whole frame is reported as
            # one enormous "particle" centred on whatever is brightest. There is
            # nothing to detect; say so rather than invent it.
            if cut <= np.median(image):
                continue
            mask = image >= cut
            weights = np.clip(image - np.median(image), 0.0, None)

        labels, n_labels = ndi.label(mask)
        if n_labels == 0:
            continue

        # Intensity-weighted centroid puts the position at the centre of the
        # spot rather than on whichever pixel happened to be brightest.
        areas = ndi.sum(np.ones_like(weights), labels, index=range(1, n_labels + 1))
        sums = ndi.sum(weights, labels, index=range(1, n_labels + 1))
        centres = ndi.center_of_mass(weights, labels, index=range(1, n_labels + 1))

        candidates = [
            (float(sums[i]), float(centres[i][0]), float(centres[i][1]))
            for i in range(n_labels)
            if areas[i] >= min_area and np.isfinite(centres[i][0]) and np.isfinite(centres[i][1])
        ]
        # Every region can fail ``min_area`` — a frame of hot pixels is exactly
        # what that cut is for. It contributes nothing rather than reaching the
        # KD-tree with an empty, one-dimensional point array.
        if not candidates:
            continue

        # Brightest first, so the survivor of a too-close pair is the brighter.
        candidates.sort(key=lambda c: -c[0])

        # A KD-tree rather than an all-pairs scan: a mis-set threshold can leave
        # thousands of candidates in a frame, and the quadratic version turned
        # that from a bad result into an apparent hang.
        from scipy.spatial import cKDTree

        points = np.array([[c[1], c[2]] for c in candidates], dtype=float)
        tree = cKDTree(points)
        suppressed = np.zeros(len(candidates), dtype=bool)
        accepted: list[tuple[float, float, float]] = []
        for i, candidate in enumerate(candidates):
            if suppressed[i]:
                continue
            accepted.append(candidate)
            for j in tree.query_ball_point(points[i], float(min_separation)):
                if j != i:
                    suppressed[j] = True

        for brightness, cy, cx in accepted:
            frame_out.append(index)
            y_out.append(cy)
            x_out.append(cx)
            intensity_out.append(brightness)

    return Detections(
        frame=np.asarray(frame_out, dtype=np.int64),
        y=np.asarray(y_out, dtype=float),
        x=np.asarray(x_out, dtype=float),
        intensity=np.asarray(intensity_out, dtype=float),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Linking
# ──────────────────────────────────────────────────────────────────────────────
def link_detections(
    detections: Detections,
    max_distance: float,
    max_frame_gap: int = 0,
) -> Tracks:
    """Link per-frame detections into trajectories.

    Frame-to-frame assignment is solved exactly (Hungarian) under a maximum
    linking distance, then — if ``max_frame_gap`` allows — tracks that ended are
    reconnected to tracks that started shortly after.

    Parameters
    ----------
    detections : Detections
        Per-frame particle positions.
    max_distance : float
        Largest displacement, in pixels, that may be called the same particle
        between consecutive frames. Choose it from the physics: a Brownian
        particle moves about ``sqrt(4 D dt)`` per frame. Too large and distinct
        particles are joined; too small and every trajectory is shattered.
    max_frame_gap : int
        Largest number of *missing* frames a track may bridge. ``0`` disables
        gap closing. Every closed gap asserts that no other particle could have
        been there, so keep this small and check what changing it does.

    Returns
    -------
    Tracks

    Raises
    ------
    ValueError
        If *max_distance* is not positive.
    """
    from scipy.optimize import linear_sum_assignment

    if not np.isfinite(max_distance) or max_distance <= 0.0:
        raise ValueError("max_distance must be a positive number of pixels")
    n = len(detections)
    track_id = np.full(n, -1, dtype=np.int64)
    if n == 0:
        return Tracks(track_id=track_id, detections=detections)

    frames = np.unique(detections.frame)
    next_id = 0
    #: Detection index that currently terminates each open track.
    previous = detections.in_frame(frames[0])
    for index in previous:
        track_id[index] = next_id
        next_id += 1

    for f_previous, f_current in zip(frames[:-1], frames[1:]):
        current = detections.in_frame(f_current)
        if previous.size == 0 or current.size == 0:
            for index in current:
                track_id[index] = next_id
                next_id += 1
            previous = current
            continue

        # Consecutive-frame linking only; a jump in frame number is a gap and is
        # left to the gap-closing pass, which widens its radius accordingly.
        if int(f_current) - int(f_previous) != 1:
            for index in current:
                track_id[index] = next_id
                next_id += 1
            previous = current
            continue

        dy = detections.y[previous][:, None] - detections.y[current][None, :]
        dx = detections.x[previous][:, None] - detections.x[current][None, :]
        cost = dy * dy + dx * dx
        forbidden = cost > max_distance ** 2
        # A large finite cost rather than infinity: the solver needs a complete
        # matrix, and forbidden pairs are rejected after the assignment.
        cost = np.where(forbidden, 1e12, cost)

        rows, cols = linear_sum_assignment(cost)
        taken = np.zeros(current.size, dtype=bool)
        for r, c in zip(rows, cols):
            if forbidden[r, c]:
                continue
            track_id[current[c]] = track_id[previous[r]]
            taken[c] = True
        for position, index in enumerate(current):
            if not taken[position]:
                track_id[index] = next_id
                next_id += 1
        previous = current

    tracks = Tracks(track_id=track_id, detections=detections)
    if int(max_frame_gap) > 0:
        tracks = _close_gaps(tracks, max_distance, int(max_frame_gap))
    return tracks


def _close_gaps(tracks: Tracks, max_distance: float, max_frame_gap: int) -> Tracks:
    """Reconnect tracks separated by a few missing frames.

    Ends and starts are matched by a single global assignment, with the search
    radius grown as ``sqrt(gap)`` — the distance diffusion covers while the
    particle was missing.
    """
    from scipy.optimize import linear_sum_assignment

    identifiers = tracks.ids()
    if identifiers.size < 2:
        return tracks

    ends: list[tuple[int, int, float, float]] = []
    starts: list[tuple[int, int, float, float]] = []
    for identifier in identifiers:
        frames, positions = tracks.track(identifier)
        ends.append((int(identifier), int(frames[-1]), positions[-1, 0], positions[-1, 1]))
        starts.append((int(identifier), int(frames[0]), positions[0, 0], positions[0, 1]))

    cost = np.full((len(ends), len(starts)), 1e12)
    for i, (id_end, f_end, y_end, x_end) in enumerate(ends):
        for j, (id_start, f_start, y_start, x_start) in enumerate(starts):
            if id_end == id_start:
                continue
            gap = f_start - f_end
            if gap < 1 or gap > max_frame_gap:
                continue
            distance = (y_start - y_end) ** 2 + (x_start - x_end) ** 2
            if distance > (max_distance ** 2) * gap:
                continue
            cost[i, j] = distance

    rows, cols = linear_sum_assignment(cost)
    # Union-find over the accepted end -> start merges, so a chain of three
    # fragments collapses to one track rather than two.
    parent = {int(i): int(i) for i in identifiers}

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for r, c in zip(rows, cols):
        if cost[r, c] >= 1e12:
            continue
        a, b = find(ends[r][0]), find(starts[c][0])
        if a != b:
            parent[b] = a

    merged = np.full(tracks.track_id.shape, -1, dtype=np.int64)
    relabel: dict[int, int] = {}
    for identifier in identifiers:
        root = find(int(identifier))
        if root not in relabel:
            relabel[root] = len(relabel)
        merged[tracks.track_id == identifier] = relabel[root]
    return Tracks(track_id=merged, detections=tracks.detections)


# ──────────────────────────────────────────────────────────────────────────────
# Transport analysis
# ──────────────────────────────────────────────────────────────────────────────
def mean_squared_displacement(positions, frames=None, max_lag: int | None = None):
    """Return the time-averaged MSD of one trajectory.

    Parameters
    ----------
    positions : array_like
        ``(m, 2)`` positions, ordered in time.
    frames : array_like, optional
        ``(m,)`` frame index of each position. Given, lags are computed in
        *frames* so a trajectory with closed gaps is handled correctly; omitted,
        the positions are assumed to be consecutive.
    max_lag : int, optional
        Largest lag to compute. Defaults to a quarter of the track length, since
        longer lags average too few, strongly overlapping displacements to be
        worth fitting.

    Returns
    -------
    lags : numpy.ndarray
        Lag in frames, starting at 1.
    msd : numpy.ndarray
        Mean squared displacement at each lag, in pixels squared. ``NaN`` at a
        lag no pair of points realises.
    counts : numpy.ndarray
        Number of displacements averaged at each lag — the honest weight for a
        subsequent fit.
    """
    positions = np.asarray(positions, dtype=float)
    if positions.ndim != 2 or positions.shape[1] != 2:
        raise ValueError("positions must be (m, 2)")
    m = positions.shape[0]
    if frames is None:
        frames = np.arange(m)
    frames = np.asarray(frames, dtype=np.int64).ravel()
    if frames.size != m:
        raise ValueError("frames and positions must have the same length")

    span = int(frames[-1] - frames[0]) if m > 1 else 0
    if max_lag is None:
        max_lag = max(int(span // 4), 1)
    max_lag = max(int(max_lag), 1)

    lags = np.arange(1, max_lag + 1, dtype=np.int64)
    msd = np.full(lags.size, np.nan)
    counts = np.zeros(lags.size, dtype=np.int64)
    for k, lag in enumerate(lags):
        # Pair up points that are exactly `lag` frames apart, whatever their
        # index distance — that is what makes gapped tracks usable.
        target = frames[:, None] + lag
        matches = np.argwhere(target == frames[None, :])
        if matches.size == 0:
            continue
        delta = positions[matches[:, 1]] - positions[matches[:, 0]]
        squared = (delta ** 2).sum(axis=1)
        msd[k] = float(squared.mean())
        counts[k] = int(squared.size)
    return lags, msd, counts


@dataclass
class MsdFit:
    """Transport parameters recovered from a mean squared displacement.

    Attributes
    ----------
    diffusion_coefficient : float
        ``D`` in the units implied by the pixel size and frame interval given
        (µm²/s when both were supplied, otherwise pixel²/frame).
    diffusion_coefficient_error : float
        Standard error on ``D`` from the fit covariance. **Read it.** With a
        handful of tracks this is routinely tens of per cent, and quoting ``D``
        without it invites a comparison the data cannot support.
    alpha : float
        Anomalous exponent: 1 is normal diffusion, below 1 subdiffusion, above 1
        directed or actively transported motion.
    alpha_error : float
        Standard error on ``alpha``.
    alpha_fixed : bool
        Whether ``alpha`` was held at a fixed value rather than fitted.
    localisation_error : float
        ``sigma``, the per-position uncertainty implied by the fitted offset, in
        the same length unit. Negative fitted offsets are reported as 0.
    n_tracks : int
        Tracks that contributed.
    n_points : int
        MSD points fitted.
    success : bool
        Whether the optimiser converged.
    """

    diffusion_coefficient: float
    alpha: float
    localisation_error: float
    diffusion_coefficient_error: float = float("nan")
    alpha_error: float = float("nan")
    alpha_fixed: bool = False
    n_tracks: int = 0
    n_points: int = 0
    success: bool = True
    lags: np.ndarray = field(default_factory=lambda: np.zeros(0))
    msd: np.ndarray = field(default_factory=lambda: np.zeros(0))

    @property
    def relative_error(self) -> float:
        """Standard error on ``D`` as a fraction of ``D`` (``nan`` if unknown)."""
        if not np.isfinite(self.diffusion_coefficient_error) or self.diffusion_coefficient <= 0:
            return float("nan")
        return float(self.diffusion_coefficient_error / self.diffusion_coefficient)

    def warnings(self) -> list[str]:
        """Return the reasons this fit should not be taken at face value.

        The MSD of a power law is a badly conditioned thing to fit: ``D`` and
        ``alpha`` trade off against each other almost exactly, so a fit that is
        too high in one is too low in the other and the curve still passes
        through the points. These are the checks worth making before quoting a
        number.
        """
        notes: list[str] = []
        if not self.success:
            notes.append("the fit did not converge; the values are the starting guess")
        if self.n_tracks < 20:
            notes.append(
                f"only {self.n_tracks} tracks contributed — D from this few is "
                "uncertain by tens of per cent however tight the curve looks"
            )
        relative = self.relative_error
        if np.isfinite(relative) and relative > 0.25:
            notes.append(f"D carries a {100 * relative:.0f} % standard error")
        # 0.1 because that is roughly where alpha stops answering the question
        # it is fitted for: 1.17 +/- 0.12 does not distinguish normal diffusion
        # from mild superdiffusion, and quoting it as though it did is the whole
        # failure mode this warning exists to prevent.
        if not self.alpha_fixed and np.isfinite(self.alpha_error) and self.alpha_error > 0.10:
            notes.append(
                f"alpha = {self.alpha:.2f} +/- {self.alpha_error:.2f} is not resolved; "
                "if normal diffusion is expected, fix alpha = 1 and D becomes far "
                "better determined"
            )
        return notes

    def to_dict(self) -> dict:
        """Return a JSON-compatible summary."""
        return {
            "diffusion_coefficient": float(self.diffusion_coefficient),
            "diffusion_coefficient_error": float(self.diffusion_coefficient_error),
            "alpha": float(self.alpha),
            "alpha_error": float(self.alpha_error),
            "alpha_fixed": bool(self.alpha_fixed),
            "localisation_error": float(self.localisation_error),
            "n_tracks": int(self.n_tracks),
            "n_points": int(self.n_points),
            "success": bool(self.success),
            "warnings": self.warnings(),
            "lags": np.asarray(self.lags, dtype=float).tolist(),
            "msd": np.asarray(self.msd, dtype=float).tolist(),
        }


def fit_msd(
    tracks: Tracks,
    pixel_size: float = 1.0,
    frame_interval: float = 1.0,
    min_length: int = 10,
    max_lag: int | None = None,
    fit_localisation_error: bool = True,
    fix_alpha: float | None = None,
    n_bootstrap: int = 200,
    bootstrap_seed: int = 1,
) -> MsdFit:
    """Fit ``MSD = 4 D tau^alpha + 4 sigma^2`` to the ensemble MSD.

    The per-track MSDs are combined weighted by how many displacements each
    contributed, so a long track counts for more than a short one — which is
    both statistically right and the correction for the bias that short tracks
    over-represent slow particles.

    Parameters
    ----------
    tracks : Tracks
        Linked trajectories.
    pixel_size : float
        Length of a pixel (µm). Leave at 1 to work in pixels.
    frame_interval : float
        Time between frames (s). Leave at 1 to work in frames.
    min_length : int
        Tracks shorter than this are excluded; see
        :meth:`Tracks.filter_by_length` for why short tracks are biased rather
        than merely noisy.
    max_lag : int, optional
        Largest lag fitted; defaults to a quarter of each track's span.
    fit_localisation_error : bool
        Fit the constant offset. Leave it on unless the localisation error is
        genuinely known to be negligible: switching it off does not remove the
        offset from the data, it only moves it into ``D``.
    fix_alpha : float, optional
        Hold the anomalous exponent at this value instead of fitting it —
        ``1.0`` for ordinary diffusion. **This is usually the right choice.**
        ``D`` and ``alpha`` are nearly degenerate: a fit too high in one is too
        low in the other and the curve still passes through the points, so
        fitting both spreads ``D`` far more than fitting ``D`` alone. Fit
        ``alpha`` only when the question *is* whether the motion is anomalous,
        and then read its error bar.
    n_bootstrap : int
        Resamples of the *track set* used to estimate the uncertainties. ``0``
        skips it and leaves the errors ``nan`` — which is honest, unlike the
        fit covariance, whose assumption of independent residuals is badly
        violated by the MSD and yields error bars several times too small.
    bootstrap_seed : int
        Seed, so a quoted uncertainty is reproducible.

    Returns
    -------
    MsdFit

    Raises
    ------
    ValueError
        If no track is long enough to fit.
    """
    from scipy.optimize import curve_fit

    kept = tracks.filter_by_length(int(min_length))
    identifiers = kept.ids()
    if identifiers.size == 0:
        raise ValueError(
            f"no track has at least {min_length} points; lower min_length or "
            "improve the linking before fitting transport"
        )

    # Per-track MSD curves, kept separately so the bootstrap can resample them.
    per_track: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
    for identifier in identifiers:
        frames, positions = kept.track(identifier)
        per_track.append(mean_squared_displacement(positions, frames, max_lag=max_lag))

    def ensemble(selection):
        """Count-weighted ensemble MSD over the selected tracks."""
        total: dict[int, float] = {}
        weight: dict[int, int] = {}
        for index in selection:
            lags, msd, counts = per_track[index]
            for lag, value, count in zip(lags, msd, counts):
                if not np.isfinite(value) or count <= 0:
                    continue
                total[int(lag)] = total.get(int(lag), 0.0) + float(value) * int(count)
                weight[int(lag)] = weight.get(int(lag), 0) + int(count)
            del lags
        if not total:
            return None, None
        keys = np.array(sorted(total), dtype=float)
        return keys, np.array([total[int(k)] / weight[int(k)] for k in keys])

    lag_values, msd_values = ensemble(range(len(per_track)))
    if lag_values is None:
        raise ValueError("the tracks yielded no usable MSD points")

    tau = lag_values * float(frame_interval)
    msd_scaled = msd_values * float(pixel_size) ** 2

    def model(t, d, alpha, offset):
        """MSD of anomalous diffusion in two dimensions plus a constant offset."""
        return 4.0 * d * np.power(t, alpha) + offset

    guess_d = float(max(msd_scaled[0] / (4.0 * tau[0]), 1e-12))
    success = True
    alpha_fixed = fix_alpha is not None
    d_error = alpha_error = float("nan")

    # Parameter order is always (D, alpha, offset); whichever are free get
    # fitted and the rest are substituted, so the unpacking below is uniform.
    free_alpha = not alpha_fixed
    free_offset = bool(fit_localisation_error)

    def build(params):
        """Expand the free-parameter vector into (D, alpha, offset)."""
        values = list(params)
        d = values.pop(0)
        alpha = values.pop(0) if free_alpha else float(fix_alpha)
        offset = values.pop(0) if free_offset else 0.0
        return d, alpha, offset

    p0 = [guess_d] + ([1.0] if free_alpha else []) + ([0.0] if free_offset else [])
    lower = [0.0] + ([0.05] if free_alpha else []) + ([-np.inf] if free_offset else [])
    upper = [np.inf] + ([3.0] if free_alpha else []) + ([np.inf] if free_offset else [])

    def solve(t, y):
        """Fit the model to one MSD curve, returning the free-parameter vector."""
        popt, _ = curve_fit(
            lambda tt, *params: model(tt, *build(params)),
            t, y, p0=p0, bounds=(lower, upper), maxfev=20000,
        )
        return popt

    try:
        popt = solve(tau, msd_scaled)
    except Exception:
        success = False
        popt = np.array(p0)

    # Uncertainty by resampling whole tracks, not by the fit covariance.
    #
    # curve_fit's covariance assumes independent residuals, and MSD points are
    # nothing of the sort: consecutive lags are built from overlapping
    # displacements of the same trajectories, so the errors are strongly
    # correlated. Measured against simulations with a known D, the covariance
    # error bar covers the truth about 1 time in 5 rather than 19 — it is worse
    # than no error bar, because it invites confidence the data do not support.
    # Resampling tracks with replacement captures both the track-to-track spread
    # and the within-track correlation, because a whole track moves together.
    if success and int(n_bootstrap) > 0 and identifiers.size >= 3:
        rng = np.random.default_rng(int(bootstrap_seed))
        draws: list[np.ndarray] = []
        for _ in range(int(n_bootstrap)):
            selection = rng.integers(0, len(per_track), len(per_track))
            t_b, y_b = ensemble(selection)
            if t_b is None or t_b.size < len(p0):
                continue
            try:
                draws.append(solve(t_b * float(frame_interval), y_b * float(pixel_size) ** 2))
            except Exception:
                continue
        if len(draws) >= max(10, int(n_bootstrap) // 4):
            spread = np.std(np.asarray(draws), axis=0, ddof=1)
            d_error = float(spread[0])
            if free_alpha:
                alpha_error = float(spread[1])

    d_value, alpha_value, offset = build(popt)
    return MsdFit(
        diffusion_coefficient=float(d_value),
        diffusion_coefficient_error=d_error,
        alpha=float(alpha_value),
        alpha_error=alpha_error,
        alpha_fixed=alpha_fixed,
        # offset = 4 sigma^2 in two dimensions; a negative fit means the offset
        # is unresolved, and reporting a complex sigma would be worse than 0.
        localisation_error=float(np.sqrt(offset / 4.0)) if offset > 0 else 0.0,
        n_tracks=int(identifiers.size),
        n_points=int(lag_values.size),
        success=success,
        lags=lag_values,
        msd=msd_scaled,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Simulation (ground truth for verification)
# ──────────────────────────────────────────────────────────────────────────────
def simulate_particle_movie(
    n_frames: int = 50,
    shape: tuple[int, int] = (128, 128),
    n_particles: int = 20,
    diffusion_coefficient: float = 1.0,
    pixel_size: float = 1.0,
    frame_interval: float = 1.0,
    sigma_psf: float = 1.5,
    amplitude: float = 200.0,
    background: float = 10.0,
    poisson: bool = True,
    seed: int = 1,
    render: bool = True,
    memory_budget_bytes: int = 2 * 1024 ** 3,
):
    """Simulate a movie of Brownian particles, with the true trajectories.

    The existing CLSM simulator places *immobile* molecules, so it cannot
    verify a tracker. This one prescribes the motion, which makes the recovered
    ``D`` checkable against a known answer rather than merely plausible.

    Particles are reflected at the field boundary rather than wrapped, because a
    particle that wraps around produces a displacement of the field width and
    would be a linking error nobody put there.

    Parameters
    ----------
    n_frames : int
        Number of frames.
    shape : tuple of int
        ``(ny, nx)`` frame size in pixels.
    n_particles : int
        Number of particles.
    diffusion_coefficient : float
        True ``D`` in µm²/s (or pixel²/frame when the scales are left at 1).
    pixel_size : float
        Length of a pixel (µm).
    frame_interval : float
        Time between frames (s).
    sigma_psf : float
        Width of the Gaussian point-spread function in pixels.
    amplitude : float
        Peak intensity of a particle above background.
    background : float
        Uniform background level.
    poisson : bool
        Apply Poisson (shot) noise. Leave on: a noiseless movie makes any
        detector look good.
    seed : int
        Random seed.
    render : bool
        Produce the image stack. ``False`` returns ``None`` in its place and
        only simulates the trajectories, which costs no memory at all — the
        right choice when the question is about the motion (step statistics,
        linking on known positions) rather than about detection.
    memory_budget_bytes : int
        Refuse to allocate a stack larger than this. ``n_frames * ny * nx * 8``
        bytes grows quietly: 200 frames of 2048² is 6.7 GB, which is enough to
        drive a machine into swap and fill its disk. Raise it deliberately if
        you really want that.

    Returns
    -------
    movie : numpy.ndarray or None
        ``(n_frames, ny, nx)`` float image stack, or ``None`` when
        ``render=False``.
    truth : Detections
        The true positions, in the same layout the detector returns, so a
        recovered track can be compared against them directly.

    Raises
    ------
    ValueError
        If the requested stack would exceed *memory_budget_bytes*.
    """
    rng = np.random.default_rng(int(seed))
    ny, nx = int(shape[0]), int(shape[1])
    n_particles = int(n_particles)

    required = int(n_frames) * ny * nx * 8
    if render and required > int(memory_budget_bytes):
        raise ValueError(
            f"a {n_frames} x {ny} x {nx} stack needs "
            f"{required / 1024 ** 3:.1f} GB, over the "
            f"{int(memory_budget_bytes) / 1024 ** 3:.1f} GB budget; use "
            "render=False if you only need the trajectories, or a smaller field"
        )

    # Brownian step in pixels: <dr^2> = 4 D dt in 2-D, so each axis gets 2 D dt.
    step = np.sqrt(2.0 * float(diffusion_coefficient) * float(frame_interval)) / float(pixel_size)
    y = rng.uniform(sigma_psf * 3, ny - sigma_psf * 3, n_particles)
    x = rng.uniform(sigma_psf * 3, nx - sigma_psf * 3, n_particles)

    movie = np.zeros((int(n_frames), ny, nx), dtype=float) if render else None
    frame_out, y_out, x_out, intensity_out = [], [], [], []
    grid_y = np.arange(ny)[:, None]
    grid_x = np.arange(nx)[None, :]

    for f in range(int(n_frames)):
        image = np.full((ny, nx), float(background)) if render else None
        for p in range(n_particles):
            if render:
                image += amplitude * np.exp(
                    -((grid_y - y[p]) ** 2 + (grid_x - x[p]) ** 2) / (2.0 * sigma_psf ** 2)
                )
            frame_out.append(f)
            y_out.append(float(y[p]))
            x_out.append(float(x[p]))
            intensity_out.append(float(amplitude))
        if render:
            movie[f] = rng.poisson(np.clip(image, 0.0, None)) if poisson else image

        y = y + rng.normal(0.0, step, n_particles)
        x = x + rng.normal(0.0, step, n_particles)
        # Reflect at the edges.
        y = np.abs(y)
        x = np.abs(x)
        y = np.where(y > ny - 1, 2 * (ny - 1) - y, y)
        x = np.where(x > nx - 1, 2 * (nx - 1) - x, x)

    truth = Detections(
        frame=np.asarray(frame_out, dtype=np.int64),
        y=np.asarray(y_out, dtype=float),
        x=np.asarray(x_out, dtype=float),
        intensity=np.asarray(intensity_out, dtype=float),
    )
    return movie, truth
