"""Cross-cutting helpers shared by every layer of core.

Small, dependency-light building blocks that exist so domain modules don't
each roll their own: translation (``i18n``), a stdlib-only HTTP client
(``http``), deprecation/registration decorators, the code-name/display-label
pairing (``labels``), dictionary-driven unit conversion (``units``), the
safe arithmetic-expression engine (``expressions``), and the physical-chemistry
constant tables (``common``).
"""
