---
name: funnel-shape-screen
description: H3 pose-based Shape screening with Schrödinger-version-aware command validation.
---

# Shape Screen

Extract real best Glide poses before screening. Probe
`$SCHRODINGER/shape_screen_gpu --help` before building the command. Under
Schrödinger 2023-3, never supply `-osd` and `-ocsv` together. A JobDJ submission or
outer `-WAIT` process is not completion; require exit 0, a success log, and a readable
non-empty output.

Set the stage command `cwd` to the declared Shape output directory and use absolute
query/database paths. Schrödinger may place output beside the process CWD rather than
the apparent output argument; validate the expected path before any move. If the file
landed in the task root, move the completed artifact once and fix the reusable adapter,
without recomputing the Shape job.

Read `.sdfgz` through gzip binary decompression before RDKit parsing. If internal
subjobs completed but the wrapper is stale, retain outputs and stop only the exact
known wrapper PID—never use pattern-wide `pkill`.
