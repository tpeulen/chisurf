"""A fit window's content, drawn by emtk and importable without Qt.

* :mod:`~chisurf.emtk.fit_pages.surface` -- the window's one emtk surface (pages, tabs, dock
  regions, the Code face toggle);
* :mod:`~chisurf.emtk.fit_pages.plots` -- which pages a model's ``view.json`` asks for, as
  classes, with :func:`~chisurf.emtk.fit_pages.plots.model_plot_specs`;
* :mod:`~chisurf.emtk.fit_pages.code_face` -- the model's source and ``view.json``, editable.

The emtk shell draws them in its fit windows (:mod:`chisurf.emtk.fit_window`).
"""
