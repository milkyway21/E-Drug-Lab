# ADMET Filter Skill

ADMET property prediction and drug-likeness filtering for e-drug-lab.

## Features
- admet-ai: 22+ pretrained ADMET endpoints (Chemprop GNN)
- RDKit: Lipinski RO5, Veber, PAINS rule-based filtering
- Batch processing with configurable batch size

## Routes
- POST /api/v1/admet/predict - batch ADMET prediction
- POST /api/v1/admet/predict/single - single molecule
- POST /api/v1/admet/filter - drug-likeness filtering
- GET /api/v1/admet/health - health check
- GET /api/v1/admet/properties - list properties
