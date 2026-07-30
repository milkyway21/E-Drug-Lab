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

Read `.sdfgz` through gzip binary decompression before RDKit parsing. If internal
subjobs completed but the wrapper is stale, retain outputs and stop only the exact
known wrapper PID—never use pattern-wide `pkill`.
