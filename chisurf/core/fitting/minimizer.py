"""The optimiser on the same side of the boundary as the objective.

``fit.run()`` used to run its Levenberg-Marquardt loop in Python: MINPACK
called back into the interpreter for every residual, and the callback wrote
each parameter across the SWIG boundary, evaluated the model, sliced three
numpy arrays and formed the residual. Measured on this tree (imp.bff
``okf/log.md``, 2026-09-01 (6)), the callback was **57%** of a 512-point
three-parameter fit while MINPACK's own arithmetic was about **4%** -- so the
cost was never the algorithm, it was the crossing.

:class:`IMP.bff.Minimizer` is that same MINPACK ``lmdif`` with this package's
own bounds transform, in C++, driving :class:`IMP.bff.Port` parameters and a
:class:`IMP.bff.Node` objective. Two arrangements follow from it:

* **A model bff can represent** -- a parse equation, say -- becomes
  ``Expression -> ChiSquared -> Minimizer``, one C++ graph. The data stay in
  the graph, the optimiser never returns to Python, and a caller crosses
  **once per fit**.
* **A group of them** -- a ``GlobalFitModel``, which is what the GUI builds
  -- becomes one such pair per member under a
  :class:`IMP.bff.JointChiSquared`, whose residual is the members' residuals
  end to end. That is exactly what ``GlobalFitModel.weighted_residuals``
  concatenates, and the parameters members share are ``Port`` links, so a
  group takes one Levenberg-Marquardt step over every dataset's curvature
  with nothing crossing per iteration. A group is refused **whole**: one
  member left in Python would put the crossing back.
* **A TCSPC lifetime decay** becomes ``TcspcDecay -> ChiSquared ->
  Minimizer``. `IMP.bff.TcspcDecay` reconvolves the lifetime spectrum with
  the measured response using **tttrlib's own** kernels -- the periodic
  ``fconv_per_cs`` and the ``shift_lamp`` timeshift, both taken header-only
  -- so bff builds the network, tttrlib computes the curve, and this package
  is not between them. Measured at **4.4x** on a default `LifetimeModel`.
  A model carrying a term the node does not have (a measured background, a
  non-periodic mode) is refused; pile-up and the DNL table ride in the node.
* **A polarised or a FRET decay** is that same instrument with a *producer*
  in front of it, because both are spectrum transforms rather than curve
  ones -- the product of two sums of exponentials is a sum of exponentials,
  and a species quenched by transfer decays at the sum of two rates. So the
  chain is

      ``[GaussianDistances] -> [FretSpectrum] -> [AnisotropySpectrum] ->
      TcspcDecay -> ChiSquared``

  with each link present only when the model has it, and nothing downstream
  of a link needing to know it happened. Measured at **6.5x** for a VV decay
  and **4.4x** for a 96-point Gaussian FRET distribution.

  The FRET figure was **1.2x** when the chain was built, and the reason is
  worth keeping: a 97-species reconvolution was genuinely most of that fit,
  so removing the crossing could not help much. What changed is the
  reconvolution itself -- first by not computing species whose amplitude is
  zero (`okf/log.md` 2026-09-01 (16)), then by interleaving the ones that
  remain, because each species is a serial dependency chain and the species
  are independent of one another (`(17)`, tttrlib's `fconv_per_cs_ad`). The
  crossing was never the cost here; it took measuring the node to see that.
* **Any other model** takes :class:`ResidualNode` -- the same C++ optimiser
  driving a Python residual through a ``Node`` director, one crossing per
  residual evaluation instead of the four or five the numpy loop paid. So
  the algorithm is bff's whatever the model is; only the objective changes
  language.

  This fallback was scipy's ``leastsqbound`` until 2026-09-01, and the
  reason was a measurement: the director path came out at 1.54 ms against
  scipy's 1.33 on a 512-point three-parameter fit, so wrapping a Python
  callback in a C++ loop appeared to buy nothing over wrapping it in a
  Fortran one.

  **It is still slower, and less so.** Timing :func:`minimize` alone --
  interleaved, min-of-many, with the covariance switched off so the two do
  the same work -- the director is **1.11x** scipy on the parse fit and
  **1.06x** on a TCSPC decay. (Caching `ResidualNode`'s port lookups was
  worth about half of what remained: it was 1.29x and 1.22x while
  `get_input_port` was being called once per parameter per evaluation.) So
  this costs something real, and the honest statement is that it is a few
  per cent of the *fallback* path, not that it is free.

  It is paid deliberately, because the argument on the other side is not
  about speed. There were **three** implementations of this bounded
  Levenberg-Marquardt in the stack (bff's, this package's 794-line copy, and
  a plugin's 365-line copy) and **two** of its finite-difference Jacobian,
  *using different step rules*. Two implementations of one algorithm do not
  average out. They disagree, silently, and this stack has already paid for
  that once -- the permuted covariance in ``okf/log.md`` 2026-09-01 was
  found only because two of them were finally run against each other. Six
  per cent of the path taken by the models that build no graph is a cheap
  price for that, and the way to get it back is to give those models a
  graph, which is ``T-20260901-08`` and ``T-20260901-09``.

:func:`minimize` takes the graph when :func:`graph_objective` can build one
for the model it is given, and the director when it cannot. It keeps the
signature ``fit.run()`` called ``leastsqbound`` with, so the switch was one
call site. The deleted implementation survives as
``imp.bff/test/minimizer/reference_leastsqbound.py``, frozen, imported by
nothing and used only to assert that the port is still 1:1.

Measured on a 512-point, three-parameter parse fit, interleaved and
min-of-many because load on a laptop drifts by more than the effect:

===========================  =========  =============================
path                         ms         what crosses per iteration
===========================  =========  =============================
scipy ``leastsqbound``       0.86       parameters, model, residual
C++ optimiser + director     0.96       the residual
whole graph                  0.26       nothing
===========================  =========  =============================

:func:`minimize` alone, with the covariance switched off so the three do the
same work; a whole ``fit.run()`` adds the same overhead to each. The first
row is history -- nothing takes it, and it is measured against the frozen
``imp.bff/test/minimizer/reference_leastsqbound.py``. It is kept because the
*comparison* is the point: the middle row is what the fallback costs now,
and the gap between the middle and the bottom is what building a graph for a
model is worth.

A four-member group over the same curves, sharing one lifetime, is 3.82 ms
against 2.20 ms -- **1.74x** on the whole ``FitGroup.run()``, and about 2.2x
on the optimisation alone; the rest of a group's run (every member updated,
the error estimates, the result snapshot) is the same either way and is what
dilutes the ratio. Before this it was **1.01x**, because the group fell back.

A default TCSPC lifetime fit -- 512 channels, four free parameters, an IRF
to reconvolve against on every evaluation -- is 13.1 ms against 2.26 ms,
**5.8x**, and that is the model anyone actually fits. The same decay under
VV, with a rotational correlation time, is 17.2 against 2.64 ms (**6.5x**);
a Gaussian-distance FRET decay over a 96-point distribution is 27.0 against
6.18 ms (**4.4x**).

**A model that builds a graph must build the *same* model**, which is a
sharper requirement than being fast and is checked separately:
``test/minimizer/census_models.py`` in ``imp.bff`` asks every ChiSurf model
class whether it builds a graph *and* whether that graph's curve is the one
``update_model()`` returns. It exists because on 2026-09-01 two lifetime
subclasses -- `MaxEntLifetimeModel` and `LifetimeMixtureModel` -- were
building the plain multi-exponential graph while computing their spectrum
somewhere else entirely, and the two curves were 793.8 counts apart with
nothing to say so.

The middle row is the point worth remembering: **replacing the optimiser
alone buys nothing.** The crossing was the cost, and a loop that still
crosses does not stop paying it merely by being written in C++. That is why
the graph, and not the C++ optimiser, is what made a fit fast -- and why the
director is nonetheless the right fallback: it costs nothing and it means
there is one implementation of the algorithm rather than three.

**The error estimate is on the same side of the boundary now too.** A fit
used to optimise entirely in C++ and then call the Python model ``p + 1``
more times to rebuild a Jacobian for the error bars -- 32% of a TCSPC fit.
:func:`curvature_over_the_graph` differences the graph instead, at
``approx_grad``'s step rule (``eps * max(|x|, 1)``, an absolute floor, which
is what MINPACK's relative step lacks and why its own covariance had to be
refused). Every consumer of a curvature goes through it: the error estimate,
the posterior view, the derived-quantity propagation, both sampler
preconditioners and :attr:`Fit.grad`. A TCSPC ``fit.run()`` now makes **two**
Python ``update_model()`` calls, which is what a parse fit always made.
"""
from __future__ import annotations

import numpy as np

import chisurf.logging
from chisurf.core.math.optimization import OptimizationCancelled

try:
    import IMP.bff as _bff
    if not hasattr(_bff, "Minimizer"):
        raise ImportError("IMP.bff is present but carries no Minimizer")
except Exception as _exc:  # pragma: no cover - depends on the build
    _bff = None
    _bff_import_error = _exc


__all__ = ["minimize", "have_minimizer", "graph_objective",
           "ResidualNode", "ProgressObserver"]


def have_minimizer() -> bool:
    """Whether the C++ optimiser is available in this environment."""
    return _bff is not None


if _bff is not None:

    class ResidualNode(_bff.Node):
        """A Python residual presented to C++ as a node with a residual port.

        The optimiser writes the trial vector into this node's input ports,
        calls ``update()``, and reads the residual vector back off the
        ``residuals`` output port. Everything in between -- setting the
        model's parameters, evaluating it, forming the weighted residual --
        happens in one Python call instead of the several the old loop made.

        The residual length must not depend on the parameters; the C++ side
        refuses a vector that changes size, because Levenberg-Marquardt has
        no meaning for an objective whose dimension moves.
        """

        def __init__(self, func, n_parameters: int, name: str = "residuals"):
            super().__init__(name)
            self._func = func
            self._names = ["p%d" % i for i in range(n_parameters)]
            for n in self._names:
                self.add_input_port(n, _bff.Port(0.0))
            self.add_output_port("residuals", _bff.Port([0.0], False, True))
            # Resolved once and held. `get_input_port` is a SWIG call and the
            # ports do not move, so looking them up inside `evaluate` cost a
            # crossing per parameter per residual evaluation -- on a
            # four-parameter fit, four of them, for a lookup whose answer was
            # settled in this constructor. Measured on a parse fit: 1.14 ms
            # of optimisation against 1.06 without it.
            self._ports = [self.get_input_port(n) for n in self._names]
            self._out = self.outputs["residuals"]
            #: Set when the callback raised, so `minimize` can re-raise it in
            #: Python rather than let it cross back through the director.
            self.error = None

        @property
        def ports(self):
            return list(self._ports)

        def set_start(self, values) -> None:
            for port, v in zip(self._ports, values):
                port.value = float(v)

        def evaluate(self):
            parameters = np.array([p.value for p in self._ports],
                                  dtype=np.float64)
            try:
                residuals = np.asarray(self._func(parameters),
                                       dtype=np.float64).ravel()
            except BaseException as exc:  # noqa: BLE001 - re-raised below
                # A Python exception thrown through a SWIG director unwinds a
                # C++ loop that is holding raw buffers. Record it, hand back
                # the previous residual so the optimiser stays well-defined,
                # and let `minimize` raise it once the C++ frame is gone.
                if self.error is None:
                    self.error = exc
                self.set_valid(True)
                return
            # `set_values_array`, not `set_value_vector`: the latter takes a
            # std::vector<double>, so from Python it builds a list of every
            # residual before storing any of it. On a 512-point curve that
            # conversion cost more than the optimiser step it served, and it
            # is why this path measured *slower* than the scipy loop.
            self._out.set_values_array(residuals)
            self.set_valid(True)

    class ProgressObserver(_bff.MinimizerObserver):
        """chisurf's ``progress_callback`` contract, driven from C++.

        Reports ``(evaluated, total)`` with ``chi2``/``chi2r`` offered as
        keywords and falls back to the documented two-argument call, which is
        what ``leastsqbound._report_progress`` does and why: a callback
        written to the documented signature raises ``TypeError`` on the
        keywords, and swallowing that left the bar at zero for whole fits.

        Cancellation is a **return value**, not an exception: the C++ loop
        stops at the last accepted point and ``minimize`` raises
        :class:`OptimizationCancelled` afterwards. Throwing through the
        director would unwind that loop mid-iteration.
        """

        def __init__(self, callback, n_free: int = 0):
            super().__init__()
            self._callback = callback
            self._n_free = int(n_free)
            self.cancelled = False

        def report(self, n_evaluations, total, chi2):
            if self._callback is None:
                return True
            dof = max(1.0, float(self._n_free))
            chi2r = float(chi2) / dof if self._n_free else float(chi2)
            try:
                try:
                    self._callback(n_evaluations, total, chi2=float(chi2),
                                   chi2r=chi2r)
                except TypeError:
                    self._callback(n_evaluations, total)
            except OptimizationCancelled:
                self.cancelled = True
                return False
            except Exception:
                # A broken progress bar must not take the optimisation down.
                pass
            return True

else:  # pragma: no cover - environment without IMP.bff
    ResidualNode = None
    ProgressObserver = None



#: The variable an mdf FCS equation reads its diffusion shape from. It is a
#: producer port, not a parameter: `FcsMdfCurve` writes it.
FCS_MDF_VARIABLE = "g_mdf"
#: The quadrature the FCS models evaluate the Enderlein MDF at, which is a
#: property of the *model* rather than of the graph -- the numpy path calls
#: `enderlein.g_diff` with exactly these, so the two agree bit for bit.
FCS_MDF_N_GRID = 121
FCS_MDF_SPAN = 30.0
FCS_MDF_N_HERM = 40


# --------------------------------------------------------------- the graph

def _smooth_prior_present(model) -> bool:
    """Whether any free parameter contributes prior residuals.

    A prior appends rows to the residual vector (`fit._prior_residuals`), so
    the graph -- which produces exactly the data residuals -- would be
    optimising a different objective. Uniform priors are enforced as bounds
    and contribute nothing, so they do not disqualify anything.
    """
    from chisurf.core.fitting.fit import _smooth_prior
    for p in getattr(model, "parameters", []):
        if _smooth_prior(p) is not None:
            return True
    return False


def _member_objective(fit, model, name, producer_ports=None, extra_carried=None):
    """`Expression -> ChiSquared` for one dataset, or ``None``.

    Builds the half of the graph that belongs to a single curve: the compiled
    equation, a port per equation variable, the axis, the data, the window and
    the noise model. It deliberately does **not** decide what drives those
    ports -- whether a variable is the optimiser's, a follower of some other
    dataset's variable, or a constant is a question about the whole fit, and
    only the caller can answer it. The ports are handed back alongside the
    parameters they carry so the caller can wire them.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        The dataset's own fit: its data, window, mask and noise model.
    model : chisurf.core.models.Model
        A parse model whose equation this library can compile.
    name : str
        Node name, unique within the graph the caller is assembling.
    producer_ports : dict, optional
        Equation variable name -> an upstream node's output port. Unlike
        ``graph_axes()`` (a flat array copied in once), a producer variable
        is *linked* -- the caller has already built a node in front of this
        one (the mdf FCS shape, ``_fcs_mdf_producer``), and the compiled
        expression reads its output live instead of holding a copy. Used the
        same way ``extra_axes`` is: presence in ``variables`` satisfies the
        "at least one axis" requirement, and a variable naming neither an
        equation parameter, an axis nor a producer still refuses.
    extra_carried : list, optional
        ``(parameter, port)`` pairs the caller has already wired to a node
        of its own (the mdf shape node's ``w0``/``wem``/``D``/``diam``
        ports) -- carried through to the caller's port-claiming exactly as
        an equation-variable pair is, even though the port belongs to a
        different node than the one built here.

    Returns
    -------
    tuple or None
        ``(chi2, carried, keepalive)``. *carried* is one
        ``(parameter, port)`` pair per equation variable the compiled
        expression kept, in equation order, plus *extra_carried*.
    """
    expression = getattr(model, "_expression", None)
    equation_parameters = getattr(model, "_parameters_equation", None)
    if expression is None or not equation_parameters:
        return None            # not a parse model, or eval()-only equation

    names = [p.name for p in equation_parameters]
    if len(set(names)) != len(names):
        return None            # two equation variables share a name

    # A model may evaluate over axes of its own instead of (or beside) the
    # data's ``x`` -- an image-correlation carpet is a function of three lag
    # grids, and none of them is the flattened index its DataCurve carries.
    # The protocol is a ``graph_axes()`` method returning name -> flat float
    # array, each exactly as long as the data; ``None`` says the axes cannot
    # be produced right now (no carpet metadata), which refuses the graph.
    extra_axes = {}
    axes_method = getattr(model, "graph_axes", None)
    if callable(axes_method):
        try:
            extra_axes = axes_method()
        except Exception:
            return None
        if extra_axes is None:
            return None
        if set(extra_axes) & set(names):
            return None        # an axis shadowing a parameter is ambiguous

    producer_ports = producer_ports or {}

    data = fit.data
    y = np.ascontiguousarray(data.y, dtype=np.float64)
    ey = np.ascontiguousarray(data.ey, dtype=np.float64)
    x = np.ascontiguousarray(data.x, dtype=np.float64)
    if y.size == 0 or ey.size != y.size:
        return None

    try:
        curve = _bff.Expression(name + "_model")
        curve.set_expression(model.func)
        variables = list(curve.get_variable_names())
    except Exception:
        return None            # the engine cannot compile it; eval() can
    used_axes = [v for v in variables if v in extra_axes]
    used_producers = [v for v in variables if v in producer_ports]
    if "x" not in variables and not used_axes and not used_producers:
        return None            # no axis or producer at all: not a curve model
    if any(v != "x" and v not in names and v not in extra_axes
           and v not in producer_ports for v in variables):
        return None

    # One port per equation variable, at the value it holds now. Read once,
    # here -- inside the fit nothing Python owns is consulted again.
    carried = list(extra_carried or [])
    for p in equation_parameters:
        if p.name not in variables:
            continue           # the equation dropped this variable
        if getattr(p, "redundant", False) or getattr(p, "_callable", None):
            # A value *derived* from other parameters is neither a constant
            # nor something the optimiser writes, and the graph has no way to
            # recompute it. Refuse rather than freeze it at its start value.
            return None
        port = _bff.Port(float(p.value))
        curve.add_input_port(p.name, port)
        carried.append((p, port))

    # Numpy in, throughout. The list spellings -- `Port([float(v) for v in
    # x])`, `set_data(list(y), list(ey))` -- convert 1536 doubles into Python
    # floats before a single one is stored, which measured as most of the
    # cost of building the graph at all.
    axes_alive = []
    if "x" in variables:
        axis = _bff.Port([0.0])
        axis.set_values_array(x)
        curve.add_input_port("x", axis)
        axes_alive.append(axis)
    for axis_name in used_axes:
        arr = np.ascontiguousarray(extra_axes[axis_name], dtype=np.float64)
        if arr.ndim != 1 or arr.size != y.size:
            return None        # the curve would not line up with the data
        port = _bff.Port([0.0])
        port.set_values_array(arr)
        curve.add_input_port(axis_name, port)
        axes_alive.append(port)
    for var_name in used_producers:
        port = _bff.Port([0.0])
        port.link = producer_ports[var_name]
        curve.add_input_port(var_name, port)
        axes_alive.append(port)
    out = _bff.Port([0.0], False, True)
    curve.add_output_port(name + "_model", out)

    chi2 = _bff.ChiSquared(name)
    chi2.set_data_arrays(y, ey)
    chi2.set_fit_range(int(fit.xmin), int(fit.xmax))
    chi2.set_noise_model_name(
        _normalize_noise(getattr(fit, "noise_model", "default")))
    model_in = _bff.Port([0.0])
    model_in.link = out
    chi2.add_input_port("model", model_in)
    chi2.add_output_port(name, _bff.Port(0.0, False, True))
    chi2.add_output_port("residuals", _bff.Port([0.0], False, True))
    return chi2, carried, (curve, axes_alive, out, model_in)


def _wire_links(pending, owner_port) -> bool:
    """Make each follower port follow the port of the parameter it follows.

    A linked parameter is not free, so it gets no port of the optimiser's
    own; its value is whatever its master holds. In the graph that is the
    same relation -- ``Port::set_link`` -- so the coupling that makes a
    global fit global never leaves C++.

    The chain is walked rather than followed one step, because a master may
    itself be linked, and because a master that is *fixed* stops nothing: the
    port chain resolves through it exactly as
    :attr:`chisurf.core.parameter.Parameter.value` does. A chain that reaches
    no optimiser-driven parameter needs no wiring at all -- the follower's
    port already holds the value it read at build time, and nothing in the
    fit moves it.

    Returns ``False`` if a chain does not terminate, which the link graph's
    acyclicity should make impossible.
    """
    for port, parameter in pending:
        master = getattr(parameter, "link", None)
        for _ in range(1000):
            if master is None or id(master) in owner_port:
                break
            master = getattr(master, "link", None)
        else:
            return False
        if master is not None:
            port.link = owner_port[id(master)]
    return True


def _masked(fit) -> bool:
    """Whether *fit* carries a mask the graph would have to reproduce."""
    return getattr(fit, "mask", None) is not None


def graph_objective(fit, model, allow_priors: bool = False):
    """Build the whole objective in C++ for *model*, or return ``None``.

    This is the arrangement the whole port was for: the parameters are ports
    the optimiser writes **in C++**, the curves are computed in C++, the data
    live in the `ChiSquared` nodes, and the caller crosses the SWIG boundary
    **once**, for ``run()``. Measured against the Python-residual path on a
    512-point three-parameter fit: 0.163 ms against 1.633 ms.

    Two shapes are built, from the same pieces:

    * a single model becomes ``Expression -> ChiSquared``;
    * a :class:`~chisurf.core.models.global_model.globalfit.GlobalFitModel`
      becomes one ``Expression -> ChiSquared`` per member and a
      :class:`IMP.bff.JointChiSquared` over them, whose residual is the
      members' residuals end to end -- which is exactly what
      :attr:`GlobalFitModel.weighted_residuals` concatenates. Parameters
      shared between members are ``Port`` links, so a group takes one
      Levenberg-Marquardt step using every dataset's curvature at once and
      still never returns to Python.

    **The graph is private to the fit, and that is the design, not an
    accident.** Driving the model's *own* parameter ports from C++ would be
    the obvious thing and is wrong: :attr:`chisurf.core.parameter.Parameter.value`
    keeps a ``_frozen_value`` cache while a fit runs inside
    :func:`~chisurf.core.fitting.factorgraph.frozen_structure`, so a port
    written from C++ is **not seen** by the next Python read -- the model
    would report its pre-fit values and nothing would say so. A private graph
    means the only thing that crosses back is the answer, written through the
    ordinary setters, which is also exactly "keep the data on bff and move
    only what is displayed".

    Returns ``None`` -- and the caller falls back -- whenever the graph would
    not be evaluating the same objective. Each refusal below is a *semantic*
    one; none of them is a limitation of the C++.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Supplies the data, the fit range, the mask and the noise model. For a
        group it supplies none of those -- each member's own fit does -- and
        only its mask is consulted, to refuse.
    model : chisurf.core.models.Model
        A parse model whose equation this library can compile, or a
        `GlobalFitModel` all of whose members are such models.

    Returns
    -------
    tuple or None
        ``(minimizer, free_parameters)`` -- the free parameters in the order
        of the minimiser's ports, which is ``model.parameters`` order.
    """
    if _bff is None:
        return None
    # Priors add rows the graph's residual does not produce, so the
    # least-squares path must refuse them. The sampler asks with
    # ``allow_priors=True``: it evaluates priors natively off the ports and
    # never reads the residual rows, so for it a prior is not a refusal.
    if not allow_priors and _smooth_prior_present(model):
        return None

    free = list(getattr(model, "parameters", []))
    if not free:
        return None

    if getattr(model, "fits", None) is not None and hasattr(
            model, "global_parameters"):
        return _group_objective(fit, model, free)
    if _is_lifetime_model(model) or _is_fret_model(model):
        # One builder for both, because a FRET decay *is* a lifetime decay
        # with a producer in front of it: same instrument, same nuisances,
        # same misfit. What differs is a link in the spectrum chain, and
        # `_spectrum_chain` is where the two part company.
        return _lifetime_objective(fit, model, free)
    if _is_fcs_mdf_model(model):
        # A third family that is not one compiled equation: the "mdf"
        # diffusion mode is a numerical kernel (bff's FcsMdfCurve), so the
        # equation-string route this file otherwise takes is replaced by one
        # producer node in front of the same Expression -> ChiSquared the
        # closed-form diffusion modes use. `_fcs_mdf_objective` is where the
        # two part company.
        return _fcs_mdf_objective(fit, model, free)
    if _is_fcs_kinetics_full_model(model):
        # A fourth family: FCS kinetics in "full" saturation mode. The
        # numerical volume integration (bff's FcsSaturationCurve) is a
        # producer node in front of the same Expression -> ChiSquared,
        # exactly as the mdf FCS shape is. `_fcs_kinetics_full_objective`
        # is where the two part company.
        return _fcs_kinetics_full_objective(fit, model, free)
    return _single_objective(fit, model, free)


def _single_objective(fit, model, free, producer_ports=None,
                      extra_carried=None, extra_keepalive=None):
    """One dataset: ``Expression -> ChiSquared -> Minimizer``.

    *producer_ports*/*extra_carried*/*extra_keepalive* are the mdf FCS
    producer's hook (`_fcs_mdf_objective`): an equation variable backed by an
    upstream node's output port instead of the data, the parameters that node
    owns, and the node instance itself, which must outlive the minimiser it
    feeds -- Python holds the only reference to it once this function returns.
    """
    if _masked(fit) and not _mask_is_representable(fit):
        return None
    built = _member_objective(fit, model, "chi2", producer_ports=producer_ports,
                              extra_carried=extra_carried)
    if built is None:
        return None
    chi2, carried, keepalive = built

    if _masked(fit):
        # Same indexing as `_apply_fit_mask`: full-data indexing, applied
        # over the same window, skipped outright when the lengths disagree.
        try:
            chi2.set_mask_array(np.ascontiguousarray(
                np.asarray(fit.mask, dtype=float).ravel()))
        except Exception:
            return None

    parameter_ports = [None] * len(free)
    owner, pending = {}, []
    _claim(carried, {id(p): i for i, p in enumerate(free)},
           parameter_ports, owner, pending)
    if any(port is None for port in parameter_ports):
        return None            # a free parameter absent from the equation
    if not _wire_links(pending, owner):
        return None

    m = _bff.Minimizer()
    m.set_parameter_ports(parameter_ports)
    m.set_objective(chi2, "residuals")
    # The graph holds the only reference to these once this function returns.
    m._graph = (chi2, carried, keepalive, extra_keepalive)
    # What a Sampler needs to drive the same graph: the objective node, the
    # ports in `free` order, and the scalar-chi2 output port's name.
    m._sampler_surface = (chi2, parameter_ports, "chi2")
    return m, free


def _is_fcs_mdf_model(model) -> bool:
    """Whether *model*'s diffusion term is the Enderlein MDF kernel.

    Duck-typed on the two classes that own it: `MdfFCSModel`, which is the
    kernel and nothing else, and `GeneralFCSModel` while its
    ``diffusion_mode`` is ``"mdf"`` -- the other three modes are closed-form
    and take the ordinary equation route. The mode is *structural*: it is in
    the equation string and therefore in `_graph_cache_key`, so switching it
    cannot leave a graph built for the other branch in place.
    """
    try:
        from chisurf.core.models.fcs.general import GeneralFCSModel
        from chisurf.core.models.fcs.mdf import MdfFCSModel
    except Exception:                              # pragma: no cover
        return False
    if isinstance(model, MdfFCSModel):
        return True
    return (isinstance(model, GeneralFCSModel)
            and model.diffusion_mode == "mdf")


def _fcs_mdf_producer(fit, model):
    """The `IMP.bff.FcsMdfCurve` node in front of an mdf FCS equation.

    The MDF shape is a *numerical kernel* -- a double axial integral, one
    trapezoid times a Gauss--Hermite quadrature -- so it is the one part of
    this model that cannot be a string. It becomes a producer node instead,
    exactly as a FRET decay's photophysics does (`_spectrum_chain`), and
    everything downstream of it stays the compiled equation the closed-form
    diffusion modes already use:

        FcsMdfCurve -> Expression -> ChiSquared -> Minimizer

    **What the node publishes is the shape, not the curve.** The bunching and
    anticorrelation factors multiply *g* and the baseline is added after them,
    so a node that folded ``b`` or ``1/N`` in could not have those terms
    downstream; ``N``, ``b`` and the count-rate background factor stay
    variables of the expression, where they compose correctly.

    **The optics are baked in, and that is what makes freeing one refuse.**
    `MdfOptics` is a fixed calibration, so its five values are set on the node
    once rather than carried as ports. A user who unfixes one puts a
    parameter in ``model.parameters`` that no port carries, and
    `_single_objective`'s unclaimable-port rule refuses the graph -- the same
    refusal any other model gets for a free parameter its equation dropped,
    reached without a special case.

    Returns ``(node, output_port, carried)`` or ``None``.
    """
    if not hasattr(_bff, "FcsMdfCurve"):
        return None            # an older build; the director path still fits
    try:
        from chisurf.core.models.fcs.mdf import MdfFCSModel
    except Exception:                              # pragma: no cover
        return None
    if isinstance(model, MdfFCSModel):
        physical, optics_group = model.physical, model.optics
    else:
        physical, optics_group = model.mdf_physical, model.mdf_optics

    tau_ms = np.ascontiguousarray(
        np.asarray(fit.data.x, dtype=np.float64).ravel())
    if tau_ms.size == 0:
        return None
    optics = optics_group.as_optics()
    try:
        node = _bff.FcsMdfCurve("mdf_shape")
        node.build_ports()
        # Seconds, as the kernel takes them; the equation's own ``x`` stays
        # the data's milliseconds, which is what the relaxation terms use.
        node.set_axis_array(tau_ms * 1e-3)
        node.set_optics(float(optics.excitation_wavelength),
                        float(optics.emission_wavelength),
                        float(optics.refractive_index),
                        float(optics.pinhole_radius))
        # The resolution `MdfFCSModel` and `GeneralFCSModel` call
        # `enderlein.g_diff` with; changing it here would change the model.
        node.set_quadrature(FCS_MDF_N_GRID, FCS_MDF_SPAN, FCS_MDF_N_HERM)
        node.set_length_scale(1e-3)   # the ports carry nanometres
        node.set_normalize(True)
        node.add_output_port("mdf_shape", _bff.Port([0.0], False, True))
    except Exception:
        return None
    carried = [(physical._w0, node.get_input_port("w0")),
               (physical._wem, node.get_input_port("wem")),
               (physical._D, node.get_input_port("D")),
               (physical._diam, node.get_input_port("diam"))]
    # The ports open at `build_ports()` defaults, not at the model's values.
    # A free parameter is overwritten by the optimiser anyway, but a *fixed*
    # one is a constant that must hold the model's value from the first
    # evaluation on -- without this write the graph computed a shape for a
    # different instrument (measured: 50% off with a fixed non-default w0).
    for p, port in carried:
        port.value = float(p.value)
    return node, node.get_output_port("mdf_shape"), carried


def _fcs_mdf_objective(fit, model, free):
    """An mdf FCS model: ``FcsMdfCurve -> Expression -> ChiSquared``."""
    built = _fcs_mdf_producer(fit, model)
    if built is None:
        return None
    node, out_port, carried = built
    return _single_objective(fit, model, free,
                             producer_ports={FCS_MDF_VARIABLE: out_port},
                             extra_carried=carried,
                             extra_keepalive=node)


def _is_fcs_kinetics_full_model(model) -> bool:
    """Whether *model* is an FCS kinetics model in "full" saturation mode.

    The "full" mode performs a numerical volume integration (bff's
    ``FcsSaturationCurve``) that cannot be an equation string. The other two
    modes -- "fast" (Gaussian * bunching) and no-power (analytical Gaussian)
    -- are closed-form and take the ordinary equation route.

    Saturation mode is *structural*: it is in the equation string (via
    ``_expression`` returning ``None`` for non-full modes) and therefore in
    ``_graph_cache_key``, so switching it cannot leave a graph built for one
    branch in place.
    """
    try:
        from chisurf.core.models.fcs.kinetics import FCSKineticsModel
    except Exception:                              # pragma: no cover
        return False
    return (isinstance(model, FCSKineticsModel)
            and model.saturation_mode == "full"
            and model.saturation.active)


def _fcs_kinetics_full_producer(fit, model):
    """The `IMP.bff.FcsSaturationCurve` node in front of a kinetics equation.

    The saturated shape is a *numerical kernel* -- a steady-state solve on a
    2D (r, z) grid plus a spatial autocorrelation -- so it is the one part of
    this model that cannot be a string. It becomes a producer node instead,
    exactly as the MDF shape does (`_fcs_mdf_producer`), and everything
    downstream stays the compiled expression:

        FcsSaturationCurve -> Expression -> ChiSquared -> Minimizer

    **What the node publishes is the shape, not the curve.** The baseline
    ``b``, the amplitude ``1/N`` and the background factor multiply the shape
    *after* the node, so they stay variables of the expression, where they
    compose correctly.

    **The photokinetic scheme is baked in.** The dark/excitation matrices,
    brightness, grid resolution and wavelength are configuration set once at
    build time -- not ports -- so they survive across the optimiser's
    evaluations without being re-set. Freeing one of those parameters puts it
    in ``model.parameters`` with no port to carry it, and the graph refuses
    (unclaimable-port rule).

    Returns ``(node, output_port, carried)`` or ``None``.
    """
    if not hasattr(_bff, "FcsSaturationCurve"):
        return None            # an older build; the director path still fits
    sat = model.saturation
    tau_ms = np.ascontiguousarray(
        np.asarray(fit.data.x, dtype=np.float64).ravel())
    if tau_ms.size == 0:
        return None
    try:
        node = _bff.FcsSaturationCurve("fcs_saturation")
        node.build_ports()
        # Seconds, as the kernel takes them; the equation's own ``x`` stays
        # the data's milliseconds.
        node.set_axis_array(tau_ms * 1e-3)
        # The photokinetic scheme: dark rates (Hz), excitation cross-sections,
        # brightness — set once, not re-set per evaluation.
        dark = np.asarray(sat.dark_matrix_hz, dtype=float).ravel()
        exc = np.asarray(sat.exc.rate_matrix(), dtype=float).ravel()
        bright = np.asarray(sat.brightness.array, dtype=float).ravel()
        node.set_scheme(list(dark), list(exc), sat.n_states, list(bright))
        node.set_quadrature(120, 40)  # the model's own grid resolution
        node.set_wavelength(float(sat.wavelength_m))
        node.set_include_bunching(True)
        node.add_output_port("fcs_saturation", _bff.Port([0.0], False, True))
    except Exception:
        return None
    # Port names match the model's FittingParameter names (power, extinction,
    # w0, z0, D) so `_claim` matches them with the free parameters. N, b, bg
    # are equation variables, not node ports.
    carried = [
        (sat._power, node.get_input_port("power")),
        (sat._extinction, node.get_input_port("extinction")),
        (sat._w_r, node.get_input_port("w0")),
        (sat._w_z, node.get_input_port("z0")),
        (sat._D, node.get_input_port("D")),
    ]
    # Set the node's port values from the model's current parameter values.
    # Fixed parameters are constants that hold their value at build time;
    # free parameters are overwritten by the optimiser, but setting them now
    # means the first evaluation (before the optimiser writes) is correct.
    for p, port in carried:
        port.value = float(p.value)
    return node, node.get_output_port("fcs_saturation"), carried


def _fcs_kinetics_full_objective(fit, model, free):
    """A kinetics FCS model in "full" mode: ``FcsSaturationCurve -> Expression -> ChiSquared``."""
    built = _fcs_kinetics_full_producer(fit, model)
    if built is None:
        return None
    node, out_port, carried = built
    return _single_objective(fit, model, free,
                             producer_ports={model.FCS_SAT_VARIABLE: out_port},
                             extra_carried=carried,
                             extra_keepalive=node)


def _publish_curve(m, model, x) -> bool:
    """Publish the fitted curve off the graph's output port, or say no.

    The expensive half of T-20260901-11. After the parameter write-back the
    graph's decay node already holds (almost) the fitted curve -- "almost"
    because MINPACK's last evaluation is not guaranteed at the solution and
    the covariance step perturbed the ports -- so the ports are set to the
    solution once, the node re-evaluated **in C++**, and the curve and the
    autoscaled amplitude read off. That replaces the one remaining Python
    ``update_model()`` of a decay fit (233 us of 2.26 ms TCSPC, 554 us of
    6.21 ms FRET).

    ``n0`` is the trap this function must not fall into: the autoscaled
    amplitude is *computed by the evaluation*, so publishing the curve
    without also publishing ``n0`` leaves the displayed amplitude stale
    while the curve looks right. Both are read off the node together.

    Scoped to the decay path (``m._decay``): the parse path's evaluation is
    microseconds, and a group's members write back through their own
    models. Returns ``False`` -- and the caller runs ``update_model()`` --
    whenever anything is not exactly as this function expects.
    """
    node = getattr(m, "_decay", None)
    surface = getattr(m, "_sampler_surface", None)
    if node is None or surface is None:
        return False
    try:
        _, ports, _ = surface
        for port, value in zip(ports, x):
            port.value = float(value)
        node.update()
        curve = np.asarray(node.get_output_port("decay").value, dtype=float)
        if curve.ndim != 1 or curve.size != np.asarray(model.y).size:
            return False
        if node.get_autoscale():
            model.convolve._n0.value = float(node.get_n0())
        model.y = curve
        return True
    except Exception:
        return False


def _claim(carried, free_slot, parameter_ports, owner, pending):
    """Sort one dataset's equation ports into the optimiser's and the rest.

    A free parameter's equation port *is* the port the optimiser writes --
    there is no second port and nothing to copy. A linked one gets no port of
    its own and is queued for :func:`_wire_links`. Anything else -- a fixed
    parameter, or one whose master the optimiser does not drive -- is a
    constant already holding the value it was built with.
    """
    for p, port in carried:
        slot = free_slot.get(id(p))
        if slot is not None:
            parameter_ports[slot] = port
            owner[id(p)] = port
        elif getattr(p, "is_linked", False):
            pending.append((port, p))


def _group_objective(fit, model, free):
    """A `GlobalFitModel`: one `JointChiSquared` over the members' misfits.

    The mapping is exact, which is why this is a graph at all rather than an
    approximation of one:

    ============================================  ==========================
    ``GlobalFitModel``                            ``IMP.bff``
    ============================================  ==========================
    ``weighted_residuals``, members concatenated  the joint residual, blocks
                                                  end to end, member order
    ``parameters``: members' free, then globals   the minimiser's ports, in
                                                  that order
    a member parameter linked to a global one     ``Port::set_link``
    each member's own window and noise model      each member's `ChiSquared`
    ============================================  ==========================

    **A group is refused whole.** A member the graph cannot represent cannot
    be left in Python and joined to the others: `JointChiSquared` has one
    objective, and half of it crossing per iteration would measure like the
    director path -- which is a regression, not a speed-up.
    """
    members = list(model.fits)
    if not members:
        return None
    # A group's masks are the one place the Python objective is not the sum
    # of its members: `GlobalFitModel.weighted_residuals` concatenates the
    # members' residuals *unmasked*, and `_apply_fit_mask` then applies the
    # group's own mask -- the selected member's -- only when its window
    # happens to be as long as the whole concatenation. Rather than
    # reproduce that, refuse: a masked group is rare and a wrong objective
    # is not.
    if _masked(fit) or any(_masked(f) for f in members):
        return None

    free_slot = {id(p): i for i, p in enumerate(free)}
    parameter_ports = [None] * len(free)
    owner = {}
    pending = []
    keepalive = []
    chi2_nodes = []

    for index, member in enumerate(members):
        member_model = getattr(member, "model", None)
        if member_model is None:
            return None
        built = _member_objective(member, member_model, "member_%d" % index)
        if built is None:
            return None        # refuse the group, not just this member
        chi2, carried, alive = built
        chi2_nodes.append(chi2)
        keepalive.append((chi2, carried, alive))
        _claim(carried, free_slot, parameter_ports, owner, pending)

        # Every free parameter of a member must be one its equation carries,
        # exactly as for a single fit: one the equation dropped is one the
        # optimiser could move without changing any residual.
        held = {id(p) for p, _ in carried}
        for p in member_model.parameters:
            if id(p) not in held:
                return None

    # What is left unfilled are the group's own global parameters. They
    # appear in no equation -- members reach them by linking -- so they get
    # a port of their own, which the followers below then follow.
    globals_by_id = {id(p) for p in model.global_parameters}
    for slot, p in enumerate(free):
        if parameter_ports[slot] is not None:
            continue
        if id(p) not in globals_by_id:
            return None        # a free parameter belonging to nothing
        port = _bff.Port(float(p.value))
        parameter_ports[slot] = port
        owner[id(p)] = port
        keepalive.append(port)

    if not _wire_links(pending, owner):
        return None

    joint = _bff.JointChiSquared("joint")
    joint.add_output_port("joint", _bff.Port(0.0, False, True))
    joint.add_output_port("residuals", _bff.Port([0.0], False, True))
    for chi2 in chi2_nodes:
        joint.add_member(chi2, "residuals")

    m = _bff.Minimizer()
    m.set_parameter_ports(parameter_ports)
    m.set_objective(joint, "residuals")
    # The graph holds the only reference to these once this function returns.
    m._graph = (joint, chi2_nodes, keepalive)
    m._sampler_surface = (joint, parameter_ports, "joint")
    return m, free


def _is_lifetime_model(model) -> bool:
    """Whether *model* is a TCSPC multi-exponential decay bff can build.

    Duck-typed rather than an ``isinstance``: `LifetimeModel` is the base of
    a family (FRET, anisotropy, PDDEM) whose members add *terms* to the
    decay, and a subclass that does so must not be mistaken for the plain
    one. The check is therefore for the exact parts this builder reads.

    **And for one part it does not read, which is the load-bearing half.**
    :func:`_lifetime_objective` builds the spectrum from the ``lifetimes``
    group's own amplitude and lifetime parameters, so it is only the model's
    spectrum while ``lifetime_spectrum`` is still
    :attr:`LifetimeModel.lifetime_spectrum`. A subclass that **overrides**
    that property computes its pairs from something else entirely -- a
    maximum-entropy inversion, a mixture of other fits' spectra, a distance
    distribution -- and the graph would then be fitting a different curve
    from the one the model reports.

    Refusing on the free parameters alone does not catch it. A subclass
    whose extra parameters are all *fixed* -- which is exactly how
    `MaxEntLifetimeModel` ships, its grid and entropy weight being settings
    rather than fitted values -- offers the same four free parameters the
    plain model does, so every port is placed and the graph builds. Measured
    on a 512-channel decay before this check existed: the graph's curve and
    the model's were **793.8 counts apart** at the same parameters, with
    nothing to say so.
    """
    if not all(hasattr(model, name)
               for name in ("convolve", "generic", "corrections",
                            "anisotropy", "lifetimes")):
        return False
    from chisurf.core.models.tcspc.lifetime import LifetimeModel
    own = getattr(type(model), "lifetime_spectrum", None)
    return own is getattr(LifetimeModel, "lifetime_spectrum", None)


def _is_fret_model(model) -> bool:
    """Whether *model* is a FRET decay this builder knows how to reproduce.

    The same discipline :func:`_is_lifetime_model` uses, one family down.
    `FRETModel` is itself a base: its subclasses differ in the *distance
    distribution*, and two of them differ in more than that -- `FRETrateModel`
    replaces the rate spectrum outright and `PDDEMModel` replaces the lifetime
    spectrum. So what is checked is that the two derivations between a
    distance and a lifetime are still `FRETModel`'s, and
    :func:`_fret_source` then checks the distribution itself.
    """
    try:
        from chisurf.core.models.tcspc.fret import FRETModel
    except Exception:                              # pragma: no cover
        return False
    if not isinstance(model, FRETModel):
        return False
    for name in ("lifetime_spectrum", "fret_rate_spectrum"):
        if getattr(type(model), name, None) is not getattr(FRETModel, name):
            return False
    return True


def _fret_distances(model, carried):
    """The node -- or the constant -- behind a model's distance distribution.

    Each `FRETModel` subclass *is* a distance distribution and nothing else;
    the quenching, the donor-only mixture and the instrument are shared. So
    this is the one place the family branches, and it branches on which class
    owns ``distance_distribution`` rather than on a list of known subclasses.

    Returns ``(node_or_None, values_or_None)``: a producer node when the
    distribution has fitted parameters behind it, otherwise the constant
    interleaved ``(p, r)`` array to write into the port once.
    """
    from chisurf.core.models.tcspc.fret import FRETModel, GaussianModel

    owner = getattr(type(model), "distance_distribution", None)

    if owner is getattr(FRETModel, "distance_distribution", None):
        # The base model's distribution is a *constant* -- one distance, one
        # weight -- so it needs no producer and no ports. Read from the model
        # rather than written out here, so it stays that model's number.
        distribution = np.asarray(model.distance_distribution, dtype=float)
        if distribution.shape[0] != 1:
            return None, None
        weights, distances = distribution[0][0], distribution[0][1]
        values = np.empty(2 * weights.size, dtype=np.float64)
        values[0::2] = weights
        values[1::2] = distances
        return None, values

    if owner is getattr(GaussianModel, "distance_distribution", None):
        gaussians = model.gaussians
        # The two-cloud form is a different probability density (the distance
        # between two Gaussian *positions*), not a different parameterisation
        # of the generalised normal. The node used to carry only the latter and
        # this branch refused; it carries both since 2026-09-02, and the two
        # share one kernel with `Gaussians.distribution` so they cannot drift.
        two_cloud = bool(getattr(gaussians, "is_distance_between_gaussians", False))
        n = len(gaussians._gaussianMeans)
        if n < 1:
            return None, None
        node = _bff.GaussianDistances("distances")
        node.set_number_of_components(n)
        node.set_distance_between_gaussians(two_cloud)
        node.add_output_port("distances", _bff.Port([0.0], False, True))
        node.set_axis_array(np.ascontiguousarray(
            np.asarray(_rda_axis(), dtype=np.float64)))
        for i in range(n):
            carried.append((gaussians._gaussianMeans[i],
                            node.get_input_port("mean%d" % i)))
            carried.append((gaussians._gaussianSigma[i],
                            node.get_input_port("sigma%d" % i)))
            carried.append((gaussians._gaussianShape[i],
                            node.get_input_port("shape%d" % i)))
            carried.append((gaussians._gaussianAmplitudes[i],
                            node.get_input_port("amplitude%d" % i)))
        return node, None

    # The closed-form polymer models: one node with a mode, dispatching into
    # the same PolymerChain kernels chisurf's rdf.py forwarders call -- the
    # graph path and the numpy path evaluate one implementation
    # (T-20260901-08; kernels landed with T-20260902-01). Ports carry what
    # the model fits; the worm-like chain's dimensionless kappa = lp / l is
    # derived in the node, the same derivation the model property makes.
    from chisurf.core.models.tcspc.fret import (
        WormLikeChainModel, SawNuModel, IsingChainModel)
    if not hasattr(_bff, "PolymerDistances"):
        return None, None

    if owner is getattr(WormLikeChainModel, "distance_distribution", None):
        node = _bff.PolymerDistances("distances")
        node.set_mode("worm_like_chain_linker" if model.use_dye_linker
                      else "worm_like_chain")
        node.add_output_port("distances", _bff.Port([0.0], False, True))
        node.set_axis_array(np.ascontiguousarray(
            np.asarray(_rda_axis(), dtype=np.float64)))
        carried.append((model._chain_length,
                        node.get_input_port("chain_length")))
        carried.append((model._persistence_length,
                        node.get_input_port("persistence_length")))
        # Carried in both modes: with the linker off the port is inert, which
        # mirrors the model exactly -- `w` is a fitting parameter either way
        # and the numpy path fits it inert too. Not carrying it would refuse
        # the graph for a free parameter that changes nothing.
        carried.append((model._sigma_linker,
                        node.get_input_port("sigma_linker")))
        return node, None

    if owner is getattr(SawNuModel, "distance_distribution", None):
        node = _bff.PolymerDistances("distances")
        node.set_mode("saw_nu")
        node.add_output_port("distances", _bff.Port([0.0], False, True))
        node.set_axis_array(np.ascontiguousarray(
            np.asarray(_rda_axis(), dtype=np.float64)))
        carried.append((model._r_rms, node.get_input_port("r_rms")))
        carried.append((model._nu, node.get_input_port("nu")))
        return node, None

    if owner is getattr(IsingChainModel, "distance_distribution", None):
        node = _bff.PolymerDistances("distances")
        node.set_mode("ising_chain")
        node.add_output_port("distances", _bff.Port([0.0], False, True))
        node.set_axis_array(np.ascontiguousarray(
            np.asarray(_rda_axis(), dtype=np.float64)))
        carried.append((model._n_residues, node.get_input_port("n_residues")))
        carried.append((model._b_structured,
                        node.get_input_port("b_structured")))
        carried.append((model._b_unstructured,
                        node.get_input_port("b_unstructured")))
        carried.append((model._coupling, node.get_input_port("coupling")))
        carried.append((model._field, node.get_input_port("field")))
        return node, None

    # A distribution this builder does not produce -- a discrete set, a
    # maximum-entropy inversion, a structure. Each is its own decision
    # (T-20260901-08 records them); until then, the numpy path is the
    # honest answer.
    return None, None


def _rda_axis():
    """The distance axis the FRET models share, resolved the way they do."""
    from chisurf.core.models.tcspc.fret import rda_axis
    return rda_axis


def _fret_source(model, lifetimes, carried):
    """``LifetimeSpectrumNode -> FretSpectrum``, and what feeds its distances.

    A FRET decay is a donor spectrum quenched over a distance distribution:
    a distance is a transfer rate, rates add, so the quenched spectrum is the
    product of the donor's rates and the transfer rates. That makes the whole
    of the photophysics a *spectrum* transform, and the instrument node
    downstream never learns a transfer happened -- the same property that
    lets a polarisation be one.

    Returns ``(donor_node, output_port, keepalive)`` or ``None``.
    """
    if not hasattr(_bff, "FretSpectrum"):
        return None            # an older build; the numpy path still fits
    import chisurf.core.settings
    settings = chisurf.core.settings.cs_settings["fret"]
    if settings.get("bin_lifetime", False):
        # Binning replaces the spectrum with a coarse-grained one after it is
        # built. That is a real step of the model, not a display choice.
        return None
    if getattr(model.orientation_parameter, "mode", "fast") != "fast":
        # A kappa-squared *spectrum* convolves the distances before they
        # become rates; the node takes one orientation factor.
        return None

    distances_node, constant = _fret_distances(model, carried)
    if distances_node is None and constant is None:
        return None

    try:
        donor = _bff.LifetimeSpectrumNode("donor")
        donor.set_number_of_lifetimes(len(lifetimes._amplitudes))
        donor.add_output_port("donor", _bff.Port([0.0], False, True))
        donor.set_absolute_amplitudes(bool(lifetimes.absolute_amplitudes))
        donor.set_normalize_amplitudes(bool(lifetimes.normalize_amplitudes))

        fret = _bff.FretSpectrum("fret")
        fret.build_ports()
        fret.add_output_port("fret", _bff.Port([0.0], False, True))
        fret.get_input_port("donor_lifetime_spectrum").link = \
            donor.get_output_port("donor")
        if distances_node is not None:
            fret.get_input_port("distance_distribution").link = \
                distances_node.get_output_port("distances")
        else:
            fret.get_input_port("distance_distribution").set_values_array(
                np.ascontiguousarray(constant))
    except Exception:
        return None

    parameters = model.fret_parameters
    carried.append((parameters._xDonly, fret.get_input_port("x_donly")))
    carried.append((parameters._forster_radius,
                    fret.get_input_port("forster_radius")))
    carried.append((parameters._tauD0, fret.get_input_port("tau0")))
    carried.append((parameters._kappa2, fret.get_input_port("kappa2")))

    efficiency = getattr(parameters, "_fret_efficiency", None)
    if efficiency is not None:
        # `E_FRET` is *derived*: its value comes from a callable and its
        # setter is ignored, so neither this path nor the numpy one can move
        # it -- yet ChiSurf hands it to the optimiser as a free parameter, so
        # both must offer it a slot. The port is deliberately wired to
        # nothing. MINPACK differences it, gets a column of zeros in either
        # path, and the two agree because they are equally unable to move it.
        # Refusing instead would refuse every FRET model, since the parameter
        # ships free.
        carried.append((efficiency, _bff.Port(float(efficiency.value))))

    keepalive = [donor, fret]
    if distances_node is not None:
        keepalive.append(distances_node)
    return donor, fret.get_output_port("fret"), keepalive


def _unpolarised_source(lifetimes):
    """``LifetimeSpectrumNode`` holding the fitted amplitudes and lifetimes.

    `TcspcDecay` reads those from its own scalar ports when nothing sits
    between the parameters and the instrument. As soon as something does --
    a polarisation, a FRET quenching -- the spectrum has to exist *before*
    the instrument, and this is the node it exists in.
    """
    node = _bff.LifetimeSpectrumNode("lifetimes")
    node.set_number_of_lifetimes(len(lifetimes._amplitudes))
    node.add_output_port("lifetimes", _bff.Port([0.0], False, True))
    node.set_absolute_amplitudes(bool(lifetimes.absolute_amplitudes))
    node.set_normalize_amplitudes(bool(lifetimes.normalize_amplitudes))
    return node


def _rotation_link(anisotropy, upstream, carried):
    """``... -> AnisotropySpectrum``, over whatever produced *upstream*.

    The instrument is the same for a VV, a VH and a magic-angle measurement;
    what differs is the spectrum that reaches it. A polarised model is
    therefore *one node further upstream*, not a second builder and not a
    term added to `TcspcDecay` -- which is the arrangement
    :meth:`IMP.bff.TcspcDecay.set_spectrum_from_port` exists for. It sits
    last in the chain because `update_model` applies it last: to the FRET
    spectrum when there is one, to the plain one otherwise.

    The transform itself is `IMP.bff.AnisotropySpectrum`, which reproduces
    :func:`chisurf.core.fluorescence.anisotropy.decay.calculcate_spectrum`
    entry for entry. It has to: a mixed channel is the *union* of two scaled
    spectra rather than their sum, so both its length and its ordering are
    observable, and a fit built on a differently-ordered one is wrong in a
    way no chi-square would show.

    Returns ``(node, output_port)`` or ``None``.
    """
    if not hasattr(_bff, "AnisotropySpectrum"):
        return None            # an older build; the numpy path still fits
    try:
        rotation = _bff.AnisotropySpectrum("anisotropy")
        rotation.set_number_of_rotations(len(anisotropy._bs))
        rotation.add_output_port("anisotropy", _bff.Port([0.0], False, True))
        # Refuses an unknown name rather than defaulting to magic angle,
        # which would silently be a model with no anisotropy in it.
        rotation.set_polarization_name(str(anisotropy.polarization_type))
        rotation.get_input_port("lifetime_spectrum").link = upstream
    except Exception:
        return None

    carried.append((anisotropy._r0, rotation.get_input_port("r0")))
    carried.append((anisotropy._g, rotation.get_input_port("g")))
    carried.append((anisotropy._l1, rotation.get_input_port("l1")))
    carried.append((anisotropy._l2, rotation.get_input_port("l2")))
    for i, (amplitude, rho) in enumerate(zip(anisotropy._bs,
                                             anisotropy._rhos)):
        carried.append((amplitude, rotation.get_input_port("b%d" % i)))
        carried.append((rho, rotation.get_input_port("rho%d" % i)))
    return rotation, rotation.get_output_port("anisotropy")


def _spectrum_chain(model, lifetimes, decay, carried):
    """Everything between the fitted parameters and the instrument node.

    One decay model differs from another almost entirely upstream of the
    instrument: reconvolve, add scatter, scale, add a background is the same
    for all of them. So this assembles a chain of producers and hands
    `TcspcDecay` its result --

        [donor] -> [FretSpectrum] -> [AnisotropySpectrum] -> TcspcDecay

    -- with each link present only when the model has it. When neither is,
    the chain is empty and the decay reads its own scalar ports, which is
    exactly what it did before any of this existed.

    Returns ``(spectrum_owner, keepalive)``, where ``spectrum_owner`` is the
    node carrying the fitted amplitude and lifetime ports, or ``None``.
    """
    anisotropy = model.anisotropy
    polarised = not anisotropy._is_vm_polarization(
        anisotropy.polarization_type)
    fret = _is_fret_model(model)

    if not polarised and not fret:
        decay.set_absolute_amplitudes(bool(lifetimes.absolute_amplitudes))
        decay.set_normalize_amplitudes(bool(lifetimes.normalize_amplitudes))
        return decay, []

    keepalive = []
    if fret:
        built = _fret_source(model, lifetimes, carried)
        if built is None:
            return None
        owner, upstream, keep = built
        keepalive.extend(keep)
    else:
        try:
            owner = _unpolarised_source(lifetimes)
        except Exception:
            return None
        upstream = owner.get_output_port("lifetimes")
        keepalive.append(owner)

    if polarised:
        built = _rotation_link(anisotropy, upstream, carried)
        if built is None:
            return None
        rotation, upstream = built
        keepalive.append(rotation)

    try:
        decay.set_spectrum_from_port(True)
        decay.get_input_port("lifetime_spectrum").link = upstream
    except Exception:
        return None
    # And **not** on the decay, which now sees a spectrum something else
    # built. ChiSurf takes the absolute value and normalises the
    # *unpolarised, unquenched* amplitudes, inside `Lifetimes.amplitudes`;
    # normalising again downstream would divide by a different sum -- after a
    # rotation it is `1 + 2 r0` rather than 1 -- and rescale the model curve.
    decay.set_absolute_amplitudes(False)
    decay.set_normalize_amplitudes(False)
    return owner, keepalive


def _lifetime_objective(fit, model, free):
    """A TCSPC decay: ``TcspcDecay -> ChiSquared -> Minimizer``.

    The second model family on the graph, and the first that is not one
    compiled equation. The curve is `IMP.bff.TcspcDecay`, which reconvolves
    the lifetime spectrum with the response using **tttrlib's own** kernels;
    the misfit is the same `ChiSquared` a parse model uses. So a lifetime fit
    crosses the SWIG boundary once per ``run()`` rather than once per
    iteration, and nothing about the objective is re-implemented on the way
    -- the convolution stays where `AGENTS.md` puts curves.

    Every refusal below is a term the node does not carry. A term left in
    Python cannot be joined to a curve computed in C++ without crossing per
    iteration, which measured as a *regression* for the group; the same
    arithmetic applies here.
    """
    if _masked(fit) and not _mask_is_representable(fit):
        return None

    convolve = model.convolve
    generic = model.generic
    corrections = model.corrections
    lifetimes = model.lifetimes

    if getattr(convolve, "mode", None) != "per":
        return None            # the node reconvolves periodically, only
    if not getattr(convolve, "do_convolution", False):
        return None            # the ideal decay is a different curve
    if generic.background_curve is not None:
        return None            # a measured background is a second curve
    if getattr(lifetimes, "_link", None) is not None:
        return None            # the spectrum comes from another model
    if getattr(lifetimes, "_lifetime_spectrum", None) is not None:
        return None            # a spectrum set outright, not from parameters

    data = fit.data
    y = np.ascontiguousarray(data.y, dtype=np.float64)
    ey = np.ascontiguousarray(data.ey, dtype=np.float64)
    if y.size == 0 or ey.size != y.size:
        return None

    # The *unshifted* processed response. Background subtraction, truncation
    # and normalisation depend only on parameters that do not move during a
    # fit, so the application does them once; the timeshift does move, so it
    # is a port and the node applies it. Taken from `_process_irf` rather
    # than from `irf`, which is the shifted one.
    try:
        irf_y = np.ascontiguousarray(
            convolve._process_irf(normalize=True).y, dtype=np.float64)
    except Exception:
        return None
    if irf_y.size != y.size:
        # ChiSurf resizes the response to the data *after* shifting it, and
        # a resize that wraps is not a shift. Rather than reproduce a tiling,
        # refuse the one case where they differ.
        return None

    try:
        node = _bff.TcspcDecay("decay")
        node.set_number_of_lifetimes(len(lifetimes._amplitudes))
        node.add_output_port("decay", _bff.Port([0.0], False, True))
        node.set_response_array(irf_y)
        node.set_timing(float(convolve.dt), 1000.0 / float(convolve.rep_rate))
        # `stop` is a channel index derived from a time; the node clamps it
        # to the last valid one, as ChiSurf's own wrapper does.
        node.set_convolution_range(int(y.size), int(convolve.stop))
    except Exception:
        return None
    # Every parameter the graph carries, paired with the port that holds it.
    # A free one becomes the optimiser's; a linked one follows its master; a
    # fixed one keeps the value written here.
    carried = []

    # A polarised or a FRET model is the *same instrument* with a different
    # spectrum reaching it, so each is a node further upstream rather than a
    # second builder.
    built = _spectrum_chain(model, lifetimes, node, carried)
    if built is None:
        return None
    spectrum_owner, keepalive = built

    # A reconvolution costs one serial recursion over every channel *per
    # species*, and a model whose spectrum comes from a distribution has as
    # many species as that distribution has bins -- 97 for a FRET decay over
    # the 96-point distance axis, of which only 53 carry a weight above
    # `1e-14` of the largest. Asking the node to skip the rest is
    # `AMPLITUDE_THRESHOLD` below; it is the application's choice to make,
    # which is why the node defaults to keeping everything.
    try:
        node.set_amplitude_threshold(AMPLITUDE_THRESHOLD)
    except AttributeError:                     # an older build
        pass

    # Autoscaling is ChiSurf's default and it makes `n0` an *output*: the
    # node computes it from the data, so it needs the data as well as
    # `ChiSquared` does. `_n0.fixed` is how ChiSurf spells "autoscale", which
    # is also why `n0` is then not among the free parameters.
    autoscale = bool(convolve._n0.fixed)
    node.set_autoscale(autoscale)
    if autoscale:
        node.set_data_arrays(y, ey)
        node.set_scale_range(min(0, int(convolve.start)),
                             min(int(convolve.stop), int(y.size)))

    # Coates pile-up runs in the node (tttrlib's kernel, chisurf's edge-case
    # semantics), between the scatter term and the scaling -- the same slot
    # `Corrections.pileup` occupies in the Python pipeline. The correction
    # is computed from the data, so it needs the arrays even without
    # autoscaling. An older engine without the setters refuses, it does not
    # silently drop the term.
    if getattr(corrections, "correct_pile_up", False):
        try:
            node.set_pile_up(True)
            node.set_pile_up_parameters(
                float(corrections.dead_time),
                float(corrections.measurement_time))
            if not autoscale:
                node.set_data_arrays(y, ey)
        except Exception:
            return None

    # The DNL table multiplies the finished curve, after the background and
    # before the clamp -- `Corrections.linearize`'s slot. The table is
    # measured, not fitted (its window parameters are fixed), so it is read
    # once here; `lintable` already resolves the `reverse` orientation. An
    # older engine without the setter refuses rather than dropping the term.
    if getattr(corrections, "correct_dnl", False):
        try:
            table = np.ascontiguousarray(
                corrections.lintable, dtype=np.float64)
            if table.ndim != 1 or table.size != y.size:
                return None
            node.set_linearization_array(table)
        except Exception:
            return None

    # The `a`/`t` ports belong to whichever node holds the *unpolarised*
    # spectrum -- the decay itself at magic angle, the upstream source node
    # otherwise -- because that is where ChiSurf's fitted amplitudes and
    # lifetimes enter the model.
    for i, (amplitude, lifetime) in enumerate(
            zip(lifetimes._amplitudes, lifetimes._lifetimes)):
        carried.append((amplitude, spectrum_owner.get_input_port("a%d" % i)))
        carried.append((lifetime, spectrum_owner.get_input_port("t%d" % i)))
    carried.append((generic._sc, node.get_input_port("scatter")))
    carried.append((generic._bg, node.get_input_port("background")))
    carried.append((convolve._n0, node.get_input_port("n0")))
    carried.append((convolve._ts, node.get_input_port("timeshift")))
    for parameter, port in carried:
        port.value = float(parameter.value)

    parameter_ports = [None] * len(free)
    owner, pending = {}, []
    _claim(carried, {id(p): i for i, p in enumerate(free)},
           parameter_ports, owner, pending)
    if any(port is None for port in parameter_ports):
        # A free parameter the node does not carry: a subclass adding a term,
        # a nuisance this builder does not know, or a rotation amplitude.
        return None
    if not _wire_links(pending, owner):
        return None

    chi2 = _bff.ChiSquared("chi2")
    chi2.set_data_arrays(y, ey)
    chi2.set_fit_range(int(fit.xmin), int(fit.xmax))
    chi2.set_noise_model_name(
        _normalize_noise(getattr(fit, "noise_model", "default")))
    if _masked(fit):
        try:
            chi2.set_mask_array(np.ascontiguousarray(
                np.asarray(fit.mask, dtype=float).ravel()))
        except Exception:
            return None
    model_in = _bff.Port([0.0])
    model_in.link = node.get_output_port("decay")
    chi2.add_input_port("model", model_in)
    chi2.add_output_port("chi2", _bff.Port(0.0, False, True))
    chi2.add_output_port("residuals", _bff.Port([0.0], False, True))

    m = _bff.Minimizer()
    m.set_parameter_ports(parameter_ports)
    m.set_objective(chi2, "residuals")
    # The graph holds the only reference to these once this function returns.
    #
    # Nothing here has to publish the autoscaled `n0`: the answer is written
    # back through the ordinary setters and `model.update()` then runs
    # ChiSurf's own pipeline once, which recomputes and stores it. The node
    # is kept reachable as `_decay` for the same reason the rest is -- so a
    # caller can look at what was built.
    m._graph = (node, chi2, carried, model_in, keepalive)
    m._decay = node
    m._sampler_surface = (chi2, parameter_ports, "chi2")
    return m, free


def _mask_is_representable(fit) -> bool:
    """Whether `ChiSquared` can carry this fit's mask.

    Kept separate from applying it so a single fit refuses for the same
    reason a group does -- a mask the graph would silently drop.
    """
    try:
        return np.asarray(fit.mask, dtype=float).ravel().size > 0
    except Exception:
        return False


def _normalize_noise(name: str) -> str:
    from chisurf.core.fitting import normalize_noise_model
    return normalize_noise_model(name)

#: Amplitude below which a decay species is not worth reconvolving, relative
#: to the largest amplitude in the spectrum.
#:
#: Measured on a FRET decay over the 96-point distance axis (a Gaussian at
#: 45 A with sigma 6, one donor lifetime, 20% donor-only), against the
#: unpruned curve:
#:
#: ==========  =======  ==============================  ==============
#: threshold   species  max abs. curve change / peak    decay node
#: ==========  =======  ==============================  ==============
#: 0 (exact)   97       0                               194 us
#: ``1e-14``   53       1.0e-15                         108 us
#: ``1e-12``   44       5.2e-14                         90 us
#: ``1e-10``   37       2.0e-11                         --
#: ``1e-6``    26       2.1e-7                          --
#: ==========  =======  ==============================  ==============
#:
#: ``1e-14`` is chosen because the change it makes to the curve is **smaller
#: than the change from summing the same species in a different order** --
#: it is not a trade of accuracy for speed, it is declining to compute terms
#: that double precision cannot represent the contribution of. The looser
#: values are real trades and are deliberately not taken.
#:
#: A plain multi-exponential is unaffected: it has one species per fitted
#: lifetime and they all carry weight.
AMPLITUDE_THRESHOLD = 1e-14

#: MINPACK's `info` values that mean the fit converged.
_SUCCESS = (1, 2, 3, 4)

#: `leastsqbound`'s default relative step for the forward-difference
#: Jacobian, used when the caller passes none.
_DEFAULT_EPSFCN = 1e-6


def _forward_differences_resolved(x, epsfcn) -> bool:
    """Whether MINPACK's Jacobian can be trusted to build a covariance.

    ``lmdif`` differences the objective forward at ``h_j = sqrt(epsfcn) *
    |x_j|`` -- a step **relative to the parameter**. A parameter that has
    converged near zero therefore gets a step near zero, its Jacobian column
    is round-off, and ``covar`` reports an enormous variance for it. Nothing
    about that is wrong in the optimiser: it is what a relative step means.

    Measured on a TCSPC decay whose free vector spans ``1.5e-5`` (a scatter
    fraction) to ``3.15`` (a lifetime): the optimiser's standard deviation on
    the scatter came out **140x** the finite-difference one, and *scipy's own*
    ``leastsqbound`` covariance for the same fit was no better -- 0.094 for
    the same parameter and exactly **zero** for two others. So this is a
    property of the estimator, not of the port, and the two implementations
    fail together.

    The test is on the same quantities the step is made of. ``h_j`` probes
    the objective usefully only if it is not lost against the resolution the
    objective is computed to, which the largest parameter sets: with
    ``h_j = sqrt(epsfcn)|x_j|``, a parameter below ``sqrt(epsfcn) * max|x|``
    is being differenced at a step under ``epsfcn * max|x|``. When one is,
    the whole matrix is refused rather than one column -- the columns are not
    independent, and dropping one silently changes what the others mean.

    Refusing costs a Jacobian rebuild (about a third of a fit) and gives the
    answer :func:`covariance_matrix` would have given, which is the numpy
    path's answer. Accepting a wrong error bar costs more.
    """
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return False
    if not np.all(np.isfinite(x)):
        return False
    scale = float(np.max(np.abs(x)))
    if scale == 0.0:
        return False
    step = np.sqrt(float(epsfcn) if epsfcn else _DEFAULT_EPSFCN)
    return bool(np.all(np.abs(x) >= step * scale))


def director_objective(func, x0, args=()):
    """`func` as a node the C++ optimiser can drive, and a minimiser over it.

    The fallback for a model the graph cannot represent -- a prior the engine
    will not compile, an equation it does not know, a subclass that computes
    its spectrum somewhere else. The optimiser is still bff's; only the
    objective is Python, reached once per residual evaluation through a SWIG
    director instead of the four or five crossings the numpy loop paid.

    Returns
    -------
    (Minimizer, ResidualNode)
        The node is returned and **must be kept** for the length of the run:
        the C++ side holds only a weak reference to its Python proxy, so a
        node that falls out of scope while the minimiser is still in use is a
        use-after-free.
    """
    node = ResidualNode(
        (lambda p: func(p, *args)) if args else func, len(x0))
    node.set_start(x0)
    m = _bff.Minimizer()
    m.set_parameter_ports(node.ports)
    m.set_objective(node, "residuals")
    return m, node


def _graph_cache_key(fit, model):
    """What must not have changed for a built graph to still be the right one.

    The *identities* of the free parameters (a re-parse rebuilds the objects,
    and a graph for the previous set would line up by length and mean
    nothing), the model and data objects, the arrays the node copied, and the
    fit window that decides which slice of them it copied.

    **The data arrays are deliberately not in the key.** ``DataCurve.x`` and
    ``.y`` build a fresh array on every access, so ``id()`` of them is the
    address of a temporary that CPython immediately reuses -- two consecutive
    reads compare *equal* while two reads either side of a call compare
    *unequal*, which is the worst of both. Measured while writing this: the
    key never matched and the cache never hit.

    So what is keyed is the structure and the window, and the cache is
    additionally dropped at the top of every :meth:`Fit.run`. **What that
    leaves uncovered**, said plainly: mutating a data buffer in place between
    two analyses of the same finished fit. Fingerprinting the contents would
    mean reading the whole array on every call, which is the transport this
    exists to remove.
    """
    try:
        free = getattr(model, "parameters", [])
        # The equation string is part of the structure: a model may
        # regenerate it from its configuration (the image-correlation model
        # does, on its geometry toggle), and a graph compiled for the other
        # string computes a different model at the same parameter values.
        func = getattr(model, "func", None)
        return (id(model), id(fit.data),
                func if isinstance(func, str) else None,
                tuple(id(p) for p in free),
                getattr(fit, "xmin", None), getattr(fit, "xmax", None))
    except Exception:
        return None


def _cached_graph(fit, model):
    """`graph_objective`, built once and kept while it stays valid.

    **Measured, and it is why this exists.** Building the graph is **70% of a
    TCSPC `covariance_matrix()` call and 53% of a FRET one** -- 175 us and
    523 us respectively -- because it constructs every node and copies
    ``x``/``y``/``ey`` into `ChiSquared` again. That is exactly the transport
    the standing rule is about: the arithmetic being in C++ does not help if
    the arrays are marshalled across to drive it, and here they were marshalled
    once per *consumer*, of which there are six.

    Deliberately not used by :func:`minimize`, which builds its own graph for
    the run it is about to do. `Fit.run()` is already one build.
    """
    key = _graph_cache_key(fit, model)
    if key is None:
        return None
    cached = getattr(fit, "_graph_cache", None)
    if cached is not None and cached[0] == key:
        return cached[1]
    try:
        built = graph_objective(fit, model)
    except Exception as e:
        chisurf.logging.debug("curvature: no graph (%s)" % e)
        built = None
    try:
        fit._graph_cache = (key, built)
    except Exception:
        pass          # a fit that will not take an attribute simply rebuilds
    return built


def curvature_over_the_graph(fit, model, epsilon=None, what="covariance"):
    """`covariance_matrix` / `approx_grad`, computed in C++ over the graph.

    The same finite differences at the same step rule, taken where the model
    and the data already are instead of ``p + 1`` times through
    :meth:`Model.update_model`. Everything that wants a curvature -- the
    error estimate, the posterior view, error propagation onto a derived
    quantity, a sampler's preconditioner -- can ask for it here, and only a
    model the graph cannot represent pays for the numpy version.

    Unlike the covariance taken at the end of a fit, this evaluates ``f0``
    itself (``p + 2`` rather than ``p + 1``): the caller is asking about
    wherever the model currently sits, which is not necessarily a point the
    optimiser just left.

    Parameters
    ----------
    fit, model : Fit, Model
        As :func:`graph_objective` wants them. ``model`` is explicit and must
        stay so: for a :class:`FitGroup` ``fit.model`` is the *selected
        member's* model rather than the global one, and four of this
        function's callers pass a different one for exactly that reason.
    epsilon : float, optional
        Relative step; ``None`` means chisurf's ``FINITE_DIFFERENCE_STEP``.
    what : {"covariance", "jacobian"}
        The pseudo-inverse of ``J J'`` over the parameters that move the
        objective, or the raw ``(p, m)`` Jacobian with every row kept.

    Returns
    -------
    tuple or None
        ``(cov, used)`` or ``(f0, grad)``-shaped ``jacobian``, and ``None``
        when the model builds no graph -- which is the caller's signal to use
        the numpy path rather than an error.
    """
    if _bff is None or fit is None or model is None:
        return None
    built = _cached_graph(fit, model)
    if built is None:
        return None
    m, free = built
    x = [float(p.value) for p in free]
    step = 0.0 if epsilon is None else float(epsilon)
    try:
        if what == "jacobian":
            return m.jacobian(x, step, 0.0)
        cov, used = m.finite_difference_covariance_at(x, step, 0.0)
    except Exception as e:
        chisurf.logging.warning("curvature: the graph would not evaluate (%s)"
                                % e)
        return None
    if cov.size == 0:
        return None
    return cov, used


def _covariance_at_the_solution(m, free, x, options):
    """The covariance to hand `update_error_estimates`, or ``None``.

    Two matrices are available at the end of a run and the cheap one is not
    always the right one:

    **The QR covariance** (:meth:`Minimizer.covariance`) costs nothing -- the
    optimiser ends holding the factorisation it is built from. But `lmdif`
    differences at ``h_j = sqrt(epsfcn)|x_j|``, a step *relative to the
    parameter*, so a parameter that converged near zero was differenced at a
    step near zero and its column is round-off.
    :func:`_forward_differences_resolved` is the test for that, and it
    refuses every real TCSPC fit, whose free vector runs from a scatter
    fraction of 1e-5 to a lifetime of 3.15.

    **The finite-difference covariance** (`Minimizer.compute_covariance`)
    costs ``p + 1`` evaluations, but of the *graph* -- in C++, with the data
    already in the node -- rather than ``p + 1`` trips through
    `Model.update()`. It uses :func:`approx_grad`'s step rule,
    ``eps * max(|x|, 1)`` with ``eps = sqrt(machine eps)``, which is the
    absolute floor the optimiser's rule lacks and the reason it resolves. It
    is the same arithmetic `covariance_matrix` does and it was pinned against
    it before this was wired: **3e-7 relative** on the parameter standard
    deviations across the parse, TCSPC, VV and FRET fixtures, including the
    FRET fit dropping the same `E_FRET` column.

    So: the free one when it is trustworthy, and the C++ one beneath it. The
    numpy path is no longer reached for anything that built a graph.

    Returns
    -------
    (cov, used, ids) or None
        ``used`` indexes the parameters the matrix is over -- shorter than
        ``free`` when a parameter does not move the objective. ``ids`` is the
        identity of the parameter objects, checked by the reader because a
        re-parse rebuilds them and a covariance for the previous set would
        line up by length and mean nothing.
    """
    ids = tuple(id(p) for p in free)
    if ier_is_success(m.status) and _forward_differences_resolved(
            x, options.get("epsfcn")):
        cov = m.covariance
        if cov.shape == (len(free), len(free)) and np.all(np.diag(cov) > 0.0):
            return cov, list(range(len(free))), ids
    try:
        cov, used = m.finite_difference_covariance()
    except Exception as e:                      # a graph that will not evaluate
        chisurf.logging.warning("minimize: no covariance: %s" % e)
        return None
    if cov.size == 0:
        return None
    return cov, used, ids


def ier_is_success(ier) -> bool:
    """Whether MINPACK's ``info`` says the fit converged."""
    return ier in _SUCCESS


def minimize(
        func,
        x0,
        args=(),
        bounds=None,
        progress_callback=None,
        n_free: int = 0,
        fit=None,
        model=None,
        **options,
):
    """Minimise ``sum(func(x)**2)`` in C++, falling back to numpy.

    A drop-in for :func:`leastsqbound` in the shape ``fit.run()`` calls it.

    Parameters
    ----------
    func : callable
        ``func(x, *args) -> residual vector``.
    x0 : array_like
        Starting parameters.
    args : tuple, optional
        Extra arguments for ``func``.
    bounds : list of (low, high), optional
        ``None`` in either slot means no bound in that direction, as does a
        non-finite value.
    progress_callback : callable, optional
        Called ``(evaluated, total)``; raising
        :class:`OptimizationCancelled` from it cancels the fit.
    n_free : int, optional
        Free-parameter count, used only to report ``chi2r``.
    fit, model : optional
        Supplied together, they let :func:`graph_objective` try to build the
        whole objective in C++. Omitted, the director path is used.
    **options
        ``ftol``, ``xtol``, ``gtol``, ``maxfev``, ``epsfcn``, ``factor``,
        ``diag`` -- the names and the defaults of :func:`leastsqbound`.

    Returns
    -------
    (x, ier)
        The solution and MINPACK's status, as :func:`leastsqbound` returns
        them without ``full_output``.

    Raises
    ------
    OptimizationCancelled
        If ``progress_callback`` asked to stop.
    """
    x0 = np.asarray(x0, dtype=np.float64).ravel()
    if _bff is None:
        raise RuntimeError(
            "chisurf has no optimiser: IMP.bff could not be imported. "
            "There is one implementation of the bounded Levenberg-Marquardt "
            "in this stack and it is bff's; a second copy in Python is what "
            "was removed on 2026-09-01.")

    # The graph when the model can be represented, the director when it
    # cannot. `graph_objective` refuses on *semantics* -- a prior, an
    # equation the engine will not compile -- so a refusal is a correct
    # answer computed the slower way, never a wrong one.
    built = graph_objective(fit, model) if (fit is not None and
                                            model is not None) else None
    if built is not None and len(built[1]) != len(x0):
        built = None
    node = None
    if built is None:
        # This fell back to scipy's `leastsqbound` until 2026-09-01, because
        # the director measured 1.54 ms against scipy's 1.33. Re-measured on
        # the current build, timing this call alone with the covariance off:
        # **1.11x on a parse fit and 1.06x on a TCSPC decay**. Still slower,
        # and small enough that the reason to pay it is the one that was
        # never about speed -- there were three implementations of this
        # algorithm in the stack and two of its Jacobian, with *different
        # step rules*, and two implementations of one algorithm do not
        # average out, they disagree quietly. See the module docstring.
        m, node = director_objective(func, x0, args)
        free = list(getattr(model, "parameters", [])) if model is not None \
            else []
        if len(free) != len(x0):
            free = []
    else:
        m, free = built
    m.set_initial_values([float(v) for v in x0])
    if bounds is not None:
        m.bounds = list(bounds)
    for key in ("ftol", "xtol", "gtol", "maxfev", "epsfcn", "factor", "diag"):
        if key in options and options[key] is not None:
            setattr(m, key, options[key])

    observer = None
    if progress_callback is not None:
        observer = ProgressObserver(progress_callback, n_free)
        m.set_observer(observer)

    ier = m.run()
    x = np.asarray(m.x)

    # A Python exception raised inside the residual is *recorded* by
    # `ResidualNode` rather than thrown, because throwing it through a SWIG
    # director unwinds a C++ loop holding raw buffers. This is where it
    # becomes an exception again, once that frame is gone.
    if node is not None and node.error is not None:
        raise node.error
    if observer is not None and observer.cancelled:
        raise OptimizationCancelled()

    # The covariance, taken *here* -- before the write-back below -- because
    # this is where the graph still holds the solution and its residuals.
    # Afterwards it would cost an extra evaluation to get back to it. The
    # director path gets one too: differencing a Python residual `p + 1`
    # times is exactly what `covariance_matrix` would have cost, and coming
    # through here means the *free* QR matrix is used whenever it resolves.
    if fit is not None:
        fit._cpp_covariance = (_covariance_at_the_solution(m, free, x, options)
                               if free else None)

    if built is not None:
        # The graph is private, so the answer has to be published: the
        # parameters through the ordinary setters, and the curve **read off
        # the node's output port** (T-20260901-11) -- computing it a second
        # time in Python is not a display step, it is a second composition
        # of the same kernels, and two implementations disagree silently.
        # This is the only place the fit's numbers change language, and it
        # happens once per fit rather than once per iteration.
        #
        # The director path needs none of it: its residual *is* the Python
        # model, so the last thing the optimiser did was evaluate the model
        # at the answer.
        for parameter, value in zip(free, x):
            parameter.value = float(value)
        if not _publish_curve(m, model, x):
            model.update()
        # Tell Fit.run the model already holds the fitted curve, so its own
        # self.update() does not evaluate the model a second time.
        if fit is not None:
            fit._model_holds_the_fit = True

    if ier not in _SUCCESS and ier != -1:
        chisurf.logging.warning("minimize: %s" % m.message)
    return x, ier
