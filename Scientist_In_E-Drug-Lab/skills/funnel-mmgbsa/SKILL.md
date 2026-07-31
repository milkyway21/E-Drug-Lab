---
name: funnel-mmgbsa
description: Run H7 Prime MMGBSA on frozen validated XP poses while preserving molecule and pose lineage. Use after H6; perform IFD only when explicitly requested and never substitute missing energy rows.
---

# H7 MMGBSA

Run Prime MMGBSA on the frozen XP pose set and join by molecule/parent ID. IFD is not
part of the default H7 path and must be explicitly requested. Completion requires
numeric binding-energy rows and traceable source poses; missing values remain visible.

Use `masld-agent funnel run/validate --stage H7`. Never perform N-by-N redocking.
