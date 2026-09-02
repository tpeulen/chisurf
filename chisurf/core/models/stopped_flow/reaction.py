"""A kinetic reaction scheme fitted against a stopped-flow trace.

The measurement is a mixing experiment: two solutions are combined and the
fluorescence is followed while the system relaxes. What is fitted is therefore
not a sum of exponentials but the **scheme** itself — a set of reactions with
rate constants, integrated numerically onto the data's time axis, with each
species contributing its own brightness.

That is the whole reason this is a model rather than a parse equation: a scheme
with a bimolecular step, or one where a species is consumed and reformed, has no
closed-form relaxation, and writing down the sum of exponentials that
approximates it is exactly the step that loses the rate constants.
"""
from __future__ import annotations

import json

import numpy as np

import chisurf.core.fitting
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.math.reaction.continuous import ReactionSystem
from chisurf.core.models.model import ModelCurve


class ReactionModel(ReactionSystem, ModelCurve):

    """Fit a kinetic scheme (species, reactions, rate constants) to a trace.

    The hand-written predecessor (``ReactionWidget``) was **abstract** — it never
    implemented ``update_model`` — so selecting it in the model menu could only
    raise. Functional compatibility with it is therefore the bar rather than file
    compatibility: everything it offered is here, and it computes.
    """

    name = "Reaction-System"
    view_spec_file = "reaction.view.json"

    def __init__(self, fit: chisurf.core.fitting.fit.Fit, **kwargs):
        """Initialize the reaction model with a two-species default scheme.

        Parameters
        ----------
        fit : chisurf.core.fitting.fit.Fit
            The fit this model belongs to.
        **kwargs
            Additional keyword arguments forwarded to the base classes. An
            optional ``parameter`` mapping (``{"reactions": [...],
            "species": [...]}``) replaces the default scheme.
        """
        ReactionSystem.__init__(self, **kwargs)
        ModelCurve.__init__(self, fit, **kwargs)

        self._scaling = FittingParameter(
            name="scaling", label_text="scaling", value=1.0,
            lb=0.0, ub=float("inf"), bounds_on=False, fixed=False,
        )
        self._background = FittingParameter(
            name="background", label_text="background", value=0.0,
            lb=float("-inf"), ub=float("inf"), bounds_on=False, fixed=False,
        )
        self._timeshift = FittingParameter(
            name="timeshift", label_text="timeshift", value=0.0,
            lb=float("-inf"), ub=float("inf"), bounds_on=False, fixed=True,
        )
        #: Rescale the model to the data's integral inside the fit window.
        self.autoscale = False
        #: Row dict of the reaction currently selected in the reaction table.
        self.selected_reaction = None

        scheme = kwargs.get("parameter")
        if isinstance(scheme, dict):
            self.set_scheme(scheme)
        else:
            # A scheme with no reaction integrates to a flat line, so the editor
            # would open on nothing to look at. The simplest scheme that relaxes
            # is one reversible step between two species.
            self.set_scheme(self.default_scheme())

        self.find_parameters()

    # -- the scheme -----------------------------------------------------

    @staticmethod
    def default_scheme() -> dict:
        """Return the scheme a new model starts from: ``A ⇌ B``."""
        return {
            "reactions": [
                {"educts": [0], "products": [1], "educt_stoichiometry": [1],
                 "product_stoichometry": [1], "rate": 1.0},
                {"educts": [1], "products": [0], "educt_stoichiometry": [1],
                 "product_stoichometry": [1], "rate": 0.1},
            ],
            "species": [
                {"species": "A", "concentration": 1.0, "brightness": 1.0},
                {"species": "B", "concentration": 0.0, "brightness": 0.5},
            ],
        }

    def set_scheme(self, scheme: dict) -> None:
        """Replace the whole scheme from a mapping.

        Parameters
        ----------
        scheme : dict
            ``{"reactions": [...], "species": [...]}``; each reaction is the
            keyword mapping :meth:`ReactionSystem.add_reaction` takes, each
            species carries ``species``, ``concentration`` and ``brightness``.
        """
        self.clear()
        self._species_names = []
        for reaction in scheme.get("reactions", ()):
            ReactionSystem.add_reaction(self, **reaction)
        for species in scheme.get("species", ()):
            self.add_species(**species)
        self.selected_reaction = None

    @property
    def scheme(self) -> dict:
        """The current scheme as the mapping :meth:`set_scheme` accepts."""
        reactions = [
            {
                "educts": list(e),
                "products": list(p),
                "educt_stoichiometry": [float(x) for x in es],
                "product_stoichometry": [float(x) for x in ps],
                "rate": float(r),
            }
            for e, p, es, ps, r in self.reactions
        ]
        species = [
            {
                "species": name,
                "concentration": float(c.value),
                "brightness": float(q.value),
            }
            for name, c, q in zip(
                self.species_names, self._initial_concentrations, self._species_brightness
            )
        ]
        return {"reactions": reactions, "species": species}

    @property
    def reaction_json(self) -> str:
        """The scheme as JSON text — the editor's paste-a-scheme field."""
        return json.dumps(self.scheme, indent=2)

    @reaction_json.setter
    def reaction_json(self, text: str) -> None:
        """Replace the scheme from JSON text, ignoring text that does not parse.

        Parameters
        ----------
        text : str
            A JSON object of the shape :meth:`set_scheme` accepts.
        """
        try:
            scheme = json.loads(text)
        except (TypeError, ValueError):
            return
        if isinstance(scheme, dict):
            self.set_scheme(scheme)

    # -- species --------------------------------------------------------

    @property
    def species_names(self) -> list[str]:
        """Names of the species, in index order."""
        names = list(getattr(self, "_species_names", []))
        while len(names) < len(self._initial_concentrations):
            names.append(str(len(names)))
        return names[: len(self._initial_concentrations)]

    def add_species(
        self,
        species: str = "",
        concentration: float = 0.0,
        brightness: float = 1.0,
        concentration_fixed: bool = True,
        brightness_fixed: bool = True,
    ) -> None:
        """Add one species with its initial concentration and brightness.

        Parameters
        ----------
        species : str
            Display name; defaults to the species index.
        concentration : float
            Concentration at ``t = 0``.
        brightness : float
            Per-species contribution to the observed signal.
        concentration_fixed, brightness_fixed : bool
            Whether each starts fixed in the fit.
        """
        index = len(self._initial_concentrations)
        name = str(species) if species else str(index)
        self._species_names = list(getattr(self, "_species_names", []))
        self._species_names.append(name)
        self._initial_concentrations.append(
            FittingParameter(
                name=f"c({name})", label_text=f"c({name})", value=float(concentration),
                lb=0.0, ub=float("inf"), bounds_on=False, fixed=bool(concentration_fixed),
            )
        )
        self._species_brightness.append(
            FittingParameter(
                name=f"Q({name})", label_text=f"Q({name})", value=float(brightness),
                lb=0.0, ub=float("inf"), bounds_on=False, fixed=bool(brightness_fixed),
            )
        )

    def add_species_row(self) -> None:
        """Append a dark species with zero starting concentration (button action)."""
        self.add_species(concentration=0.0, brightness=1.0)

    def remove_species(self) -> None:
        """Drop the last species, keeping at least two (button action).

        Two is the floor because a reaction needs something on each side; below
        that the scheme cannot be integrated and the editor would show an empty
        table with reactions pointing at species that do not exist.
        """
        if len(self._initial_concentrations) <= 2:
            return
        self._initial_concentrations.pop()
        self._species_brightness.pop()
        if getattr(self, "_species_names", None):
            self._species_names.pop()

    def _species_parameter_rows(self) -> list:
        """Return the species as ``(concentration, brightness)`` pairs per row."""
        rows: list = []
        for c, q in zip(self._initial_concentrations, self._species_brightness):
            rows.extend((c, q))
        return rows

    def _species_row_labels(self) -> list[str]:
        """Return the species names, used as the species table's row headers."""
        return self.species_names

    # -- reactions ------------------------------------------------------

    def reaction_label(self, i: int) -> str:
        """Return reaction ``i`` written with species *names*.

        ``ReactionSystem.reaction_string`` writes indices (``1.0 * [0] -> …``),
        which is unreadable in a table the user is meant to check: the whole
        point of naming a species is to recognise the step.

        Parameters
        ----------
        i : int
            Reaction index.

        Returns
        -------
        str
            e.g. ``"A -> B"`` or ``"2 A + B -> C"``.
        """
        names = self.species_names

        def side(indices, stoichiometry) -> str:
            terms = []
            for index, count in zip(indices, np.atleast_1d(stoichiometry)):
                name = names[index] if 0 <= index < len(names) else str(index)
                terms.append(name if float(count) == 1.0 else f"{float(count):g} {name}")
            return " + ".join(terms) or "∅"

        return (
            f"{side(self.educts[i], self.educts_stoichometry[i])}"
            f" → {side(self.products[i], self.products_stoichometry[i])}"
        )

    def reaction_rows(self) -> list[dict]:
        """Return one row mapping per reaction for the reaction table."""
        return [
            {
                "index": i,
                "reaction": self.reaction_label(i),
                "rate": float(self.rates[i].value),
            }
            for i in range(self.n_reactions)
        ]

    def _signal_parameter_rows(self) -> list:
        """Return the nuisance parameters that map concentrations onto the trace."""
        return [self._scaling, self._background, self._timeshift]

    def _rate_parameter_rows(self) -> list:
        """Return the rate constants, in reaction order."""
        return list(self.rates)

    def add_reaction_row(self) -> None:
        """Append a unimolecular step from the last species to a new one.

        A blank row would have to be filled in before it means anything and there
        is nowhere in a table to type "which species"; growing the chain by one
        step gives a scheme that is always valid and always editable.
        """
        source = max(0, len(self._initial_concentrations) - 1)
        self.add_species(concentration=0.0, brightness=1.0)
        target = len(self._initial_concentrations) - 1
        ReactionSystem.add_reaction(
            self,
            educts=[source],
            products=[target],
            educt_stoichiometry=[1],
            product_stoichometry=[1],
            rate=1.0,
        )

    def remove_selected_reaction(self) -> None:
        """Drop the selected reaction, or the last one when none is selected."""
        if self.n_reactions == 0:
            return
        row = self.selected_reaction
        index = -1
        if isinstance(row, dict) and isinstance(row.get("index"), int):
            index = int(row["index"])
        if index < -1 or index >= self.n_reactions:
            index = -1
        self.pop(index)
        self.selected_reaction = None

    def clear_reactions(self) -> None:
        """Restore the default two-species scheme (the reaction list's reset)."""
        self.set_scheme(self.default_scheme())

    # -- compute --------------------------------------------------------

    def _fit_window(self) -> tuple[int, int]:
        """Return the fit window as indices, an unset window meaning the whole trace.

        ``Fit`` starts with ``xmax == 0`` — an *empty* window, not a full one — so
        autoscaling against it would divide by a zero-length sum.
        """
        n = int(np.asarray(self.fit.data.y).size)
        xmin = max(0, int(getattr(self.fit, "xmin", 0) or 0))
        xmax = getattr(self.fit, "xmax", None)
        if xmax is None or int(xmax) <= xmin:
            return xmin, n
        return xmin, min(int(xmax) + 1, n)

    def _update_model(self, **kwargs) -> None:
        """Integrate the scheme onto the data's time axis and scale the signal.

        Parameters
        ----------
        **kwargs
            Additional keyword arguments accepted for signature compatibility.
        """
        data = self.fit.data
        t = np.asarray(data.x, dtype=float).ravel()
        if t.size == 0 or self.n_reactions == 0:
            self.x = t
            self.y = np.zeros_like(t)
            return

        self.times = t - float(self._timeshift.value)
        self.calc()
        y = np.asarray(self.signal_intensity, dtype=float).ravel()
        if y.size != t.size:
            self.x = t
            self.y = np.zeros_like(t)
            return

        y = y * float(self._scaling.value)
        if self.autoscale:
            lo, hi = self._fit_window()
            model_sum = float(np.sum(y[lo:hi]))
            data_sum = float(np.sum(np.asarray(data.y, dtype=float).ravel()[lo:hi]))
            if np.isfinite(model_sum) and model_sum != 0.0:
                y = y * (data_sum / model_sum)
        self.x = t
        self.y = y + float(self._background.value)
