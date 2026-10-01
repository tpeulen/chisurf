# TTTR ⇄ .pto

The bare conversion tool between vendor TTTR files and the .pto container. Drop files on it, or press Add files...; nothing else is required.

## Both ways
The direction comes from what you give it.
- A vendor file (.ptu, .spc, .ht3, ...) is packed into a .pto written beside it. The vendor file is kept: packing never deletes it.
- A .pto is unpacked back to the vendor file(s) it embeds, plus the analysis results it holds. The container is kept: unpacking never touches it.

## One recording, one container
Vendor files given together are packed into one .pto, in file-name order, because a measurement split across m000.spc, m001.spc, ... is one recording, not one container per file. A Becker and Hickl .set next to an .spc is never packed on its own: it is the .spc's sidecar and is picked up automatically with it. A .set offered alone is rejected.

## The table
One row per conversion: Status (Queued, Converting, Verified, Failed, Rejected), Action (Pack or Unpack), the Files you gave and the Result (the files written, or the reason it failed). Packing is verified against the container's checksum; unpacking verifies the recovered instrument bytes. Hover a row for the full paths. Clear history removes the finished rows and never touches a file on disk.

## Not the drop guard
This window is the explicit convert action. The drop guard is the prompt another tool shows when a vendor file lands on it. See the Intensity traces and file tools guide in the documentation.
