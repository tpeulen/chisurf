# File Tools

The hub for everything that acts on a *file* rather than on a measurement: a
single window with a navigation list on the left and one lazily-loaded panel
per tool on the right.

Six tools live here, and they belong together because they are the same *kind*
of operation — none of them measures anything. They move a measurement between
containers, read one back, or correct what a vendor wrote into a header:

1. **TTTR Split / Convert** — split a PTU into pieces and convert between
   container formats.
2. **TTTR → Time Windows** — cut a recording down to a macro-time window.
3. **BID → Analysis** — turn a BID file into something the analysis reads.
4. **⇄ .pto** — pack vendor files into a `.pto` container and unpack one back.
5. **PTO Inspector** — read what a `.pto` actually contains before using it.
6. **TTTR header editor** — view and correct the tags a vendor wrote into a
   TTTR header.

## Why a hub

Each sub-tool already exists on its own; the hub embeds them **unchanged**.
What the hub adds is the company: header corrections sit beside the converters
because they are all file surgery, and a broken sub-tool breaks only its own
panel — the rest of the window still opens.

## Adding a panel

Panels are declared in `panels.json` beside the tool module and translated by
the shared panel loader; adding one is a JSON entry, not Python.

Press **Guide** for the walk-through.
