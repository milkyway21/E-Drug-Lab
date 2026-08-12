---
name: funnel-desmond-long-md
description: Run or resume H9 200 ns Desmond production from short-MD-qualified corrected poses with attempt isolation and hard trajectory validation. Use only for H8-pass candidates and after explicit compute confirmation.
---

# H9 Long MD

Only H8-qualified corrected-pose or validated late-medoid systems may enter H9.
Use the bundled 200 ns protocol and attempt directories. Confirm completion from
continuous trajectory time, expected frame spacing, final CMS readability, topology
consistency, and normal job exit—not filenames or process absence.

Do not submit without `--execute --confirm`. Recovery may resume an authorized queue
but must not overwrite prior attempts.
