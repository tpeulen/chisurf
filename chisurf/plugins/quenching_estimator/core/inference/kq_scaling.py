"""Contact quenching rate kQ per dye, scaled from the reference chemistry by the titrations.

The reference PET chemistry gives a contact quenching rate :math:`k_Q^{ref}(r)` per quenching
residue type :math:`r`, made for dyes like the reference dye (AF488). Each dye gets its own
*relative* strengths from the free-dye titrations,

.. math:: k_Q(\\text{dye}, r) = k_Q^{ref}(r)\\,
          \\frac{\\max(K_{SV}(\\text{dye}, a), 0)/\\tau_0(\\text{dye}, a)}
               {\\max(K_{SV}(\\text{ref}, a), 0)/\\tau_0(\\text{ref}, a)},

with :math:`a` the titrated amino acid of residue :math:`r` (a residue that was not titrated
borrows one, e.g. Pro uses Trp). Only the positive part of a slope is quenching; a reference
with no quenching gives 0. The uncertainty is propagated numerically: each model titration
slope is moved by its posterior sd and the squared changes are summed
(:func:`kq_uncertainty`).

The residue list, the titrated-amino-acid map and the reference dye are declared in
``settings/analysis/measurement_columns.yaml``. Theory: ``docs/concepts/quenching_inference.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import columns as _columns


def _settings():
    """The kQ-scaling selections declared in the measurement-columns file.

    Returns
    -------
    dict
        The ``settings`` mapping.
    """
    return _columns.settings()


def textbook_kq(quenchers=None, settings=None):
    """Reference contact quenching rate of each quenching residue, from IMP.bff's chemistry.

    Parameters
    ----------
    quenchers : sequence of str, optional
        Residue names; the declared ``quenchers`` by default.
    settings : dict, optional
        Declared settings (``quenchers``, ``textbook_dye_radius``); the measurement-columns
        file by default.

    Returns
    -------
    dict
        ``{residue: kQ in 1/ns}`` at unit scale.
    """
    from ..dye_diffusion import default_amino_acid_interactions

    settings = settings or _settings()
    table = default_amino_acid_interactions(1.0, 1.0, settings["textbook_dye_radius"])
    return {r: float(table[r]["kQ"]) for r in (quenchers or settings["quenchers"])}


def kq_vector(dye, K, tau0, textbook, settings=None):
    """kQ at contact of every quenching residue for one dye.

    Parameters
    ----------
    dye : str
        The dye.
    K : dict
        ``{(dye, amino_acid): K_SV}`` titration slopes (1/M); must hold the dye's and the
        reference dye's.
    tau0 : dict
        ``{(dye, amino_acid): tau0}`` of the titrations (ns).
    textbook : dict
        ``{residue: reference kQ}`` (1/ns), e.g. :func:`textbook_kq`.
    settings : dict, optional
        Declared settings (``quenchers``, ``titrated``, ``reference_dye``); the
        measurement-columns file by default.

    Returns
    -------
    numpy.ndarray
        kQ (1/ns) in the order of the declared ``quenchers``.
    """
    settings = settings or _settings()
    ref_dye = settings["reference_dye"]
    out = []
    for residue in settings["quenchers"]:
        aa = settings["titrated"][residue]
        mine = max(K[(dye, aa)], 0.0) / tau0[(dye, aa)]
        ref = max(K[(ref_dye, aa)], 0.0) / tau0[(ref_dye, aa)]
        out.append(textbook[residue] * mine / ref if ref > 0 else 0.0)
    return np.array(out)


def model_keys(settings=None):
    """The titration slopes that enter the kQ vectors (and later the inverse fit).

    Parameters
    ----------
    settings : dict, optional
        Declared settings (``dyes``, ``model_titrations``); the measurement-columns file by
        default.

    Returns
    -------
    list of tuple
        ``(dye, amino_acid)`` pairs, dye-major in declared order.
    """
    settings = settings or _settings()
    return [(dye, aa) for dye in settings["dyes"] for aa in settings["model_titrations"]]


def kq_uncertainty(dye, K_mean, K_sd, tau0, textbook, settings=None):
    """Uncertainty of the kQ vector from the titration slope errors (numeric propagation).

    Parameters
    ----------
    dye : str
        The dye.
    K_mean, K_sd : dict
        ``{(dye, amino_acid): value}`` posterior mean and sd of K_SV (1/M).
    tau0 : dict
        ``{(dye, amino_acid): tau0}`` of the titrations (ns).
    textbook : dict
        ``{residue: reference kQ}`` (1/ns).
    settings : dict, optional
        Declared settings; the measurement-columns file by default.

    Returns
    -------
    numpy.ndarray
        sd of kQ (1/ns), same order as :func:`kq_vector`: each slope of :func:`model_keys` is
        moved by +1 sd in turn and the squared changes are summed.
    """
    settings = settings or _settings()
    base = kq_vector(dye, K_mean, tau0, textbook, settings)
    var = np.zeros(len(settings["quenchers"]))
    for key in model_keys(settings):
        shifted = dict(K_mean)
        shifted[key] += K_sd[key]
        var += (kq_vector(dye, shifted, tau0, textbook, settings) - base) ** 2
    return np.sqrt(var)


@dataclass(frozen=True)
class KqTable:
    """kQ at contact per dye and quenching residue, with its titration uncertainty.

    Attributes
    ----------
    dyes : tuple of str
        Row order.
    quenchers : tuple of str
        Column order (residue names).
    value, sd : numpy.ndarray
        Shape ``(len(dyes), len(quenchers))``, 1/ns.
    textbook : dict
        The reference kQ the table is scaled from.
    """

    dyes: tuple
    quenchers: tuple
    value: np.ndarray
    sd: np.ndarray
    textbook: dict

    def row(self, dye):
        """The kQ vector of one dye.

        Parameters
        ----------
        dye : str
            The dye.

        Returns
        -------
        dict
            ``{residue: kQ}``.
        """
        i = self.dyes.index(dye)
        return {r: float(v) for r, v in zip(self.quenchers, self.value[i])}

    def row_sd(self, dye):
        """The kQ uncertainty of one dye.

        Parameters
        ----------
        dye : str
            The dye.

        Returns
        -------
        dict
            ``{residue: sd}``.
        """
        i = self.dyes.index(dye)
        return {r: float(v) for r, v in zip(self.quenchers, self.sd[i])}

    def as_table(self):
        """The long-format declared table.

        Returns
        -------
        numpy.ndarray
            Declared table ``kq_contact``: one row per dye and residue.
        """
        rows = [
            dict(dye=d, quencher=r, kq=float(self.value[i, j]), kq_sd=float(self.sd[i, j]))
            for i, d in enumerate(self.dyes)
            for j, r in enumerate(self.quenchers)
        ]
        return _columns.make_table("kq_contact", rows)


def kq_table(posterior, dyes=None, textbook=None, settings=None):
    """kQ at contact for every dye from the titration posterior.

    Parameters
    ----------
    posterior : TitrationPosterior
        From :func:`~.titration.titration_posterior`.
    dyes : sequence of str, optional
        Row order; the declared ``dyes`` by default.
    textbook : dict, optional
        Reference kQ; :func:`textbook_kq` by default.
    settings : dict, optional
        Declared settings; the measurement-columns file by default.

    Returns
    -------
    KqTable
        Values and uncertainties.
    """
    settings = settings or _settings()
    dyes = tuple(dyes or settings["dyes"])
    textbook = textbook or textbook_kq(settings=settings)
    K_mean, K_sd, tau0 = posterior.k_mean(), posterior.k_sd(), posterior.tau0()
    value = np.array([kq_vector(d, K_mean, tau0, textbook, settings) for d in dyes])
    sd = np.array([kq_uncertainty(d, K_mean, K_sd, tau0, textbook, settings) for d in dyes])
    return KqTable(
        dyes=dyes,
        quenchers=tuple(settings["quenchers"]),
        value=value,
        sd=sd,
        textbook=dict(textbook),
    )
