from __future__ import annotations

import csv
import json
from pathlib import Path

from masld_agent.evidence_pipeline import run_evidence_nomination
from masld_agent.http_cache import CachedHttp
from masld_agent.models import EvidenceLevel, StructureCandidate
from masld_agent.models import DiseaseScope
from masld_agent.supervisor import run_pipeline
from masld_agent.tools.compound_evidence import load_compound_library, rank_compounds
from masld_agent.tools.pdb import qualify_pocket, structure_candidate_from_records


def test_cached_http_post_json_replays_without_request(tmp_path: Path, monkeypatch) -> None:
    client = CachedHttp(cache_dir=tmp_path)
    calls = []

    def fake_request(method, url, *, params=None, headers=None, json_body=None):
        calls.append((method, url, json_body))
        return {"ok": True, "request": json_body}

    monkeypatch.setattr(client, "_request_json", fake_request)
    first = client.post_json("https://example.test/graphql", json_body={"query": "x"})
    second = client.post_json(
        "https://example.test/graphql",
        json_body={"query": "x"},
        cache_only=True,
    )

    assert first == second
    assert len(calls) == 1


def test_structure_parsing_ranking_fields_and_pocket_gate() -> None:
    entry = {
        "rcsb_entry_info": {"resolution_combined": [1.8]},
        "rcsb_entry_container_identifiers": {"non_polymer_entity_ids": ["1"]},
        "exptl": [{"method": "X-RAY DIFFRACTION"}],
        "rcsb_accession_info": {"initial_release_date": "2024-01-01"},
    }
    entity = {
        "entity_poly": {"pdbx_strand_id": "A, B"},
        "rcsb_entity_source_organism": [{"ncbi_scientific_name": "Homo sapiens"}],
        "rcsb_polymer_entity_container_identifiers": {
            "reference_sequence_identifiers": [
                {"database_name": "UniProt", "database_accession": "P12345"}
            ]
        },
    }
    nonpolymer = [
        {
            "pdbx_entity_nonpoly": {"comp_id": "LIG"},
            "rcsb_nonpolymer_entity": {"pdbx_description": "relevant inhibitor"},
        }
    ]
    structure = structure_candidate_from_records(
        "1ABC_1", entry, entity, target_gene="GENE", nonpolymer_data=nonpolymer
    )
    pocket = qualify_pocket(structure, target_gene="GENE")

    assert structure.resolution_A == 1.8
    assert structure.chains == ["A", "B"]
    assert structure.bound_ligands == ["LIG: relevant inhibitor"]
    assert pocket.qualified is True
    assert pocket.docking_recommendation == "dock"

    predicted = StructureCandidate(
        source="test",
        evidence_level=EvidenceLevel.U,
        confidence=0,
        pdb_id="AF-P12345",
    )
    rejected = qualify_pocket(predicted, target_gene="GENE")
    assert rejected.qualified is False
    assert rejected.docking_recommendation == "do_not_dock"


def _write_library(path: Path) -> None:
    fields = [
        "library_id",
        "name",
        "smiles",
        "target_or_pathway",
        "lipid_rationale",
        "mechanism_hypothesis",
        "evidence_refs",
        "validation_readouts",
    ]
    rows = [
        {
            "library_id": "A",
            "name": "first",
            "smiles": "CCO.Cl",
            "target_or_pathway": "AMPK",
            "lipid_rationale": "Supplied lipid evidence",
            "mechanism_hypothesis": "AMPK modulation",
            "evidence_refs": "PMID:1",
            "validation_readouts": "lipid accumulation;cell viability",
        },
        {
            "library_id": "B",
            "name": "duplicate-parent",
            "smiles": "CCO",
            "target_or_pathway": "AMPK",
            "lipid_rationale": "Supplied lipid evidence",
            "mechanism_hypothesis": "AMPK modulation",
            "evidence_refs": "PMID:2",
            "validation_readouts": "lipid accumulation;cell viability",
        },
        {
            "library_id": "C",
            "name": "second-parent",
            "smiles": "CCN",
            "target_or_pathway": "PPAR_alpha",
            "lipid_rationale": "Supplied lipid evidence",
            "mechanism_hypothesis": "PPAR modulation",
            "evidence_refs": "PMID:3",
            "validation_readouts": "lipid accumulation;cell viability",
        },
        {"library_id": "D", "name": "invalid", "smiles": "not-smiles"},
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_library_identity_dedup_and_unknown_toxicity(tmp_path: Path) -> None:
    library = tmp_path / "library.csv"
    _write_library(library)
    cards = load_compound_library(library)
    ranked = rank_compounds(cards)
    valid = [card for card in ranked if card.identity_valid]

    assert len(valid) == 2
    assert len({card.parent_inchikey for card in valid}) == 2
    assert all("unknown" in card.toxicity_rationale.lower() for card in valid)
    invalid = next(card for card in ranked if card.library_id == "D")
    assert "invalid_or_missing_structure" in invalid.warnings


def test_e0_e6_pipeline_writes_stage_reports_and_ranked_outputs(tmp_path: Path) -> None:
    library = tmp_path / "library.csv"
    _write_library(library)
    output = tmp_path / "run"

    run_evidence_nomination(library, output, final_count=2, online=False)

    assert (output / "target_evidence.json").is_file()
    assert (output / "pocket_manifest.json").is_file()
    assert (output / "compound_evidence.jsonl").is_file()
    assert (output / "toxicity_evidence.csv").is_file()
    assert (output / "nomination_scorecard.csv").is_file()
    assert (output / "mechanism_validation.md").is_file()
    assert (output / "machine_readable_report.json").is_file()
    assert len(list((output / "stage_reports").glob("E*.json"))) == 7

    with (output / "top10_nomination.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2
    assert len({row["parent_inchikey"] for row in rows}) == 2
    machine = json.loads((output / "machine_readable_report.json").read_text(encoding="utf-8"))
    assert len(machine["nominations"]) == 2


def test_main_pipeline_routes_library_to_evidence_envelope(tmp_path: Path) -> None:
    library = tmp_path / "library.csv"
    _write_library(library)
    output = tmp_path / "one-shot"

    result = run_pipeline(
        output,
        disease=DiseaseScope.MASLD,
        library_path=library,
        final_count=2,
        evidence_profile="competition",
    )

    assert result == output.resolve()
    assert (result / "stage_reports" / "E6_nomination_reporting.json").is_file()
