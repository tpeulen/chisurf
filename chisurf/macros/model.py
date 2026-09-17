from __future__ import annotations

import typing

import chisurf as cs
import chisurf.core.data
import chisurf.core.experiments


def set_linearization(
    idx: int = None, curve_name: str = None, fit: cs.core.fitting.fit.FitGroup = None
) -> None:
    if fit is None:
        gui = cs.cs
        fit = gui.current_fit

    if fit is None or idx is None:
        return

    try:
        lin_table = fit.model.corrections.lin_select.datasets[idx]
    except Exception:
        return

    for f in fit[fit.selected_fit_index :]:
        f.model.corrections.lintable = cs.core.data.DataCurve(x=lin_table.x, y=lin_table.y)
        f.model.corrections.correct_dnl = True

    lin_name = curve_name
    for f in fit[fit.selected_fit_index :]:
        f.model.corrections.lineEdit.setText(str(lin_name or ""))
        f.model.corrections.checkBox.setChecked(True)
    fit.update()


def unload_lintable(fit: cs.core.fitting.fit.FitGroup = None) -> None:
    if fit is None:
        gui = cs.cs
        fit = gui.current_fit

    if fit is None:
        return

    for f in fit[fit.selected_fit_index :]:
        try:
            f.model.corrections.unload_lintable()
        except Exception:
            pass
    fit.update()


def set_correction(
    correction_type: str, value: typing.Any, fit: cs.core.fitting.fit.FitGroup = None
) -> None:
    if fit is None:
        gui = cs.cs
        fit = gui.current_fit

    if fit is None:
        return

    for f in fit[fit.selected_fit_index :]:
        try:
            setattr(f.model.corrections, correction_type, value)
        except Exception:
            pass
    fit.update()


def normalize_amplitudes(
    normalize: bool = True, name: str = "amplitudes", fit: cs.core.fitting.fit.FitGroup = None
) -> None:
    if fit is None:
        gui = cs.cs
        fit = gui.current_fit
    if fit is None:
        return
    for f in fit:
        try:
            target = getattr(f.model, name)
        except AttributeError:
            continue
        try:
            setattr(target, "normalize_amplitudes", normalize)
        except Exception:
            continue
        try:
            f.model.update()
        except Exception:
            continue


def absolute_amplitudes(
    use_absolute_amplitudes: bool = True,
    name: str = "amplitudes",
    fit: cs.core.fitting.fit.FitGroup = None,
) -> None:
    if fit is None:
        gui = cs.cs
        fit = gui.current_fit
    if fit is None:
        return
    for f in fit:
        try:
            target = getattr(f.model, name)
        except AttributeError:
            continue
        try:
            setattr(target, "absolute_amplitudes", use_absolute_amplitudes)
        except Exception:
            continue
        try:
            f.model.update()
        except Exception:
            continue


def remove_component(name: str, fit: cs.core.fitting.fit.FitGroup = None) -> None:
    if fit is None:
        gui = cs.cs
        fit = gui.current_fit
    for f in fit:
        try:
            target = getattr(f.model, name)
        except AttributeError:
            continue
        pop = getattr(target, "pop", None)
        if not callable(pop):
            continue
        # Keep at least one component so the model stays valid (mirrors the
        # old per-widget ``len > 1`` guard); applies to every group member.
        try:
            if len(target) <= 1:
                continue
        except TypeError:
            pass
        try:
            pop()
        except Exception:
            continue
        try:
            f.model.update()
        except Exception:
            continue


def _resolve_selected_curve(
    dataset_idx: int, curve_name: str, selector: typing.Any = None
) -> cs.core.curve.Curve | None:
    """Resolve the curve a data-selector picked, by index then by name.

    The index refers to the selector's own dataset list when there is one (a
    legacy widget carries its `ExperimentalDataSelector`); a pure, Qt-free model
    has no selector, so the same index is interpreted against the global imported
    datasets instead. The name is tried before that fallback because indices go
    stale as soon as the dataset list is re-sorted or filtered, while the name
    survives -- and a wrong-but-valid index silently attaches the wrong curve
    rather than failing.

    Parameters
    ----------
    dataset_idx : int
        Position of the curve in `selector.datasets`, else in the imported
        datasets.
    curve_name : str
        Name of the curve; matched exactly, then by suffix, then by basename so a
        path-like name still resolves.
    selector : typing.Any, optional
        Widget exposing a `datasets` sequence. Absent for pure models.

    Returns
    -------
    chisurf.core.curve.Curve or None
        The resolved curve, or None when neither index nor name matches.
    """
    try:
        selector_datasets = list(getattr(selector, "datasets", []) or [])
    except Exception:
        selector_datasets = []

    if 0 <= int(dataset_idx) < len(selector_datasets):
        return selector_datasets[int(dataset_idx)]

    try:
        imported = list(getattr(cs, "imported_datasets", []) or [])
    except Exception:
        imported = []

    name = str(curve_name or "").strip()
    if name:
        basename = name.replace("\\", "/").split("/")[-1]
        for ds in imported:
            ds_name = str(getattr(ds, "name", "") or "")
            if ds_name == name or ds_name.endswith(name) or ds_name.endswith(basename):
                return ds

    if 0 <= int(dataset_idx) < len(imported):
        return imported[int(dataset_idx)]

    return None


def change_irf(dataset_idx: int, irf_name: str, fit: cs.core.fitting.fit.FitGroup = None) -> None:
    if fit is None:
        gui = cs.cs
        fit = gui.current_fit

    irf_curve = _resolve_selected_curve(
        dataset_idx,
        irf_name,
        selector=getattr(getattr(fit.model, "convolve", None), "irf_select", None),
    )

    if irf_curve is None:
        return

    for f in fit[fit.selected_fit_index :]:
        f.model.convolve._irf = cs.core.data.DataCurve(x=irf_curve.x, y=irf_curve.y)

    fit.update()
    for f in fit[fit.selected_fit_index :]:
        # Presentation only: pure (Qt-free) models have no line edit, and a
        # missing one must not undo the IRF that was just attached above.
        try:
            f.model.convolve.lineEdit.setText(str(irf_name or getattr(irf_curve, "name", "")))
        except AttributeError:
            pass


def unload_irf(fit: cs.core.fitting.fit.FitGroup = None) -> None:
    if fit is None:
        gui = cs.cs
        fit = gui.current_fit

    if fit is None:
        return

    for f in fit[fit.selected_fit_index :]:
        try:
            f.model.convolve.unload_irf()
        except Exception:
            pass
        try:
            f.model.convolve.lineEdit.setText("")
        except Exception:
            pass
    try:
        fit.update()
    except Exception:
        pass


def set_background_curve(
    dataset_idx: int, curve_name: str, fit: cs.core.fitting.fit.FitGroup = None
) -> None:
    """Attach a measured background decay to the model's `generic` group.

    The counterpart of `unload_background_curve`, and the action a
    `curve_input` view-spec section dispatches. A copy is stored rather than the
    imported dataset itself, so re-scaling the background for one fit cannot
    mutate the dataset other fits share.

    Parameters
    ----------
    dataset_idx : int
        Position of the curve in the selector's dataset list, else in the
        imported datasets.
    curve_name : str
        Name of the curve to attach; see `_resolve_selected_curve`.
    fit : chisurf.core.fitting.fit.FitGroup, optional
        Target fit group; the current fit when omitted.
    """
    if fit is None:
        gui = cs.cs
        fit = gui.current_fit

    if fit is None:
        return

    curve = _resolve_selected_curve(dataset_idx, curve_name)
    if curve is None:
        return

    for f in fit[fit.selected_fit_index :]:
        f.model.generic.background_curve = cs.core.data.DataCurve(x=curve.x, y=curve.y)

    fit.update()


def unload_background_curve(fit: cs.core.fitting.fit.FitGroup = None) -> None:
    if fit is None:
        gui = cs.cs
        fit = gui.current_fit

    if fit is None:
        return

    for f in fit[fit.selected_fit_index :]:
        # The group is ``generic`` -- this read ``f.model.nuisance`` for as long
        # as the action existed, so the AttributeError was swallowed by the bare
        # ``except`` below and unloading silently did nothing.
        f.model.generic.unload_background_curve()
    fit.update()


def _update_model(fit: cs.core.fitting.fit.FitGroup = None) -> None:
    if fit is None:
        gui = cs.cs
        fit = gui.current_fit

    if fit is None:
        return

    fit.update()


def add_component(name: str, fit: cs.core.fitting.fit.FitGroup = None) -> None:
    if fit is None:
        gui = cs.cs
        fit = gui.current_fit
    for f in fit:
        try:
            target = getattr(f.model, name)
        except AttributeError:
            continue
        append = getattr(target, "append", None)
        if not callable(append):
            continue
        try:
            append()
        except TypeError:
            # Fallback for append signatures that expect amplitude/lifetime
            try:
                append(amplitude=1.0, lifetime=4.0)
            except Exception:
                continue
        except Exception:
            continue
        try:
            f.model.update()
        except Exception:
            continue


def remove_local_fit(row: int, fit: cs.core.fitting.fit.FitGroup = None) -> None:
    if fit is None:
        gui = cs.cs
        fit = gui.current_fit
    if fit is None:
        return
    try:
        fit.remove_local_fit(row)
    except Exception:
        pass


def clear_local_fits(fit: cs.core.fitting.fit.FitGroup = None) -> None:
    if fit is None:
        gui = cs.cs
        fit = gui.current_fit
    if fit is None:
        return
    try:
        fit.clear_local_fits()
    except Exception:
        pass


def append_global_parameter(parameter_name: str, fit: cs.core.fitting.fit.FitGroup = None) -> None:
    if fit is None:
        gui = cs.cs
        fit = gui.current_fit
    if fit is None:
        return
    try:
        fit.append_global_parameter(parameter_name)
    except Exception:
        pass


def append_fit(fit_index: int, fit: cs.core.fitting.fit.FitGroup = None) -> None:
    # Local import to ensure symbol resolution in static analyzers and at runtime
    import chisurf as _cs

    if fit is None:
        gui = _cs.cs
        fit = gui.current_fit
    if fit is None:
        return
    try:
        target_fit = _cs.fits[fit_index]
        _cs.logging.info(
            f"macros.model.append_fit: requested fit_index={fit_index}; receiver fit obj type={type(fit).__name__}"
        )
        # Prefer model-level append when available (GlobalFitModel.append_fit expects a Fit)
        model_obj = getattr(fit, "model", None)
        used_path = None
        if hasattr(model_obj, "append_fit") and callable(getattr(model_obj, "append_fit", None)):
            used_path = "fit.model.append_fit"
            _cs.logging.info(
                f"macros.model.append_fit: using {used_path}; target_fit type={type(target_fit).__name__}, name={getattr(target_fit, 'name', None)}"
            )
            model_obj.append_fit(target_fit)
        elif hasattr(fit, "append_fit") and callable(getattr(fit, "append_fit", None)):
            used_path = "fit.append_fit"
            _cs.logging.info(
                f"macros.model.append_fit: using {used_path}; target_fit type={type(target_fit).__name__}, name={getattr(target_fit, 'name', None)}"
            )
            fit.append_fit(target_fit)
        else:
            _cs.logging.warning(
                "macros.model.append_fit: neither fit.model.append_fit nor fit.append_fit is available; no-op"
            )
        if used_path is not None:
            recv = model_obj if used_path.startswith("fit.model") else fit
            _cs.logging.info(
                f"macros.model.append_fit: appended via {used_path} to receiver={type(recv).__name__}"
            )
    except Exception:
        try:
            _cs.logging.exception("macros.model.append_fit: exception while appending")
        except Exception:
            pass
