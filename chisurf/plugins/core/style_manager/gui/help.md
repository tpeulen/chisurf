# Styles

ChiSurf's appearance is an emtk style sheet: a small CSS dialect that sets the
colours and spacing emtk draws every control with. This panel edits those
files and applies one.

## Choosing a style

**Style File** lists the `.css` files in your ChiSurf settings directory. The
shipped ones are copied there on first run, so editing one never touches the
installation and you can always get the originals back.

**Apply** saves the file, restyles the running window at once, and records it as
your style so it comes back the next time you start.

## Editing

A style sheet is a list of rules: a selector naming a control, then colours.

```css
:root { --accent: #3d7ab8; }
button       { background-color: #3a3a3a; }
button:hover { background-color: var(--accent); }
window       { background-color: #242424; color: #f0f0f0; padding: 4px 6px; }
```

Selectors name a control and, where it has one, its state or part:
`window`, `widget`, `button` (`:hover`, `:active`), `tab` (`:selected`,
`:hover`), `input` (`:hover`, `:focus`), `menu`, `menu::item` (`:hover`,
`:selected`), `menubar`, `header`, `table` (`:selected`, `:hover`),
`scrollbar` and `scrollbar::handle`, `checkbox`, `slider` and
`slider::handle`, `dock:title`, `plot`. Properties are `background-color`
(`background`), `color`, `border-color`, and for tables and plots
`alternate-background-color` and `grid-color`; `padding` and `border-radius`
set the spacing and rounding of every control. `--name: value` in `:root`
defines a variable that `var(--name)` reads.

While you type:

- **Live preview** — the panel on the right draws sample controls in the
  colours of the sheet as it stands in the buffer, before you save or apply.
  A half-typed rule simply previews the last good parse.
- **Colour swatches** — every `#rrggbb` literal gets a chip in its own
  colour, and the literal is re-tinted to stay readable on the chip.
- **Folding** — the gutter marker (`▾`) next to a line that opens a block
  collapses it to one row (`▸ …`). Click the marker to fold and unfold.

**New** starts a file from a minimal template; a name that exists already is
refused. **Save** writes without applying, so you can work on a style you are
not using. **Open** and **Save As** reach files outside the list; unsaved
changes ask before another style is opened.

## Starting over

**Clear All Styles** deletes the `.css` files in your settings directory and
restores the shipped ones. Anything you wrote there is lost, so copy it out
first if you want to keep it.

## A caution

A style sheet can make things unreadable — text the same colour as its
background. If you apply one and cannot see enough to fix it, delete the file
from your settings directory and restart; ChiSurf falls back to the default
appearance.

## Further reading

- [Settings reference](docs/reference/settings.md)
