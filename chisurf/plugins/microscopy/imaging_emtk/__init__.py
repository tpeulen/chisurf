"""Shared emtk building blocks of the imaging analysis tools (tracking, drift, flow, FRC).

Qt-free by construction: nothing here imports Qt or ``chisurf.gui``. ``app_base`` is the window shell
(settings form, result windows, file dialogs, jobs, help and guide), ``views`` the result views a
``view.json`` cannot express (series plots, image and movie panels, a vector field over an image).
"""
