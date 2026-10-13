#!/usr/bin/env python

# Get the cookiecutter variables
plugin_name = "{{ cookiecutter.plugin_name }}"
plugin_display_name = "{{ cookiecutter.plugin_display_name }}"

print(f"\nPlugin '{plugin_display_name}' created successfully!")
print(f"To use your plugin, copy the '{plugin_name}' directory to the ChiSurf plugins directory.")
print(f"Its window is gui/{plugin_name}.view.json drawn by emtk (gui/app.py); open it with")
print(f"  python -m chisurf.plugins.{plugin_name}")
print("Replace gui/help.md and gui/guide.json, and the placeholder icon.png.")
