#!/usr/bin/env python3
"""Prepare the first two post-top16 Phase F candidates with the original medoid/QC code."""
from __future__ import annotations

import csv
from datetime import datetime
from importlib import import_module

import pandas as pd
from rdkit import Chem, DataStructs
from rdkit.Chem import AllChem
from rdkit.Chem.Scaffolds import MurckoScaffold

from phaseF_common import ANALYSIS_ROOT, MANIFEST, write_json


prepare = import_module("24_prepare_phaseF_medoid_top16")

EXTRA = [("T16866", 48.0, 0.745), ("T3232", 47.6, 1.000)]
EXTRA_MANIFEST = ANALYSIS_ROOT / "phaseF_gpu01_extra2_manifest.csv"
EXTRA_IDS = ANALYSIS_ROOT / "phaseF_gpu01_extra2_ids.txt"
DONE = ANALYSIS_ROOT / "INPUT_GPU01_EXTRA2_QC_DONE.flag"
FAILED = ANALYSIS_ROOT / "INPUT_GPU01_EXTRA2_QC_FAILED.flag"


def verify_combined_diversity(records: list[dict]) -> tuple[float, str, dict[str, tuple[float, str]]]:
    original = pd.read_csv(MANIFEST)
    smiles = dict(zip(original["molecule_id"], original["smiles"]))
    smiles.update({record["molecule_id"]: record["smiles"] for record in records})
    fingerprints = {}
    scaffolds = {}
    for mid, value in smiles.items():
        molecule = Chem.MolFromSmiles(str(value))
        if molecule is None:
            raise RuntimeError(f"{mid}: invalid SMILES")
        fingerprints[mid] = AllChem.GetMorganFingerprintAsBitVect(molecule, 2, nBits=2048)
        scaffold = MurckoScaffold.GetScaffoldForMol(molecule)
        scaffolds[mid] = Chem.MolToSmiles(scaffold, isomericSmiles=False)
    if len(scaffolds) != 18 or len(set(scaffolds.values())) != 18:
        raise RuntimeError("Combined top16+extra2 set has a duplicate exact Murcko scaffold")

    ids = list(fingerprints)
    maximum = -1.0
    maximum_pair = ""
    per_extra: dict[str, tuple[float, str]] = {}
    for index, first in enumerate(ids):
        for second in ids[index + 1:]:
            similarity = float(DataStructs.TanimotoSimilarity(fingerprints[first], fingerprints[second]))
            if similarity > maximum:
                maximum, maximum_pair = similarity, f"{first}:{second}"
    for mid, _, _ in EXTRA:
        best = max(
            (float(DataStructs.TanimotoSimilarity(fingerprints[mid], fingerprints[other])), other)
            for other in ids if other != mid
        )
        per_extra[mid] = best
    if maximum >= 0.70:
        raise RuntimeError(f"Combined diversity QC failed: {maximum:.3f} ({maximum_pair})")
    return maximum, maximum_pair, per_extra


def main() -> None:
    ANALYSIS_ROOT.mkdir(parents=True, exist_ok=True)
    DONE.unlink(missing_ok=True)
    FAILED.unlink(missing_ok=True)
    records = []
    for rank, (mid, planned_time, expected_fraction) in enumerate(EXTRA, 17):
        print(f"PREP extra rank={rank} {mid} medoid={planned_time:.1f} ns", flush=True)
        record = prepare.prepare_one(mid, planned_time, expected_fraction)
        records.append(record)
        print(
            f"PASS {mid} actual={record['actual_medoid_time_ns']:.3f} ns "
            f"fraction={record['dominant_cluster_fraction']:.6f} "
            f"min={record['min_protein_ligand_A']:.3f} A",
            flush=True,
        )

    records = prepare.add_metadata(records)
    maximum, maximum_pair, per_extra = verify_combined_diversity(records)
    for offset, record in enumerate(records, 17):
        similarity, partner = per_extra[record["molecule_id"]]
        record.update({
            "selection_rank": offset,
            "post_top16_rank": offset - 16,
            "selection_class": "A_target_pocket_retained",
            "selection_rationale": (
                "deterministic next candidate after top16; target-pocket retention, "
                "late contacts, convergence, and combined-18 scaffold diversity"
            ),
            "batch_max_pairwise_morgan_tanimoto": maximum,
            "batch_max_similarity_pair": maximum_pair,
            "candidate_max_morgan_tanimoto": similarity,
            "candidate_max_similarity_partner": partner,
            "assigned_gpu": offset - 17,
            "queue_predecessor": "T39220" if offset == 17 else "T10425",
            "requested_protocol": "2ns_equilibration+200ns_production",
        })

    with EXTRA_MANIFEST.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    EXTRA_IDS.write_text("\n".join(record["molecule_id"] for record in records) + "\n")
    write_json(
        ANALYSIS_ROOT / "phaseF_gpu01_extra2_selection.json",
        {
            "created_at": datetime.now().isoformat(),
            "ids": [record["molecule_id"] for record in records],
            "combined_set_size": 18,
            "combined_max_morgan_tanimoto": maximum,
            "combined_max_similarity_pair": maximum_pair,
            "manifest": str(EXTRA_MANIFEST),
        },
    )
    DONE.write_text(
        f"{datetime.now().isoformat()}\nvalid=2/2\nmanifest={EXTRA_MANIFEST}\n"
    )
    print(f"DONE extra2 input CMS validated; manifest={EXTRA_MANIFEST}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        ANALYSIS_ROOT.mkdir(parents=True, exist_ok=True)
        FAILED.write_text(f"{datetime.now().isoformat()}\n{error!r}\n")
        raise
