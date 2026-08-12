---
name: funnel-glide-xp
description: Refine the frozen H5 parent set with H6 Glide XP using preserved poses and the same validated receptor grid. Use only after H5 validation; do not redock the entire upstream library.
---

# H6 Glide XP

Select unique parents from validated H5 SP results, preserve their actual poses and
reuse the same grid. Configure an existing XP runner as `stages.H6.command`.
Validate numeric XP scores and a readable pose viewer before advancing.

Preview first; production requires `--execute --confirm`. Never XP the full upstream
library when a frozen target subset exists.
