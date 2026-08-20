# Styles

ChiSurf's appearance is a Qt style sheet — a CSS-like file describing how
widgets are drawn. This panel edits those files and applies one.

## Choosing a style

**Style File** lists the `.qss` files in your ChiSurf settings directory. The
shipped ones are copied there on first run, so editing one never touches the
installation and you can always get the originals back.

**Apply** saves the file, applies it to the running application immediately, and
records it as your style so it comes back the next time you start.

## Editing

The editor highlights QSS syntax. A style sheet is a list of rules:

```css
QPushButton {
    background-color: #3a3a3a;
    color: #f0f0f0;
    padding: 4px 10px;
}
QPushButton:hover { background-color: #4a4a4a; }
```

Selectors can name a Qt class (`QPushButton`), a state (`:hover`, `:selected`,
`:pressed`), a sub-control (`QMenuBar::item`) or a specific widget by object
name (`#plugin_manager_toolbar`).

**New** starts an empty file. **Save** writes without applying, so you can work
on a style you are not using.

## Starting over

**Clear All Styles** deletes the `.qss` files in your settings directory and
restores the shipped ones. Anything you wrote there is lost, so copy it out
first if you want to keep it.

## A caution

A style sheet can make things unreadable — text the same colour as its
background, or controls with no visible border. If you apply one and cannot see
enough to fix it, delete the offending file from your settings directory and
restart; ChiSurf falls back to the default appearance.

## Further reading

- [Settings reference](docs/reference/settings.md)
