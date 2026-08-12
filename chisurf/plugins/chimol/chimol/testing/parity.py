"""One report, run on both hosts, so desktop and browser can be compared.

Why this exists
---------------
"chimol works in a browser" is not a thing a screenshot can settle. The page
renders a molecule and a panel; so does the desktop; and the interesting
question -- *which of the hundred-odd commands, and which of the controls,
behave differently there* -- is invisible in both pictures.

So this is the measurement. It is deliberately **engine code, shipped to the
page**, not a test-side script: a comparison whose two halves are written twice
compares the two scripts as much as the two hosts, and the first thing that
drifts is the argument some command is probed with.

What it reports
---------------
``report`` answers four questions about a live viewer:

``commands``
    Every registered command name. A name missing on one host is a command that
    host cannot run at all.
``probes``
    Every command **actually run**, with what it said. This is the functional
    half: a command that exists on both hosts and errors on one is exactly what
    a name list cannot show. Arguments come from :data:`PROBE_ARGS`; anything
    not listed is run bare, which for most commands is the no-argument form
    PyMOL also accepts.
``chrome``
    The control inventory -- the panel's rows, the sequence strip, the menu
    tree, and every control a coarse sweep of ``hit_test`` can *reach*. This is
    the same measure ``test/chrome_baseline.py`` freezes, and for the same
    reason: parity is judged on what is there and pressable, not on pixels.
``host``
    What the host itself can do -- double clicks, a wheel that carries a
    position, a resize, picking. These are not engine features and cannot be
    probed by running a command: a browser that never delivers a double click
    has a fully working menu system that nobody can open.

Determinism
-----------
Probes run in a fixed order, and one that reloads: a command in
:data:`DESTRUCTIVE` empties the viewer, so the session is rebuilt after it or
every later probe reports "no object" on both hosts and the comparison passes by
agreeing about nothing.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional

__all__ = [
    "DESTRUCTIVE",
    "PROBE_ARGS",
    "SKIP",
    "chrome_inventory",
    "host_features",
    "normalise",
    "probe_commands",
    "report",
]

#: The viewport the chrome is laid out at for the inventory. Fixed, and the
#: same on both hosts: a different width re-flows the panel, and a re-wrapped
#: control is indistinguishable from a missing one.
INVENTORY_SIZE = (1280, 860)

#: Arguments to probe a command with, where running it bare would prove
#: nothing. A command absent from this table is run with no arguments.
#:
#: Chosen to *do something observable* on 148L rather than to be accepted: a
#: probe that returns "usage: ..." on both hosts agrees about the usage string
#: and not about the command.
PROBE_ARGS: dict[str, str] = {
    "align": "148l, 148l",
    "alter": "resi 20, b=1.0",
    "alter_state": "1, resi 20, x=x",
    "angle": "ang1, resi 20 and name CA, resi 21 and name CA, resi 22 and name CA",
    "as": "cartoon",
    "bg_color": "white",
    "bg_colour": "black",
    "bond": "resi 20 and name CA, resi 21 and name CA",
    "buried_area": "148l, 148l",
    "cartoon": "loop",
    "cba": "148l",
    "cbh": "148l",
    "center": "resi 20-40",
    "centroid": "resi 20-40",
    "clashes": "148l",
    "clip": "slab, 100",
    "cnc": "148l",
    "color": "red, resi 20-40",
    "copy": "copy1, 148l",
    "create": "frag1, resi 20-40",
    "del": "sele",
    "delete": "sele",
    "deselect": "",
    "dihedral": ("dih1, resi 20 and name CA, resi 21 and name CA, "
                 "resi 22 and name CA, resi 23 and name CA"),
    "disable": "148l",
    "dist": "d1, resi 20 and name CA, resi 40 and name CA",
    "distance": "d2, resi 20 and name CA, resi 40 and name CA",
    "dss": "148l",
    "enable": "148l",
    "extract": "part1, resi 50-60",
    "frame": "1",
    "get": "bg_color",
    "get_area": "148l",
    "get_bond_list": "148l",
    "get_bonds": "148l",
    "get_color_index": "red",
    "get_extent": "148l",
    "get_names": "",
    "get_state": "",
    "get_title": "148l",
    "group": "grp1, 148l",
    "h_add": "resi 20",
    "hbond_network": "148l",
    "help": "load",
    "help_setting": "bg_color",
    "hide": "spheres",
    "hide_dust": "",
    "intra_fit": "148l",
    "intra_rms": "148l",
    "iterate": "resi 20, print(resi)",
    "iterate_state": "1, resi 20, print(x)",
    "label": "resi 20 and name CA, 'CA'",
    "lighting": "ambient, 0.2",
    "map_level": "1.0",
    "mask": "resi 20-40",
    "measure_buriedarea": "148l, 148l",
    "measure_center": "resi 20-40",
    "measure_inertia": "148l",
    "measure_weight": "148l",
    "molecular_weight": "148l",
    "move": "x, 1.0",
    "mset": "1 x10",
    "mutate": "resi 20, ALA",
    "mview": "store",
    "order": "148l",
    "orient": "148l",
    "origin": "resi 20-40",
    "pair_fit": "148l, 148l",
    "pi_interactions": "148l",
    "preset": "publication",
    "protect": "resi 20-40",
    "pseudoatom": "ps1, pos=[0,0,0]",
    "rms": "148l, 148l",
    "rms_cur": "148l, 148l",
    "rotate": "x, 10",
    "scene": "F1, store",
    "select": "sele, resi 20-40",
    "set": "line_width, 2",
    "set_color": "mycol, [1,0,0]",
    "set_name": "148l, 148l",
    "set_symmetry": "148l, 61, 61, 97, 90, 90, 120, P 32 2 1",
    "show": "sticks",
    "show_as": "cartoon",
    "show_dust": "",
    "smooth": "148l",
    "sort": "148l",
    "spectrum": "count, rainbow, 148l",
    "split_chains": "148l",
    "super": "148l, 148l",
    "symexp": "sym1, 148l, 148l, 5",
    "toggle": "148l",
    "toggle_rep": "cartoon",
    "translate": "[1,0,0]",
    "turn": "x, 10",
    "unbond": "resi 20 and name CA, resi 21 and name CA",
    "unmask": "resi 20-40",
    "unset": "line_width",
    "volume_gaussian": "1.0",
    "volume_level": "1.0",
    "volume_quality": "balanced",
    "zoom": "resi 20-40",
}

#: Commands that empty or replace the session. Probed like any other, and the
#: structure is reloaded afterwards -- otherwise every probe after the first
#: ``delete all`` reports "no object" on both hosts, and the comparison passes
#: by agreeing about nothing.
DESTRUCTIVE = frozenset({
    "clear", "del", "delete", "extract", "mclear", "reinit", "reinitialize",
    "remove", "reset", "rm", "split_chains",
})

#: Commands deliberately not run, each with the reason. A skip is a hole in the
#: comparison and is reported as one: silence about a command nobody probed
#: reads exactly like a command that passed.
SKIP: dict[str, str] = {
    "exit": "ends the session",
    "quit": "ends the session",
    "full_screen": "changes the window, and a page has none to change",
    "fullscreen": "changes the window, and a page has none to change",
    "fetch": "network; the browser and the desktop reach it differently by design",
    "fetch_emdb": "network",
    "fetch_ihm": "network",
    "load": "run explicitly as the session's first command, not as a probe",
    "load_map": "needs a map file that neither host bundles",
    "load_mrc": "needs a map file that neither host bundles",
    "load_traj": "needs a trajectory that neither host bundles",
    "load_session": "needs a session file",
    "session_load": "needs a session file",
    "open": "opens a file dialog on the desktop and cannot on a page",
    "png": "writes a file; the browser's filesystem is a different thing",
    "save": "writes a file; the browser's filesystem is a different thing",
    "save_session": "writes a file",
    "session_save": "writes a file",
    "ray": "seconds per call, and it is measured by its own benchmark",
    "rock": "starts a timer that never stops",
    "mplay": "starts a timer that never stops",
    "demo": "builds a large scene; the demo suite covers it",
    "demo_edit": "builds a large scene",
    "wizard": "opens a modal flow that then owns every later key",
}


def normalise(text: str) -> str:
    """Return *text* with host-specific detail removed.

    Parameters
    ----------
    text : str
        A message or an error from the command layer.

    Returns
    -------
    str
        The same text with absolute paths replaced by ``<path>``. Nothing else
        is normalised, and deliberately: an atom count or a distance that
        differs between the hosts is the finding, not noise to be smoothed
        away.
    """
    text = re.sub(r"(?:/[\w.+-]+)+", "<path>", str(text))
    return text.strip()


def probe_commands(
    cmd,
    *,
    reload: Optional[Callable[[], None]] = None,
    only: Optional[tuple[str, ...]] = None,
) -> list[dict[str, Any]]:
    """Run every command once and record what it said.

    Parameters
    ----------
    cmd : chimol.cmd.Cmd
        The command layer to drive.
    reload : callable, optional
        Called after a :data:`DESTRUCTIVE` probe to rebuild the session. Without
        one, those probes still run and everything after them is measured
        against an empty viewer.
    only : tuple of str, optional
        Probe just these commands. For narrowing an investigation; the report
        runs the lot.

    Returns
    -------
    list of dict
        One entry per command, in name order, with ``name``, ``line``,
        ``outcome`` (``"ok"``, ``"error"`` or ``"raised"``) and ``said`` -- the
        normalised messages and errors joined by ``" | "``.
    """
    messages: list[str] = []
    errors: list[str] = []
    previous = (cmd._message_callback, cmd._error_callback)
    cmd.set_message_callback(messages.append)
    cmd.set_error_callback(errors.append)

    results: list[dict[str, Any]] = []
    try:
        for name in sorted(set(cmd.command_names())):
            if only is not None and name not in only:
                continue
            if name in SKIP:
                results.append({
                    "name": name, "line": "", "outcome": "skipped",
                    "said": SKIP[name],
                })
                continue
            arguments = PROBE_ARGS.get(name, "")
            line = f"{name} {arguments}".strip()
            messages.clear()
            errors.clear()
            raised = ""
            try:
                cmd.do(line)
            except BaseException as exc:  # noqa: BLE001 - the finding itself
                raised = f"{type(exc).__name__}: {exc}"
            if raised:
                outcome, said = "raised", raised
            elif errors:
                outcome, said = "error", " | ".join(errors)
            else:
                outcome, said = "ok", " | ".join(messages)
            results.append({
                "name": name,
                "line": line,
                "outcome": outcome,
                "said": normalise(said)[:400],
            })
            if name in DESTRUCTIVE and reload is not None:
                try:
                    reload()
                except Exception as exc:  # noqa: BLE001 - reported, not raised
                    results[-1]["said"] += f" [reload failed: {exc}]"
    finally:
        cmd.set_message_callback(previous[0])
        cmd.set_error_callback(previous[1])
    return results


def _hit_sweep(gui, width: int, height: int, step: int = 4) -> list[str]:
    """Every distinct control a coarse sweep of ``hit_test`` can reach.

    Parameters
    ----------
    gui : chimol.renderer.internal_gui.InternalGui
        The laid-out chrome.
    width, height : int
        Viewport size in logical pixels.
    step : int
        Sweep spacing; four pixels is finer than the smallest control.

    Returns
    -------
    list of str
        Sorted ``"<kind>:<key>"`` labels. Reachability, not appearance: a
        control that is painted and not in this list cannot be pressed.
    """
    found: set[str] = set()
    for y in range(0, int(height), step):
        for x in range(0, int(width), step):
            hit = gui.hit_test(x, y)
            kind = getattr(hit, "kind", None)
            if not kind:
                continue
            key = getattr(hit, "key", None)
            entry = getattr(hit, "entry", None)
            label = getattr(entry, "label", None) if entry is not None else None
            found.add(f"{kind}:{key or label or ''}")
    return sorted(found)


def _menu_tree(gui) -> list[dict[str, Any]]:
    """The menu bar as titles and item labels, opened one at a time.

    Parameters
    ----------
    gui : InternalGui

    Returns
    -------
    list of dict
        ``{"title": ..., "entries": [...]}`` per menu. The menus are the part of
        the chrome a host can render perfectly and never let anybody open, so
        they are enumerated rather than sampled.
    """
    tree: list[dict[str, Any]] = []
    titles = [str(t) for t, _entries in getattr(gui, "menubar", ()) or ()]
    for index, title in enumerate(titles):
        entries: list[str] = []
        try:
            if gui.open_menubar(index):
                menus = getattr(gui, "_menus", None) or []
                if menus:
                    entries = [
                        str(getattr(e, "label", "")) for e in
                        (getattr(menus[0], "entries", None) or [])
                    ]
        except Exception:  # noqa: BLE001 - a menu that cannot open is the finding
            entries = ["<could not open>"]
        finally:
            try:
                gui.close_menus()
            except Exception:
                pass
        tree.append({"title": title, "entries": entries})
    return tree


def chrome_inventory(gui, width: int, height: int) -> dict[str, Any]:
    """Describe what the chrome holds and what of it is reachable.

    Parameters
    ----------
    gui : InternalGui
        The chrome. Laid out here at *width* x *height*, so the two hosts are
        measured at one size whatever their windows are.
    width, height : int
        Logical pixels.

    Returns
    -------
    dict
        ``rows``, ``sequences``, ``menus``, ``windows``, ``bands`` and
        ``reachable``.
    """
    gui.layout(int(width), int(height))
    rows = [
        {
            "name": getattr(row, "name", None),
            "enabled": bool(getattr(row, "enabled", True)),
            "is_header": bool(getattr(row, "is_header", False)),
            "is_group": bool(getattr(row, "is_group", False)),
            "is_selection": bool(getattr(row, "is_selection", False)),
        }
        for row in getattr(gui, "rows", []) or []
    ]
    sequences = [
        {
            "name": getattr(seq, "name", None),
            "columns": len(getattr(seq, "codes", "") or ""),
        }
        for seq in getattr(gui, "sequences", []) or []
    ]
    windows = sorted(
        str(getattr(win, "key", "")) for win in getattr(gui, "windows", []) or []
    )
    bands = {
        "menubar": round(float(gui.menubar_height()), 1),
        "toolbar": round(float(gui.toolbar_height()), 1),
        "top_band": round(float(gui.top_band_height()), 1),
        "sequence": round(float(gui.sequence_height()), 1),
        "column": round(float(gui.effective_column_width()), 1),
        "command": round(float(gui.command_area_height()), 1),
    }
    return {
        "size": [int(width), int(height)],
        "rows": rows,
        "sequences": sequences,
        "menus": _menu_tree(gui),
        "windows": windows,
        "bands": bands,
        "reachable": _hit_sweep(gui, width, height),
    }


#: What a host has to deliver for the engine's gestures to be reachable, as
#: ``(key, description)``. Every one of them is a *host* duty -- the engine
#: cannot probe them by running a command, and each has a control that is
#: perfectly drawn and completely unreachable without it.
HOST_FEATURES: tuple[tuple[str, str], ...] = (
    ("press", "a pointer press, with its button and modifiers"),
    ("double_click", "a second press flagged as double -- the panel's menus open on one"),
    ("move", "a move carrying which buttons are held"),
    ("release", "a release, which is where a click is decided"),
    ("wheel", "a wheel notch carrying a position, so it can scroll a menu"),
    ("wheel_modifiers", "shift+wheel, which is the clipping gesture"),
    ("key", "a key press with its modifiers"),
    ("resize", "a surface resize, so the chrome re-flows"),
    ("context_menu", "a right press opening the viewer's own menu"),
    ("picking", "clicking an atom"),
    ("box_select", "dragging a rubber-band selection"),
    ("labels", "3-D labels, which are rasterised rather than built as quads"),
    ("ray_image", "showing a traced frame over the scene"),
)


def host_features(host) -> dict[str, bool]:
    """Which of :data:`HOST_FEATURES` a host says it delivers.

    Parameters
    ----------
    host : object
        The page's or the window's viewport object. Answers through its
        ``supported_features`` attribute -- a set of the keys above -- because
        "can this host deliver a double click" is not something inspection can
        answer: every host has *some* method that could be called with one.

    Returns
    -------
    dict
    """
    declared = set(getattr(host, "supported_features", ()) or ())
    return {key: (key in declared) for key, _why in HOST_FEATURES}


def report(
    *,
    gui,
    cmd,
    host=None,
    reload: Optional[Callable[[], None]] = None,
    size: tuple[int, int] = INVENTORY_SIZE,
    run_commands: bool = True,
) -> dict[str, Any]:
    """The whole comparison, for one host.

    Parameters
    ----------
    gui : InternalGui
        The chrome.
    cmd : chimol.cmd.Cmd
        The command layer.
    host : object, optional
        The viewport, for :func:`host_features`.
    reload : callable, optional
        Rebuilds the session after a destructive probe.
    size : tuple of int, optional
        The size the chrome is inventoried at.
    run_commands : bool, optional
        Whether to run the command probes. ``False`` gives the inventory alone,
        which is the cheap half.

    Returns
    -------
    dict
        JSON-serialisable, because one half of every comparison crosses out of
        a browser as a string.
    """
    from ..renderer.gpu import backend_name

    width, height = int(size[0]), int(size[1])
    out: dict[str, Any] = {
        "backend": backend_name(),
        "commands": sorted(set(cmd.command_names())),
        "chrome": chrome_inventory(gui, width, height),
        "host": host_features(host),
    }
    out["probes"] = probe_commands(cmd, reload=reload) if run_commands else []
    return out


def compare(desktop: dict[str, Any], browser: dict[str, Any]) -> dict[str, Any]:
    """Diff two :func:`report` results.

    Parameters
    ----------
    desktop, browser : dict

    Returns
    -------
    dict
        ``commands_missing``, ``commands_extra``, ``probe_differences``,
        ``chrome_missing``, ``chrome_extra``, ``menu_differences`` and
        ``host_missing``. Empty everywhere is parity.
    """
    d_cmds, b_cmds = set(desktop["commands"]), set(browser["commands"])
    d_probes = {p["name"]: p for p in desktop.get("probes", [])}
    b_probes = {p["name"]: p for p in browser.get("probes", [])}

    differences = []
    for name in sorted(set(d_probes) & set(b_probes)):
        left, right = d_probes[name], b_probes[name]
        if (left["outcome"], left["said"]) != (right["outcome"], right["said"]):
            differences.append({
                "name": name,
                "line": left["line"],
                "desktop": f"{left['outcome']}: {left['said']}",
                "browser": f"{right['outcome']}: {right['said']}",
            })

    d_reach = set(desktop["chrome"]["reachable"])
    b_reach = set(browser["chrome"]["reachable"])
    d_menus = {m["title"]: m["entries"] for m in desktop["chrome"]["menus"]}
    b_menus = {m["title"]: m["entries"] for m in browser["chrome"]["menus"]}
    menu_differences = [
        {"title": title,
         "desktop_only": sorted(set(d_menus.get(title, ())) - set(b_menus.get(title, ()))),
         "browser_only": sorted(set(b_menus.get(title, ())) - set(d_menus.get(title, ())))}
        for title in sorted(set(d_menus) | set(b_menus))
        if set(d_menus.get(title, ())) != set(b_menus.get(title, ()))
    ]

    return {
        "commands_missing": sorted(d_cmds - b_cmds),
        "commands_extra": sorted(b_cmds - d_cmds),
        "probe_differences": differences,
        "chrome_missing": sorted(d_reach - b_reach),
        "chrome_extra": sorted(b_reach - d_reach),
        "menu_differences": menu_differences,
        "bands_differ": {
            key: [desktop["chrome"]["bands"].get(key),
                  browser["chrome"]["bands"].get(key)]
            for key in sorted(set(desktop["chrome"]["bands"]))
            if desktop["chrome"]["bands"].get(key)
            != browser["chrome"]["bands"].get(key)
        },
        "host_missing": sorted(
            key for key, ok in desktop["host"].items()
            if ok and not browser["host"].get(key)
        ),
    }
