---
name: funnel-drugflow-hepg2
description: H4 ADMET routing with honest DrugFlow, QikProp, or other backend identity.
---

# H4 ADMET

The backend is mandatory and must be reported verbatim. Supported campaign labels
include `drugflow`, `schrodinger_qikprop`, and `hepg2_equiv_admet_ai`; none may be
renamed as another.

For QikProp, run LigPrep first, select one deterministic representative state per
parent, and pass a structure file to QikProp. Do not use unsupported direct-SMILES
`-inp/-osd` combinations. Quarantine empty or failed attempts and never present
QikProp properties as experimental HepG2 viability.

Completion requires complete numeric rows, frozen filtering rules, and an exact
selection manifest when a target count is requested.
