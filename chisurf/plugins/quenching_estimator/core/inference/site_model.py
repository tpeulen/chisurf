"""The site model: a dye's measured lifetime at one site, from its site table and a parameter set.

The dye's positions are the voxels of the site table. At equilibrium a position is occupied
in proportion to

.. math:: p(x) \\propto \\prod_g s_g^{-n_g(x)},

with :math:`s_g \\in (0, 1]` the slow factor (stickiness) of residue group :math:`g` and
:math:`n_g(x)` the residues of that group within the slow radius. This is the stationary
state a long Brownian walk would reach; the walk itself does not equilibrate in the sticky
regime, so the inverse fit uses this closed form. The walk and the grid diffusion solve stay
in the forward simulator.

At each position the quenching rate is

.. math:: k(x) = e^{\\ln \\text{scale}}\\, c(x; \\delta, \\lambda) \\cdot k_Q + w\\, e(x),

``c`` the quencher contacts weighted by the declared ``rate_model``, mixed between crystal
and rotamer side chains by :math:`\\lambda`. ``kernel`` (distance-continuous): a quencher at
:math:`u = r - R_q` beyond its reference contact distance counts
:math:`f(u) = 1` for :math:`u \\le 0` and :math:`e^{-u/\\ell}` beyond, averaged over the
table's distance-histogram bins (:meth:`Site.kernel_weights`). ``contact_shell`` (the MalE
prototype's): the contact counts at :math:`R_q + \\delta`, read over the tested offsets
(declared ``delta_interpolation``: ``bspline``, the uniform cubic B-spline with the tested
values as control points, or ``linear``, the prototype's). :math:`k_Q` is the dye's contact
rates, :math:`w` the water quenching rate of a fully exposed dye and :math:`e` the water
exposure. The lifetime there is
:math:`\\tau(x) = 1/(1/(\\tau_0 + \\Delta\\tau_{shield}(1 - e)) + k)`. A position is visible
with :math:`1/(1 + (\\tau_{min}/\\tau)^4)` times the static channel
:math:`\\exp(-e^{\\ln \\text{static}}\\, c(x; \\delta_{static}, \\lambda) \\cdot k_Q)` (``kernel``: the
kernel offset by :math:`\\delta_{static} \\le 0`); the
predicted lifetime is the visible-weighted mean of :math:`\\tau`.

Positions identical in every feature are kept once with their count (about 15 times fewer
rows, the same sums; with the kernel the rows are matched by a double 64-bit hash of their
features and sparse distances, :func:`unique_sparse_rows`). Under ``contact_shell`` the
arithmetic, including the float32 contact products, is the MalE prototype's, so a prototype
site table gives its numbers bit for bit.

Parameter names (``theta`` keys): ``ln_s_<group>`` per declared group (``ln_s_common`` is
the stickiness prior's centre and does not enter here), ``ln_scale``, ``delta``
(contact_shell) or ``ln_decay_length`` (kernel), ``lam``,
``ln_static``, ``delta_static``, optional ``dtau_shield``, and ``kq`` (contact rates, 1/ns, in
the declared ``quenchers`` order). Theory: ``docs/concepts/quenching_inference.md``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import columns as _columns
from . import site_table as _site_table


def unique_rows(features):
    """Distinct rows of a feature matrix, as ``np.unique(features, axis=0)`` orders them.

    ``np.unique(axis=0)`` sorts a structured view field by field, which takes seconds for a
    site table (8 s for 131 187 x 106 under load). A stable lexicographic ``lexsort`` over the
    columns gives the same order, the same first index of each distinct row (the smallest
    one, as ``np.unique``'s stable sort) and the same counts, about 20 times faster.

    Parameters
    ----------
    features : numpy.ndarray
        ``(n, k)`` floats.

    Returns
    -------
    tuple
        ``(first, count)``: index of each distinct row's first occurrence, in ``np.unique``'s
        lexicographic order, and how often it occurs.
    """
    features = np.asarray(features)
    if len(features) == 0:
        return np.zeros(0, int), np.zeros(0, int)
    order = np.lexsort(features.T[::-1])
    ranked = features[order]
    new = np.ones(len(ranked), bool)
    new[1:] = np.any(ranked[1:] != ranked[:-1], axis=1)
    starts = np.flatnonzero(new)
    return order[starts], np.diff(np.append(starts, len(ranked)))


_HASH_MASK = np.uint64(0xFFFFFFFFFFFFFFFF)


def _mix(x, seed):
    """SplitMix64 of uint64 values (vectorised, wrapping)."""
    with np.errstate(over="ignore"):
        z = (np.asarray(x, np.uint64) + np.uint64(seed) * np.uint64(0x9E3779B97F4A7C15))
        z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return z ^ (z >> np.uint64(31))


def unique_sparse_rows(dense, rows, columns, weights):
    """Distinct rows of a dense feature block joined with a sparse one.

    Each row is hashed twice (two independent 64-bit SplitMix sums over its dense values and
    its sparse ``(column, weight)`` entries, order free), and rows with equal hash pairs are one
    row; a collision of both 64-bit hashes is not a practical concern.

    Parameters
    ----------
    dense : numpy.ndarray
        ``(n, k)`` floats.
    rows, columns, weights : numpy.ndarray
        Sparse entries (rows ascending).

    Returns
    -------
    tuple
        ``(first, count, keep, new_row)``: the first row of each distinct row, its
        multiplicity, a mask of the sparse entries that belong to a first row, and their new
        row index.
    """
    dense = np.ascontiguousarray(dense, np.float64)
    n = len(dense)
    bits = dense.view(np.uint64)
    entry = (np.asarray(columns, np.uint64) << np.uint64(32)) | np.asarray(
        np.asarray(weights, np.float32).view(np.uint32), np.uint64)
    hashes = []
    for seed in (1, 2):
        h = np.zeros(n, np.uint64)
        with np.errstate(over="ignore"):
            for j in range(bits.shape[1]):
                h = h + _mix(bits[:, j] ^ np.uint64(j + 1), seed)
            e = _mix(entry, seed + 10)
            np.add.at(h, np.asarray(rows, np.int64), e)
        hashes.append(h)
    pair = np.stack(hashes, 1).copy().view([("a", np.uint64), ("b", np.uint64)]).ravel()
    _, first, count = np.unique(pair, return_index=True, return_counts=True)
    new_of_row = np.full(n, -1, np.int64)
    new_of_row[first] = np.arange(len(first))
    mapped = new_of_row[np.asarray(rows, np.int64)]
    keep = mapped >= 0
    return first, count, keep, mapped[keep]


class Site:
    """One dye at one site: predicts the measured lifetime.

    Parameters
    ----------
    table : SiteTable or str or pathlib.Path
        The site table, or the path of a stored one (also a MalE prototype cache file).
    settings_ : dict, optional
        Declared settings (``groups``, ``radius_offsets``, ``delta_interpolation``, ``tau_min``,
        ``visibility_power``);
        ``settings/analysis/site_model.yaml`` by default.

    Attributes
    ----------
    n_group : numpy.ndarray
        ``(m, n_groups)`` residues per group of each distinct row.
    exposure : numpy.ndarray
        ``(m,)`` water exposure, clipped to [0, 1].
    count : numpy.ndarray
        ``(m,)`` voxels per distinct row.
    C : numpy.ndarray
        ``(m, n_quenchers, n_offsets, 2)`` float32 contacts.
    groups : list of str
        Group names, the column order of ``n_group``.
    """

    def __init__(self, table, settings_=None):
        s = settings_ or _site_table.settings()
        if isinstance(table, (str, Path)):
            table = _site_table.load_site_table(table)
        self.table = table
        self.groups = list(s["groups"])
        self.radius_offsets = [float(v) for v in s["radius_offsets"]]
        self.tau_min = float(s["tau_min"])
        self.visibility_power = s["visibility_power"]
        residues = _site_table.residue_types(s)
        n = np.asarray(table.neighbours).astype(float)
        if n.shape[1] != len(residues):
            raise ValueError(f"site table has {n.shape[1]} residue columns, settings {len(residues)}")
        index = {r: i for i, r in enumerate(residues)}
        n_group = np.stack(
            [n[:, [index[r] for r in rs]].sum(1) for rs in s["groups"].values()], 1
        )
        exposure = np.clip(np.asarray(table.exposure).astype(float), 0, 1)
        self.rate_model = str(s["rate_model"])
        if self.rate_model == "contact_shell":
            contacts = np.asarray(table.contacts).astype(np.float32)
            features = np.concatenate([n_group, contacts.reshape(len(n), -1), exposure[:, None]],
                                      1)
            first, count = unique_rows(features)
            self.C = contacts[first]
        elif self.rate_model == "kernel":
            d = table.distances
            if d is None:
                raise ValueError("the kernel rate model needs a site table with quencher distances "
                                 f"(schema {_site_table.SCHEMA}); {getattr(table, 'path', None)} "
                                 "has none (a prototype table: declare rate_model contact_shell)")
            first, count, keep, new_row = unique_sparse_rows(
                np.concatenate([n_group, exposure[:, None]], 1), d.rows, d.columns, d.weights)
            n_sources = 2
            n_qs = len(s["quenchers"]) * n_sources
            qs = d.columns[keep].astype(np.int64) // d.n_bins          # quencher * 2 + source
            bins = (d.columns[keep] % d.n_bins).astype(np.int64)
            weight = d.weights[keep].astype(np.float64)
            lo, hi = d.edges()
            # Bins at or below u = 0 (a bin edge) are inside the dynamic kernel's contact
            # distance (weight 1); only the static channel, offset by delta_static <= 0, reads
            # them otherwise. The tail (u > 0) is the same exp(-u / l) for both channels, up to
            # the static channel's factor exp(delta_static / l). Each entry is indexed by its
            # row and by (bin, quencher, source), so one gather of a (bin x quencher-source)
            # table and one bincount over the rows give a channel.
            inner = hi[bins] <= 0.0
            self._inner_sum = np.bincount(new_row[inner] * n_qs + qs[inner], weights=weight[inner],
                                          minlength=len(first) * n_qs).reshape(len(first), n_qs)
            self._inner = (new_row[inner], bins[inner] * n_qs + qs[inner], weight[inner])
            self._tail = (new_row[~inner], bins[~inner] * n_qs + qs[~inner], weight[~inner])
            if np.any(bins[~inner] == 0):
                raise ValueError("the distance histogram's underflow bin lies above u = 0")
            self._edges = d.edges()
            self._step = float(d.step)
            self._n_quenchers = len(s["quenchers"])
            self.C = None
        else:
            raise ValueError(f"rate_model must be kernel or contact_shell, not {self.rate_model!r}")
        self.n_group, self.exposure, self.count = n_group[first], exposure[first], count.astype(float)
        self.delta_interpolation = str(s["delta_interpolation"])
        if self.delta_interpolation not in ("linear", "bspline"):
            raise ValueError(f"delta_interpolation must be linear or bspline, not "
                             f"{self.delta_interpolation!r}")
        steps = np.diff(self.radius_offsets)
        if self.delta_interpolation == "bspline" and not np.allclose(steps, steps[0]):
            raise ValueError("the bspline delta interpolation needs evenly spaced radius_offsets")

    @property
    def n_positions(self):
        """Voxels of the site (the sum of the row counts)."""
        return int(self.count.sum())

    def _rates(self, theta, static=False):
        """Quenching rate per row before the quench scale or static strength (1/ns).

        Parameters
        ----------
        theta : dict
            Parameter set: ``delta`` / ``delta_static`` (contact_shell) or ``ln_decay_length``
            and ``delta_static`` (kernel), ``lam``, ``kq``.
        static : bool, optional
            The static channel's (offset ``delta_static``) instead of the dynamic one's.

        Returns
        -------
        numpy.ndarray
        """
        kq = np.asarray(theta["kq"], float)
        if self.rate_model == "contact_shell":
            key = ("shell", float(theta["delta_static"] if static else theta["delta"]),
                   float(theta["lam"]), kq.tobytes())
        else:
            key = ("kernel", float(theta["delta_static"]), float(theta["ln_decay_length"]),
                   float(theta["lam"]), kq.tobytes())
        cache = self.__dict__.setdefault("_rate_cache", {})
        if key not in cache:
            if self.rate_model == "contact_shell":
                cache[key] = self._contacts(key[1], theta["lam"], theta["kq"])
            else:
                cache[key] = self._kernel_contacts(float(theta["delta_static"]),
                                                   float(np.exp(theta["ln_decay_length"])),
                                                   theta["lam"], kq)
            while len(cache) > 4:
                cache.pop(next(iter(cache)))
        out = cache[key]
        return out if self.rate_model == "contact_shell" else out[:, 1 if static else 0]

    def kernel_weights(self, offset, decay_length):
        """The kernel averaged over every histogram bin.

        ``f(u) = 1`` for ``u <= offset`` and ``exp(-(u - offset) / decay_length)`` beyond,
        averaged over each bin of u (exactly, for quenchers spread evenly in the bin); the
        underflow bin counts in full.

        Parameters
        ----------
        offset : float
            A.
        decay_length : float
            A.

        Returns
        -------
        numpy.ndarray
            One weight per bin.
        """
        lo, hi = self._edges
        h, length = self._step, float(decay_length)
        a = np.where(np.isfinite(lo), lo, hi - h)
        out = np.ones(len(lo))
        beyond = a >= offset
        out[beyond] = length * (np.exp(-(a[beyond] - offset) / length)
                                - np.exp(-(hi[beyond] - offset) / length)) / h
        mixed = (a < offset) & (hi > offset)
        out[mixed] = ((offset - a[mixed])
                      + length * (1.0 - np.exp(-(hi[mixed] - offset) / length))) / h
        out[0] = 1.0
        return out

    def _kernel_contacts(self, static_offset, decay_length, lam, kq):
        """Kernel-weighted quencher count times the contact rates, per row (1/ns).

        Parameters
        ----------
        static_offset : float
            The static channel's kernel offset (A, declared at most 0); the dynamic channel's
            is 0.
        decay_length : float
            A (:meth:`kernel_weights`).
        lam : float
            0 crystal side chains, 1 rotamers.
        kq : sequence of float
            Contact rate per quencher (1/ns).

        Returns
        -------
        numpy.ndarray
            ``(rows, 2)``: dynamic, static.
        """
        kq = np.asarray(kq, float)
        coef = np.stack([(1 - lam) * kq, lam * kq], 1).ravel()          # per quencher, source
        n = len(self.count)
        row, index, weight = self._tail
        table = np.outer(self.kernel_weights(0.0, decay_length), coef).ravel()
        tail = np.bincount(row, weights=weight * table[index], minlength=n)
        dynamic = self._inner_sum @ coef + tail
        table_s = np.outer(self.kernel_weights(static_offset, decay_length), coef).ravel()
        if static_offset > 0.0:
            # beyond the declared range (a finite-difference step past delta_static's upper
            # bound): inside bins count in full, the tail is read with its own weights
            static = self._inner_sum @ coef + np.bincount(row, weights=weight * table_s[index],
                                                         minlength=n)
        else:
            row_s, index_s, weight_s = self._inner
            static = np.bincount(row_s, weights=weight_s * table_s[index_s], minlength=n)
            static += np.exp(static_offset / decay_length) * tail
        return np.stack([dynamic, static], 1)

    def _contacts(self, delta, lam, kq):
        """Quenching rate per row before the quench scale (1/ns), float32.

        Parameters
        ----------
        delta : float
            Contact-distance change (A), read over the tested offsets (linear or cubic
            B-spline, see ``delta_interpolation``); clamped to the tested range.
        lam : float
            0 crystal side chains, 1 rotamers.
        kq : sequence of float
            Contact rate per quencher (1/ns).

        Returns
        -------
        numpy.ndarray
        """
        offsets = self.radius_offsets
        x = float(np.interp(delta, offsets, np.arange(len(offsets))))
        i = min(int(np.floor(x)), len(offsets) - 2)
        w = x - i
        if self.delta_interpolation == "linear":
            c = (1 - w) * self.C[:, :, i, :] + w * self.C[:, :, i + 1, :]
        else:
            # uniform cubic B-spline, the tested values as control points (the end values
            # repeated beyond the range): twice continuously differentiable, a weighted mean
            # of four neighbouring offsets, so contacts stay >= 0 and grow with delta
            t = np.float32(w)
            weights = ((1 - t) ** 3 / 6, (3 * t**3 - 6 * t**2 + 4) / 6,
                       (-3 * t**3 + 3 * t**2 + 3 * t + 1) / 6, t**3 / 6)
            last = len(offsets) - 1
            c = sum(wk * self.C[:, :, min(max(i - 1 + k, 0), last), :]
                    for k, wk in enumerate(weights))
        c = (1 - lam) * c[:, :, 0] + lam * c[:, :, 1]
        return c @ np.asarray(kq, np.float32)

    def weights(self, theta):
        """Equilibrium occupancy of each row, p ~ count * prod_g s_g^(-n_g).

        Parameters
        ----------
        theta : dict
            Parameter set (``ln_s_<group>``).

        Returns
        -------
        numpy.ndarray
            Normalised to 1.
        """
        log_p = -self.n_group @ np.array([theta[f"ln_s_{g}"] for g in self.groups])
        p = self.count * np.exp(log_p - log_p.max())
        return p / p.sum()

    def seen(self, theta, tau0, water=0.0):
        """Lifetime and visible share of each row.

        Parameters
        ----------
        theta : dict
            Parameter set.
        tau0 : float
            Free-dye lifetime (ns).
        water : float, optional
            Water quenching rate of a fully exposed dye (1/ns).

        Returns
        -------
        tau : numpy.ndarray
            ns.
        seen : numpy.ndarray
            1 visible, 0 dark.
        """
        k = np.exp(theta["ln_scale"]) * self._rates(theta)
        k = k + water * self.exposure
        tau0 = tau0 + theta.get("dtau_shield", 0.0) * (1.0 - self.exposure)
        tau = 1.0 / (1.0 / tau0 + k)
        seen = 1.0 / (1.0 + (self.tau_min / tau) ** self.visibility_power)
        seen = seen * np.exp(
            -np.exp(theta["ln_static"]) * self._rates(theta, static=True)
        )
        return tau, seen

    def lifetime(self, theta, tau0, water=0.0):
        """Predicted lifetime, dark fraction and visible water exposure.

        Parameters
        ----------
        theta : dict
            Parameter set.
        tau0 : float
            Free-dye lifetime (ns).
        water : float, optional
            Water quenching rate of a fully exposed dye (1/ns).

        Returns
        -------
        tuple of float
            ``(tau_x, dark_fraction, visible_exposure)``.
        """
        p = self.weights(theta)
        tau, seen = self.seen(theta, tau0, water)
        visible = (p * seen).sum()
        return (
            float((p * seen * tau).sum() / visible),
            float(1 - visible),
            float((p * seen * self.exposure).sum() / visible),
        )

    def exposure_profile(self, theta, tau0, water=0.0):
        """Water exposure over the visible dye's time and over the reachable positions.

        Parameters
        ----------
        theta : dict
        tau0 : float
        water : float, optional

        Returns
        -------
        dict
            ``exposure`` and ``weight`` per row (the visible-time histogram's data),
            ``visible`` (time-weighted mean e), ``reachable`` (count-weighted mean e) and
            ``dark_fraction``.
        """
        time = self.weights(theta)
        _, seen = self.seen(theta, tau0, water)
        weight = time * seen / (time * seen).sum()
        return dict(
            exposure=self.exposure,
            weight=weight,
            visible=float((weight * self.exposure).sum()),
            reachable=float(np.average(self.exposure, weights=self.count)),
            dark_fraction=float(1 - (time * seen).sum()),
        )


def predict(points, theta, tau0):
    """Predicted lifetimes of several (site, water) points at one parameter set.

    Parameters
    ----------
    points : sequence of (Site, float)
        The site and the water quenching rate of each measured lifetime.
    theta : dict
        Parameter set.
    tau0 : float
        Free-dye lifetime (ns).

    Returns
    -------
    numpy.ndarray
        ns.
    """
    return np.array([site.lifetime(theta, tau0, water)[0] for site, water in points])


def predictions_table(rows):
    """The declared ``site_predictions`` table.

    Parameters
    ----------
    rows : sequence of dict
        Keys: the declared columns (``dye``, ``solvent``, ``state``, ``site``,
        ``linker_length``, ``water``, ``tau0``, ``lifetime``, ``dark_fraction``,
        ``visible_exposure``).

    Returns
    -------
    numpy.ndarray
    """
    return _columns.make_table("site_predictions", rows, _site_table.SITE_MODEL)


def exposure_table(rows):
    """The declared ``site_exposure`` table.

    Parameters
    ----------
    rows : sequence of dict
        Keys ``site``, ``state``, ``reachable``, ``visible``, ``dark_fraction``.

    Returns
    -------
    numpy.ndarray
    """
    return _columns.make_table("site_exposure", rows, _site_table.SITE_MODEL)


class SiteLibrary:
    """Site models of a data set, built once per (state, site, linker length).

    Parameters
    ----------
    structures : dict, optional
        ``{state: structure path}``; the shipped MalE structures by default.
    settings_ : dict, optional
        Declared settings.
    cache_dir : str or pathlib.Path, optional
        Site-table cache folder.
    """

    def __init__(self, structures=None, settings_=None, cache_dir=None):
        self.settings = settings_ or _site_table.settings()
        self.structures = structures or {
            state: _site_table.male_structure(state, self.settings)
            for state in self.settings["structures"]
        }
        self.cache_dir = cache_dir
        self._sites = {}

    def table(self, state, site, linker_length):
        """The site table (cached on disk).

        Parameters
        ----------
        state : str
        site : int
        linker_length : float

        Returns
        -------
        SiteTable
        """
        return _site_table.site_table(
            self.structures[state], int(site), float(linker_length),
            settings_=self.settings, cache_dir=self.cache_dir,
        )

    def site(self, state, site, linker_length):
        """The site model (kept in memory).

        Parameters
        ----------
        state : str
        site : int
        linker_length : float

        Returns
        -------
        Site
        """
        key = (state, int(site), round(float(linker_length), 6))
        if key not in self._sites:
            self._sites[key] = Site(self.table(state, site, linker_length), self.settings)
        return self._sites[key]

    def points(self, rows, linker_length=None, water=None):
        """``(Site, water)`` per measured row.

        Parameters
        ----------
        rows : numpy.ndarray or sequence of dict
            With fields ``state``, ``site`` and (unless *linker_length* is given) ``dye``.
        linker_length : float, optional
            One length for every row; else the declared ``linker_lengths[dye]``.
        water : sequence of float or float, optional
            Water rate per row (or one for all); 0 by default.

        Returns
        -------
        list of (Site, float)
        """
        rows = list(rows)
        if water is None or np.isscalar(water):
            water = [0.0 if water is None else float(water)] * len(rows)
        out = []
        for row, w in zip(rows, water):
            length = linker_length
            if length is None:
                length = self.settings["linker_lengths"][str(row["dye"])]
            out.append((self.site(str(row["state"]), int(row["site"]), float(length)), float(w)))
        return out
