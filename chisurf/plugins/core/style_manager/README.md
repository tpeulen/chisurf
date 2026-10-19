# Style Manager

Edit, save and apply ChiSurf's emtk style sheets: a small CSS dialect that sets
the colours and spacing emtk draws every control with.

## Features

- Style editor with CSS highlighting, colour swatches and folding
- Live preview of sample controls in the colours of the buffer
- Style files kept in the user's settings folder; shipped styles copied there
- Apply restyles the running window and is remembered for the next start

## Usage

1. Open **Setup › Styles**.
2. Pick a style in **Style File**, or press **New** and give it a name.
3. Edit the rules (`button { background-color: #3a3a3a; }`, `button:hover`, `menu::item:selected`, ...).
4. **Save** to keep the file, **Apply** to restyle the window and keep it as your style.
5. **Clear All Styles** restores the shipped files.

The selectors and properties are listed in the plugin's help (`gui/help.md`).
