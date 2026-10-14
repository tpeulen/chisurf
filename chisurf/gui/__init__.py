"""Shipped GUI assets: the application icons and the translation catalogues.

The Qt main window that lived here was retired with the Qt shell; the ChiSurf window is
the emtk shell (:mod:`chisurf.emtk.main_app`). What is left is data both the shell and the
plugins read by path -- ``resources/icons/`` (logo, splash art, toolbar icons) and
``i18n/chisurf_<code>.ts`` (the catalogues :mod:`chisurf.emtk.i18n` registers). This package
imports nothing.
"""
