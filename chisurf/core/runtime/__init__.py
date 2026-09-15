"""Execution seams: how core computations meet their environment.

The model layer must run headless (CLI, server, tests) and inside the Qt GUI.
The modules here are the narrow seams that make both work without core ever
importing a widget toolkit: the presenter a view registers for GUI-thread
notification (``presentation``), the terminal progress bar for headless
long-runners (``progress``), the memoization fingerprinting that lets
workflow steps skip recomputation (``analysis_cache``), and the
dependency-API compatibility shims applied at start-up (``compat``).
"""
