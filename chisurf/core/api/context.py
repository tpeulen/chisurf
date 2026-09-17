from __future__ import annotations

from typing import Any


class PluginContext:
    """Context passed to plugins during migration.
    ...

    Examples
    --------
    >>> ctx = PluginContext(api=api, client=client)
    >>> fits = ctx.api.list_fits()
    """

    def __init__(
        self,
        api: Any = None,
        client: Any = None,
        main_window: Any = None,
    ):
        self.api = api
        self.client = client
        self.main_window = main_window

    def list_fits(self) -> list[dict[str, Any]]:
        if self.api is not None:
            return self.api.list_fits()
        return []

    def list_datasets(self) -> list[dict[str, Any]]:
        if self.api is not None:
            return self.api.list_datasets()
        return []

    def run_fit(self, fit_index: int | None = None, fit_uid: str | None = None) -> dict[str, Any]:
        if self.api is not None:
            return self.api.run_fit(fit_index=fit_index, fit_uid=fit_uid)
        return {"ok": False, "error": "no api available"}

    def get_fit_info(
        self, fit_index: int | None = None, fit_uid: str | None = None
    ) -> dict[str, Any]:
        if self.api is not None:
            return self.api.get_fit_info(fit_index=fit_index, fit_uid=fit_uid)
        return {"ok": False, "error": "no api available"}

    def get_parameter(self, parameter_name: str, fit_index: int = 0) -> dict[str, Any]:
        if self.api is not None:
            return self.api.get_parameter(parameter_name=parameter_name, fit_index=fit_index)
        return {"ok": False, "error": "no api available"}

    def set_parameter_value(
        self, parameter_name: str, value: float, fit_index: int = 0
    ) -> dict[str, Any]:
        if self.api is not None:
            return self.api.set_parameter_value(
                parameter_name=parameter_name, value=value, fit_index=fit_index
            )
        return {"ok": False, "error": "no api available"}

    def set_parameter_fixed(
        self, parameter_name: str, fixed: bool, fit_index: int = 0
    ) -> dict[str, Any]:
        if self.api is not None:
            return self.api.set_parameter_fixed(
                parameter_name=parameter_name, fixed=fixed, fit_index=fit_index
            )
        return {"ok": False, "error": "no api available"}

    def set_parameter_bounds(
        self, parameter_name: str, bounds: tuple, fit_index: int = 0
    ) -> dict[str, Any]:
        if self.api is not None:
            return self.api.set_parameter_bounds(
                parameter_name=parameter_name, bounds=bounds, fit_index=fit_index
            )
        return {"ok": False, "error": "no api available"}

    def load_dataset(self, experiment_reader: Any = None, **kwargs: Any) -> dict[str, Any]:
        if self.api is not None:
            return self.api.load_dataset(experiment_reader=experiment_reader, **kwargs)
        return {"ok": False, "error": "no api available"}

    def save_project(self, target_path: str, project_name: str | None = None) -> dict[str, Any]:
        if self.api is not None:
            return self.api.save_project(target_path=target_path, project_name=project_name)
        return {"ok": False, "error": "no api available"}

    def load_project(self, project_path: str) -> dict[str, Any]:
        if self.api is not None:
            return self.api.load_project(project_path=project_path)
        return {"ok": False, "error": "no api available"}

    def ping(self) -> dict[str, Any]:
        if self.api is not None:
            return self.api.ping()
        return {"ok": False, "error": "no api available"}

    # ── Global-View parameter exposure ───────────────────────────────

    def register_working_model(
        self, model: Any, *, owner_id: str, label: str | None = None
    ) -> None:
        """Expose a plugin working model to the Global View parameter table.

        Any model-bearing plugin can call this so its out-of-fit parameters (a
        ``FittingParameterGroup`` such as a ``LifetimeModel``) become visible and
        linkable alongside real fits. Re-registering the same ``owner_id``
        replaces; the group is held weakly, so keep your own reference.

        Parameters
        ----------
        model : FittingParameterGroup
            The working model/group to expose.
        owner_id : str
            Stable identifier for this plugin's model (e.g. the plugin id).
        label : str, optional
            Human-readable Owner-column label (defaults to ``owner_id``).
        """
        from chisurf.core.registry.parameter_groups import register_parameter_group

        register_parameter_group(model, owner_id=owner_id, label=label or owner_id)

    def unregister_working_model(self, owner_id: str) -> None:
        """Remove a model previously exposed via :meth:`register_working_model`."""
        from chisurf.core.registry.parameter_groups import unregister_parameter_group

        unregister_parameter_group(owner_id)
