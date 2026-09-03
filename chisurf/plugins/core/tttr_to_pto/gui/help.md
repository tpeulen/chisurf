# TTTR ⇄ PTO

The bare conversion tool between vendor TTTR files and the `.pto` container.
Drop files on it; nothing else is required.

It works **both ways**, telling the direction from what was dropped:

- A vendor file (`.ptu`, `.spc`, `.ht3`, …) is **packed** into a `.pto`
  written beside it. The vendor file is kept — packing never deletes it.
- A `.pto` is **unpacked** back to the vendor file(s) it embeds. The container
  is kept — unpacking never touches it.

Vendor files dropped **together** are packed into **one** `.pto`, in lexical
order by name, because a measurement split across `m000.spc`, `m001.spc`, …
is one recording, not one container per file. A Becker & Hickl `.set` dropped
alongside is never itself packed: it is an `.spc`'s sidecar and is picked up
automatically with the file it belongs to.

This window is the explicit "convert" action. It is distinct from the drop
*guard* (which asks permission when a convertible file lands on some other
tool) and from the `tttr/filetools` hub (which transcodes between vendor
formats and has nothing to do with `.pto`).

Press **Guide** for the walk-through.
