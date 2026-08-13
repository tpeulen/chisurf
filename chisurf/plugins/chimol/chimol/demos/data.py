"""Demo material ChiMOL makes for itself.

Most demos open a file: a PDB in the test data, or something fetched by
accession. One does not exist anywhere to be opened -- a simulation has to be
*run* -- and shipping a binary of its output would be a picture of a result
rather than the result. So it is generated on first use and cached, which keeps
the demo honest: what you watch is what the simulator produced on this machine,
and changing the model changes the demo.

The simulator is the agent-swarm framework that lives beside ChiSurf, driven by
a configuration file it ships. ChiMOL calls it and reads the RMF it writes;
nothing about the biology lives here.
"""

from __future__ import annotations

import logging
import pathlib
import tempfile

logger = logging.getLogger(__name__)


class DemoDataUnavailable(RuntimeError):
    """Raised when a generated demo asset cannot be produced.

    Carries the reason, because the alternative -- returning a path that is not
    there -- surfaces as "cannot read file" and sends whoever hit it looking for
    a missing download.
    """


def cache_dir() -> pathlib.Path:
    """Where generated demo material is kept between sessions.

    Through :mod:`chimol.settings_dir` rather than asking ChiSurf directly: it
    already resolves the same three cases (the env override a test sets,
    ChiSurf's directory when ChiSurf is there, a standalone fallback), and the
    temp-directory fallback here meant demo material was silently re-generated
    every session on a machine without ChiSurf.
    """
    from ..settings_dir import settings_dir  # noqa: PLC0415

    directory = settings_dir(create=True) / "chimol_demos"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _biofilm_config() -> pathlib.Path:
    """The shipped simulation configuration the biofilm demo runs."""
    import IMP.swarm

    return (
        pathlib.Path(IMP.swarm.__file__).resolve().parent
        / "examples"
        / "biofilm_growth.yaml"
    )


def build_biofilm(destination: pathlib.Path) -> pathlib.Path:
    """Grow a biofilm and write it where the demo expects it.

    Parameters
    ----------
    destination : pathlib.Path
        The ``.rmf`` the demo loads.

    Returns
    -------
    pathlib.Path
        ``destination``.

    Raises
    ------
    DemoDataUnavailable
        When the simulator is not importable, or the run failed.
    """
    try:
        from IMP.swarm.core.visual_runner import run_visual_swarm_from_yaml
    except Exception as exc:  # pragma: no cover - depends on the environment
        raise DemoDataUnavailable(
            "the agent-swarm simulator is not importable, so the biofilm demo "
            f"cannot be generated: {exc}"
        ) from exc

    config = _biofilm_config()
    if not config.is_file():  # pragma: no cover - a partial install
        raise DemoDataUnavailable(f"simulation configuration missing: {config}")

    logger.info("chimol: growing the biofilm demo into %s", destination)
    try:
        summary = run_visual_swarm_from_yaml(
            config, output_dir=destination.parent, verbose=False
        )
    except Exception as exc:
        raise DemoDataUnavailable(f"the biofilm simulation failed: {exc}") from exc

    written = pathlib.Path(summary["rmf_file"])
    if written != destination:
        written.replace(destination)
    return destination


#: Demo files that are produced rather than shipped: ``{name: builder}``. The
#: name is what a demo script says, so ``load biofilm_growth.rmf`` reads like
#: any other load.
GENERATED_DEMO_DATA = {
    "biofilm_growth.rmf": build_biofilm,
}


def generated_demo_path(name: str) -> pathlib.Path | None:
    """Return the cached path of a generated demo file, building it if needed.

    Parameters
    ----------
    name : str
        File name as a demo script writes it.

    Returns
    -------
    pathlib.Path or None
        The file, or ``None`` when *name* is not one this module makes.

    Raises
    ------
    DemoDataUnavailable
        When it is one this module makes and making it did not work.
    """
    builder = GENERATED_DEMO_DATA.get(name)
    if builder is None:
        return None
    destination = cache_dir() / name
    if destination.is_file():
        return destination
    return builder(destination)


__all__ = [
    "DemoDataUnavailable",
    "GENERATED_DEMO_DATA",
    "build_biofilm",
    "cache_dir",
    "generated_demo_path",
]
