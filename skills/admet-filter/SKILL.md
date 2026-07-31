---
name: admet-filter
description: ADMET property prediction and drug-likeness filtering using admet-ai and RDKit
---

# ADMET Filter Skill

Predict Absorption, Distribution, Metabolism, Excretion, and Toxicity (ADMET) properties.

## Capabilities
- 22+ ADMET properties via admet-ai (GNN-based, pretrained on TDC benchmarks)
- Rule-based filtering: Lipinski RO5, Veber, PAINS
- Batch prediction: up to 500 molecules per request
- Local execution: no internet needed after model download

## Usage

### Predict ADMET properties
POST /api/v1/admet/predict with {"smiles": ["CC(=O)Oc1ccccc1C(=O)O"]}

### Filter by drug-likeness rules
POST /api/v1/admet/filter with {"smiles": [...], "rules": ["lipinski", "veber", "pains"]}

See references/admet-properties.md and references/filter-rules.md for details.
