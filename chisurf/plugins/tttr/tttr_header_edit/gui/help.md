# TTTR Header Editor

Open or drop a TTTR file to inspect its header tags. Reading and saving run in
the background. Add tags, edit names/types/values/indices, or remove rows. The
JSON dock shows the last valid header. Invalid edits remain visible in the table
and prevent saving until corrected.

PTU Float8 timing tags use seconds, not nanoseconds; divide a nanosecond value
by one billion before entering it. DateTime values use the native PTU day value.
Float8Array values are JSON lists. Bool accepts true/false or 1/0. Index -1 means
an unindexed tag. Unknown tag types are preserved unchanged.

Save as PTU writes a new file containing the edited header and original photon
events. The original file cannot be selected as the destination. Other source
containers are converted to PTU because they cannot retain arbitrary custom
header tags. Changing structural timing/record tags can change downstream
interpretation; photon records themselves are preserved.
