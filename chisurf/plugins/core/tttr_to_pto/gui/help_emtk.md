# TTTR ⇄ .pto

The bare conversion tool between vendor TTTR files and the .pto container. It takes the photon streams of the Datasets workspace: pick them in the **Input** table (or right-click a dataset, *Open in…*, or drag it onto this window). Files enter ChiSurf one way, by dropping them on the ChiSurf window. What a conversion writes appears in the workspace under the dataset it came from.

## Both ways
The direction comes from what you give it.
- A vendor file (.ptu, .spc, .ht3, ...) is packed into a .pto written beside it. The vendor file is kept: packing never deletes it.
- A photon stream of a .pto unpacks its container back to the vendor file(s) it embeds, plus the analysis results it holds. The container is kept: unpacking never touches it.

## One recording, one container
Vendor files used together are packed into one .pto, in file-name order, because a measurement split across m000.spc, m001.spc, ... is one recording, not one container per file. A Becker and Hickl .set next to an .spc is never packed on its own: it is the .spc's sidecar and is picked up automatically with it. A .set offered alone is rejected.

## The table
One row per conversion: Status (Queued, Converting, Verified, Failed, Rejected), Action (Pack or Unpack), the Files you gave and the Result (the files written, or the reason it failed). Packing is verified against the container's checksum; unpacking verifies the recovered instrument bytes. Hover a row for the full paths. Clear history removes the finished rows and never touches a file on disk.

## Not the drop guard
This window is the explicit convert action. The drop guard is the prompt another tool shows when it is handed a vendor file. See the Intensity traces and file tools guide in the documentation.
