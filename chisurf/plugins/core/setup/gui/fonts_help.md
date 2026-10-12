# Fonts

The faces, sizes and magnification of the ChiSurf window. Every change applies on the next frame -- text is rasterised again and every window relays itself out -- and is saved to `gui.fonts` in `settings_chisurf.yaml`, so the next start uses it too. **Reset to defaults** returns to the shipped look.

## Interface

**Size** is the size of all interface text in points (8 pt shipped). Headings, captions and code follow it unless they have a size of their own. **Magnification** scales the whole window -- text, spacing, icons and plots -- the way a browser zoom does; clicks still land where things are drawn. **Face** `monospace` is the built-in face, the sharpest and the fastest; any installed family works.

## Editor and console

The face and size of the Console dock, the code editor and code blocks. Only monospaced families are listed: the editor lines its columns up on a fixed character width. A size of 0 (*Same as interface*) follows the interface size. A font chosen in the code editor's own settings wins inside that tool.

## Documentation

**Text face** and **Text size** set the running text of the Documentation dock and the help windows; `prose` picks Verdana, else DejaVu Sans. **Heading scale** is the ratio between heading levels: a fourth-level heading is the text size times it, a page title times its fourth power. Captions sit one step below the text unless given a size. The dock's A− / A+ zoom on top of these.

## Formulas

The text face of formulas -- it needs an italic style; `auto` picks STIX Two, else Times New Roman, else DejaVu Serif. Symbols the face lacks come from the installed mathematical faces.

## Rendering

**Resolution** is the glyph raster scale of installed faces: 1× puts one glyph pixel on one screen pixel on the pixel grid (sharpest); higher values rasterise finer and scale down (smoother, slightly softer). **Smooth edges** turns grey-scale anti-aliasing on or off. Hinting cannot be chosen: the rasteriser does not offer it. **Fallback faces** are tried, in order, for a character the chosen face lacks -- CJK, mathematical symbols, subscripts -- before the faces the system provides. Any face field also takes a chain of its own, such as `Inter, Verdana, prose`.

## Further reading

- [Settings](docs/getting_started/settings.md)
