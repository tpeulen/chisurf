---
type: PRD
prd: "83"
title: "PRD-83: Retire pyqtgraph — the umbrella, and the 3-D half nobody owned"
description: pyqtgraph is a declared dependency reached from 14 files, one .native escape hatch, and three subsystems that are not plotting at all — OpenGL views, a parameter tree, and a dock area. PRD-64 owns the 2-D seam; this concept owns the end state (pyqtgraph absent from the environment) and the parts PRD-64 does not reach. The 3-D half is closed here: ChiMOL renders through PyOpenGL on a plain QOpenGLWidget and imports nothing from pyqtgraph.
status: in-progress
phase: "3-D half landed; 2-D seam is PRD-64"
resource: test/pyqtgraph_import_allowlist.txt
tags: [prd, gui, plotting, opengl, dependencies, chimol, chiplot]
timestamp: '2026-08-06T00:00:00Z'
---

# Where to pick this up

**The 3-D half is done** (2026-08-06). ChiMOL's renderer is a plain
`QOpenGLWidget` driving PyOpenGL directly; the last `import pyqtgraph.opengl`
in the plugin was a 13-line module (`renderer/backend.py`) that computed a
`_HAVE_GL` flag **nothing imported**, and the shims it left behind are gone with
it. What remains, in order of how much it blocks the end state:

1. **The 2-D seam — PRD-64**, 14 files still importing pyqtgraph and 12
   `.native` escapes. That is the bulk and it has its own concept; do not
   duplicate the plan here.
2. **`pyqtgraph.opengl`, still used twice.** chiplot's own backend builds its
   3-D volume view on it (`backends/pyqtgraph_backend.py`), and the exploration
   tool's UMAP plot does the same. Both are *3-D* views behind a 2-D-shaped
   facade, so PRD-64's "swap the backend" plan does not describe them: chiplot
   needs a 3-D surface of its own, or those two views need to render the way
   ChiMOL now does.
3. **`pyqtgraph.parametertree`**, in the exploration tool's parameter editor.
   Not plotting at all — a property-sheet widget, and the closest thing in the
   tree is AutoForm, which is what a replacement should be measured against.
4. **`pyqtgraph.dockarea`**, already guarded separately by the seam test, and
   duplicated in the tree's own dock area.

Only when all four are true does the dependency come out of `pixi.toml`
(`pyqtgraph = "0.13.*"`), which is the one check that cannot be argued with.

# Why this is a concept and not a line in PRD-64

PRD-64 is about a **seam**: route every plotting call through `chiplot` so
pyqtgraph becomes swappable. That is the right frame for 2-D plotting and the
wrong one for the rest, because three of the four uses above are not plotting.
Filing them under a plotting PRD is how they stayed unowned — the ChiMOL
OpenGL module sat on the allow-list for months described as *"the ChiMOL OpenGL
module owned by PRD-57"*, in a PRD about **command parity** whose renderer
section is about an immediate-mode GUI, not about pyqtgraph.

So: PRD-64 owns the plotting seam and its allow-list, PRD-57 owns ChiMOL's
renderer direction, and this concept owns the **question** — *is pyqtgraph still
installed, and what is the last thing keeping it here?*

# What the 3-D half turned out to be

Worth writing down, because the size of it is the finding.

ChiMOL has not rendered through pyqtgraph for a long time: `renderer/qtgl.py` is
a `QOpenGLWidget` with its own shaders, its own matrices and its own picking.
What survived was **shaped** like pyqtgraph without being it:

* `renderer/backend.py` — 13 lines, `import pyqtgraph.opengl as gl`, a
  `_HAVE_GL` flag. **No module imported it.** It was the plugin's only entry on
  the import allow-list, so the list said ChiMOL was unported when the only
  unported thing was a file nobody used;
* `self.opts` — a dictionary mirroring `fov` and `center`, with the comment
  *"Compatibility with picking helpers"*, plus a `cameraPosition()` returning a
  `QVector3D`. Together these are pyqtgraph's `GLViewWidget` camera API.

The shim was not merely unnecessary, it was **actively harmful**, and this is
the durable lesson: a compatibility layer nobody re-checks becomes a *second
store* of a derived value. `opts["center"]` was maintained by
`_update_center_opt` from **seven** call sites and read by nothing, while the
real value was recomputed on demand in `_build_matrices`; `opts["fov"]` was a
second copy of `self._fov`. And the picking helper the shim existed for read
`opts["center"]` — a `QVector3D` — straight into `numpy.asarray`, which raises,
so **every click in the viewport raised** and the exception was swallowed. The
compatibility layer's only consumer was broken *by* the compatibility layer.

Closed by pointing the picker at the renderer's real projection
(`project_to_screen`, the same matrices `paintGL` uses) and deleting the shim,
the mirror and the dead module. Detail in
[pymol parity](../plugins/pymol-parity.md).

# Definition of done

- [x] no `import pyqtgraph` anywhere under `chisurf/plugins/chimol/`
- [x] no pyqtgraph-shaped compatibility surface on the ChiMOL renderer
      (`opts`, `cameraPosition`)
- [ ] `test/pyqtgraph_import_allowlist.txt` is empty
- [ ] `test/chiplot_native_allowlist.txt` is empty
- [ ] no `pyqtgraph.opengl` in the tree — chiplot has a 3-D surface of its own,
      or its two consumers render directly
- [ ] no `pyqtgraph.parametertree` — the parameter editor is measured against
      AutoForm and ported or kept deliberately
- [ ] no `pyqtgraph.dockarea`
- [ ] `pyqtgraph` removed from `pixi.toml`, and the package count before and
      after recorded here

# How to measure

The claims above are counts, so re-derive them rather than trusting this list:

```bash
grep -rln "^\s*\(import pyqtgraph\|from pyqtgraph\)" --include="*.py" chisurf/ | wc -l
grep -rho "pyqtgraph\.\w*" --include="*.py" chisurf/ modules/ | sort | uniq -c | sort -rn
grep -vc "^#\|^$" test/pyqtgraph_import_allowlist.txt
grep -vc "^#\|^$" test/chiplot_native_allowlist.txt
```

Both allow-lists are **shrinking** records, never somewhere to add a file to
make the guard pass.

# Related

* [PRD-64](prd-64.md) — the chiplot seam: the 2-D plan, the call-site
  migration, and the allow-list this concept counts.
* [PRD-57](prd-57.md) — ChiMOL command parity and renderer direction.
* [chiplot](../subsystems/chiplot.md) — the seam as it stands.
* [pymol parity](../plugins/pymol-parity.md) — what the 3-D shim was hiding.
