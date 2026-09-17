"""The GUI's handle on an ebFRET backend session.

One method per thing the ebFRET window can do, each a single RPC call. The GUI
holds no data and imports no analysis code; by default the calls go to an
in-process dispatcher with the plugin's services registered, and to a ChiSurf
server when a ZMQ client is handed in.
"""

from __future__ import annotations

from typing import Any

__all__ = ["EbfretClient"]

PREFIX = "burst_ebfret.session."


class EbfretClient:
    """Typed wrapper over the ``burst_ebfret.session.*`` RPC methods.

    Parameters
    ----------
    client : object, optional
        Anything with ``call(method, params) -> dict``. ``None`` builds an
        in-process dispatcher with this plugin's services.
    seed : int, optional
        Seed of the session's random restarts.
    """

    def __init__(self, client: Any = None, seed: int | None = None) -> None:
        self._client = client if client is not None else self._local_client()
        self.session_id = self._call("open", {"seed": seed}, with_session=False)["session_id"]

    @staticmethod
    def _local_client() -> Any:
        """An ``InProcessClient`` over a dispatcher with the ebFRET services."""
        from chisurf.core.plugin.client import InProcessClient

        from ..backend.services import register_services

        class _Dispatcher:
            def __init__(self) -> None:
                self.handlers: dict = {}

            def register(self, name: str, handler: Any) -> None:
                self.handlers[name] = handler

            def dispatch(self, method: str, params: dict | None) -> dict:
                return self.handlers[method](params or {})

        dispatcher = _Dispatcher()
        register_services(dispatcher)
        return InProcessClient(dispatcher)

    def _call(self, name: str, params: dict | None = None, with_session: bool = True) -> Any:
        payload = dict(params or {})
        if with_session:
            payload["session_id"] = self.session_id
        response = self._client.call(PREFIX + name, payload)
        if isinstance(response, dict) and response.get("ok") is False:
            raise RuntimeError(response.get("error", name))
        return response.get("result") if isinstance(response, dict) else response

    # -- lifecycle ---------------------------------------------------------- #
    def close(self) -> None:
        """Stop the analysis and release the backend session."""
        self._call("close")

    def status(self) -> dict:
        """Revision, running flag, controls and messages."""
        return self._call("status")

    def view(self, timeout: float = 0.5) -> dict:
        """Everything the window draws: plot lines, limits, control values."""
        return self._call("view", {"timeout": timeout})

    def series_table(self) -> list:
        """Label, file, group, length, crop and exclude flag of every series."""
        return self._call("series_table")

    # -- File menu ---------------------------------------------------------- #
    def smd_columns(self, files: list[str]) -> list:
        """Column labels of SMD files, for the *Assign Channels* dialog."""
        return self._call("smd_columns", {"files": list(files)})

    def load(
        self, files: list[str], ftype: int, append: bool = False, smd_channels: dict | None = None
    ) -> dict:
        """*File > Load* with the chosen files, filter index and Keep/Replace."""
        return self._call(
            "load",
            {
                "files": list(files),
                "ftype": int(ftype),
                "append": bool(append),
                "smd_channels": smd_channels,
            },
        )

    def save(self, path: str) -> None:
        """*File > Save* the session."""
        self._call("save", {"path": path})

    def export_summary(self, path: str) -> None:
        """*File > Export > Analysis Summary*."""
        self._call("export_summary", {"path": path})

    def export_traces(
        self, path: str, channels: dict, states: int, group: str = "all", fmt: str | None = None
    ) -> None:
        """*File > Export > Traces*."""
        self._call(
            "export_traces",
            {"path": path, "channels": channels, "states": states, "group": group, "fmt": fmt},
        )

    def export_smd(
        self, path: str, states: int, group: str = "all", fmt: str | None = None
    ) -> None:
        """*File > Export > Single-molecule Dataset (SMD)*."""
        self._call("export_smd", {"path": path, "states": states, "group": group, "fmt": fmt})

    # -- controls ----------------------------------------------------------- #
    def set(self, name: str, value: Any) -> dict:
        """Set one control (``series``, ``crop_min``, ``restarts``, ``show_prior``...)."""
        return self._call("set", {"name": name, "value": value})

    def run(self) -> bool:
        """The *Run* button; ``False`` when nothing was started."""
        return bool(self._call("run", {})["started"])

    def stop(self) -> None:
        """The *Stop* button."""
        self._call("stop")

    def reset(self) -> None:
        """The *Reset* button."""
        self._call("reset")

    # -- Analysis menu ------------------------------------------------------ #
    def remove_bleaching(self, method: int, thresholds: dict | None = None) -> str:
        """*Analysis > Remove Photo-bleaching* with the dialog's values."""
        return self._call("remove_bleaching", {"method": method, "thresholds": thresholds})

    def clip_outliers(self, x_lim: tuple[float, float], max_outliers: int) -> str:
        """*Analysis > Clip Outliers* with the dialog's values."""
        return self._call(
            "clip_outliers", {"x_lim": list(x_lim), "max_outliers": int(max_outliers)}
        )

    def update_priors(self, choice: str) -> None:
        """The *Update Priors* question's answer (Auto / Keep Current)."""
        self._call("update_priors", {"choice": choice})

    def init_priors(self, theta: dict, counts: dict, status: int) -> None:
        """*Analysis > Set Priors* with the dialog's values."""
        self._call("init_priors", {"theta": theta, "counts": counts, "status": status})
