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

``c`` the quencher contacts interpolated linearly in the contact-distance change
:math:`\\delta` and mixed between crystal and rotamer side chains by :math:`\\lambda`,
:math:`k_Q` the dye's contact rates, :math:`w` the water quenching rate of a fully exposed dye
and :math:`e` the water exposure. The lifetime there is
:math:`\\tau(x) = 1/(1/(\\tau_0 + \\Delta\\tau_{shield}(1 - e)) + k)`. A position is visible
with :math:`1/(1 + (\\tau_{min}/\\tau)^4)` times the static channel
:math:`\\exp(-e^{\\ln \\text{static}}\\, c(x; \\delta_{static}, \\lambda) \\cdot k_Q)`; the
predicted lifetime is the visible-weighted mean of :math:`\\tau`.

Positions identical in every feature are kept once with their count (about 15 times fewer
rows, the same sums). The arithmetic, including the float32 contact products, is the MalE
prototype's, so a prototype site table gives its numbers bit for bit.

Parameter names (``theta`` keys): ``ln_s_<group>`` per declared group (``ln_s_common`` is
the stickiness prior's centre and does not enter here), ``ln_scale``, ``delta``, ``lam``,
``ln_static``, ``delta_static``, optional ``dtau_shield``, and ``kq`` (contact rates, 1/ns, in
the declared ``quenchers`` order). Theory: ``docs/concepts/quenching_inference.md``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import columns as _columns
from . import site_table as _site_table


class Site:
    """One dye at one site: predicts the measured lifetime.

    Parameters
    ----------
    table : SiteTable or str or pathlib.Path
        The site table, or the path of a stored one (also a MalE prototype cache file).
    settings_ : dict, optional
        Declared settings (``groups``, ``radius_offsets``, ``tau_min``, ``visibility_power``);
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
        contacts = np.asarray(table.contacts).astype(np.float32)
        exposure = np.clip(np.asarray(table.exposure).astype(float), 0, 1)
        features = np.concatenate([n_group, contacts.reshape(len(n), -1), exposure[:, None]], 1)
        _, first, count = np.unique(features, axis=0, return_index=True, return_counts=True)
        self.n_group, self.exposure, self.count = n_group[first], exposure[first], count.astype(float)
        self.C = contacts[first]

    @property
    def n_positions(self):
        """Voxels of the site (the sum of the row counts)."""
        return int(self.count.sum())

    def _contacts(self, delta, lam, kq):
        """Quenching rate per row before the quench scale (1/ns), float32.

        Parameters
        ----------
        delta : float
            Contact-distance change (A), interpolated between the tested offsets.
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
        c = (1 - w) * self.C[:, :, i, :] + w * self.C[:, :, i + 1, :]
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
        k = np.exp(theta["ln_scale"]) * self._contacts(theta["delta"], theta["lam"], theta["kq"])
        k = k + water * self.exposure
        tau0 = tau0 + theta.get("dtau_shield", 0.0) * (1.0 - self.exposure)
        tau = 1.0 / (1.0 / tau0 + k)
        seen = 1.0 / (1.0 + (self.tau_min / tau) ** self.visibility_power)
        seen = seen * np.exp(
            -np.exp(theta["ln_static"]) * self._contacts(theta["delta_static"], theta["lam"], theta["kq"])
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
