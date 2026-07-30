"""
e-drug lab SDF 分子库 API 路由
"""
import uuid
import os
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func, and_, or_
from app.repositories.models import SDFMolecule
from app.services.sdf_sync import sync_sdf_library, get_sdf_molecule_count, get_sdf_file_count
from app.db import get_db
from app.core.errors import MoleculeLibraryError, AppError
from app.core.paths import ensure_safe_path, get_repo_root

router = APIRouter(prefix="/api/v1/molecule-db", tags=["Molecule Database"])

try:
    from rdkit import Chem
    from rdkit.Chem.Draw import rdMolDraw2D
    _HAS_RDKIT = True
except ImportError:
    _HAS_RDKIT = False


class SyncRequest(BaseModel):
    sdf_directory: Optional[str] = Field(None)


def _serialize_molecule(m: SDFMolecule) -> dict:
    return {
        "id": str(m.id), "name": m.name, "smiles": m.smiles, "inchi": m.inchi, "inchikey": m.inchikey,
        "molecular_formula": m.molecular_formula, "molecular_weight": m.molecular_weight,
        "num_atoms": m.num_atoms, "num_heavy_atoms": m.num_heavy_atoms,
        "num_rotatable_bonds": m.num_rotatable_bonds, "num_h_bond_donors": m.num_h_bond_donors,
        "num_h_bond_acceptors": m.num_h_bond_acceptors, "logp": m.logp, "tpsa": m.tpsa, "qed": m.qed,
        "sa_score": m.sa_score,
        "sdf_filename": m.sdf_filename, "sdf_file_path": m.sdf_file_path, "sdf_file_hash": m.sdf_file_hash,
        "file_size_bytes": m.file_size_bytes, "conformer_index": m.conformer_index,
        "total_conformers": m.total_conformers, "sdf_properties": m.sdf_properties,
        "tags": m.tags or [], "created_at": m.created_at.isoformat() if m.created_at else None,
    }


# ── Shared filter helper ────────────────────────────────────────
def _apply_filters(query, **kw):
    """Apply filter parameters to a molecule query. Returns modified query."""
    if kw.get("search"):
        t = f"%{kw['search']}%"
        query = query.filter(
            SDFMolecule.name.ilike(t) | SDFMolecule.smiles.ilike(t) |
            SDFMolecule.molecular_formula.ilike(t) | SDFMolecule.inchikey.ilike(t)
        )
    pairs = [
        ("min_mw", "max_mw", SDFMolecule.molecular_weight),
        ("min_logp", "max_logp", SDFMolecule.logp),
        ("min_qed", "max_qed", SDFMolecule.qed),
        ("min_sa_score", "max_sa_score", SDFMolecule.sa_score),
        ("min_tpsa", "max_tpsa", SDFMolecule.tpsa),
        ("min_rotatable_bonds", "max_rotatable_bonds", SDFMolecule.num_rotatable_bonds),
        ("min_hbd", "max_hbd", SDFMolecule.num_h_bond_donors),
        ("min_hba", "max_hba", SDFMolecule.num_h_bond_acceptors),
        ("min_heavy_atoms", "max_heavy_atoms", SDFMolecule.num_heavy_atoms),
    ]
    for lo_key, hi_key, col in pairs:
        lo = kw.get(lo_key)
        hi = kw.get(hi_key)
        if lo is not None: query = query.filter(col >= lo)
        if hi is not None: query = query.filter(col <= hi)

    lip = kw.get("lipinski_pass")
    if lip is True:
        query = query.filter(and_(
            SDFMolecule.molecular_weight <= 500,
            SDFMolecule.logp <= 5,
            SDFMolecule.num_h_bond_donors <= 5,
            SDFMolecule.num_h_bond_acceptors <= 10,
        ))
    elif lip is False:
        query = query.filter(or_(
            SDFMolecule.molecular_weight > 500,
            SDFMolecule.logp > 5,
            SDFMolecule.num_h_bond_donors > 5,
            SDFMolecule.num_h_bond_acceptors > 10,
            SDFMolecule.molecular_weight.is_(None),
            SDFMolecule.logp.is_(None),
            SDFMolecule.num_h_bond_donors.is_(None),
            SDFMolecule.num_h_bond_acceptors.is_(None),
        ))
    if kw.get("sdf_filename"):
        query = query.filter(SDFMolecule.sdf_filename.ilike(f"%{kw['sdf_filename']}%"))
    return query


# ── Filter param extraction (shared across endpoints) ───────────
FILTER_KEYS = [
    "search", "min_mw", "max_mw", "min_logp", "max_logp",
    "min_qed", "max_qed", "min_sa_score", "max_sa_score",
    "min_tpsa", "max_tpsa",
    "min_rotatable_bonds", "max_rotatable_bonds",
    "min_hbd", "max_hbd", "min_hba", "max_hba",
    "min_heavy_atoms", "max_heavy_atoms",
    "lipinski_pass", "sdf_filename",
]


def _extract_filters(
    search: Optional[str] = Query(None),
    min_mw: Optional[float] = Query(None), max_mw: Optional[float] = Query(None),
    min_logp: Optional[float] = Query(None), max_logp: Optional[float] = Query(None),
    min_qed: Optional[float] = Query(None), max_qed: Optional[float] = Query(None),
    min_sa_score: Optional[float] = Query(None), max_sa_score: Optional[float] = Query(None),
    min_tpsa: Optional[float] = Query(None), max_tpsa: Optional[float] = Query(None),
    min_rotatable_bonds: Optional[int] = Query(None), max_rotatable_bonds: Optional[int] = Query(None),
    min_hbd: Optional[int] = Query(None), max_hbd: Optional[int] = Query(None),
    min_hba: Optional[int] = Query(None), max_hba: Optional[int] = Query(None),
    min_heavy_atoms: Optional[int] = Query(None), max_heavy_atoms: Optional[int] = Query(None),
    lipinski_pass: Optional[bool] = Query(None),
    sdf_filename: Optional[str] = Query(None),
) -> dict:
    return {k: v for k, v in locals().items() if k in FILTER_KEYS}


# ── Endpoints ──────────────────────────────────────────────────

@router.get("/molecules")
async def list_molecules(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: str = Query(default="molecular_weight"),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
    search: Optional[str] = Query(None),
    min_mw: Optional[float] = Query(None), max_mw: Optional[float] = Query(None),
    min_logp: Optional[float] = Query(None), max_logp: Optional[float] = Query(None),
    min_qed: Optional[float] = Query(None), max_qed: Optional[float] = Query(None),
    min_sa_score: Optional[float] = Query(None), max_sa_score: Optional[float] = Query(None),
    min_tpsa: Optional[float] = Query(None), max_tpsa: Optional[float] = Query(None),
    min_rotatable_bonds: Optional[int] = Query(None), max_rotatable_bonds: Optional[int] = Query(None),
    min_hbd: Optional[int] = Query(None), max_hbd: Optional[int] = Query(None),
    min_hba: Optional[int] = Query(None), max_hba: Optional[int] = Query(None),
    min_heavy_atoms: Optional[int] = Query(None), max_heavy_atoms: Optional[int] = Query(None),
    lipinski_pass: Optional[bool] = Query(None),
    sdf_filename: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    filters = _extract_filters(
        search=search, min_mw=min_mw, max_mw=max_mw,
        min_logp=min_logp, max_logp=max_logp,
        min_qed=min_qed, max_qed=max_qed,
        min_sa_score=min_sa_score, max_sa_score=max_sa_score,
        min_tpsa=min_tpsa, max_tpsa=max_tpsa,
        min_rotatable_bonds=min_rotatable_bonds, max_rotatable_bonds=max_rotatable_bonds,
        min_hbd=min_hbd, max_hbd=max_hbd,
        min_hba=min_hba, max_hba=max_hba,
        min_heavy_atoms=min_heavy_atoms, max_heavy_atoms=max_heavy_atoms,
        lipinski_pass=lipinski_pass, sdf_filename=sdf_filename,
    )
    query = _apply_filters(db.query(SDFMolecule), **filters)

    sort_cols = {
        "molecular_weight": SDFMolecule.molecular_weight, "logp": SDFMolecule.logp,
        "qed": SDFMolecule.qed, "sa_score": SDFMolecule.sa_score,
        "num_heavy_atoms": SDFMolecule.num_heavy_atoms,
        "num_rotatable_bonds": SDFMolecule.num_rotatable_bonds,
        "tpsa": SDFMolecule.tpsa, "created_at": SDFMolecule.created_at,
        "name": SDFMolecule.name, "molecular_formula": SDFMolecule.molecular_formula,
        "num_h_bond_donors": SDFMolecule.num_h_bond_donors,
        "num_h_bond_acceptors": SDFMolecule.num_h_bond_acceptors,
    }
    sort_col = sort_cols.get(sort_by, SDFMolecule.molecular_weight)
    query = query.order_by(desc(sort_col) if sort_order == "desc" else asc(sort_col))
    total = query.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    molecules = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "molecules": [_serialize_molecule(m) for m in molecules],
        "pagination": {"page": page, "page_size": page_size, "total": total, "total_pages": total_pages},
    }


@router.get("/molecules/{molecule_id}")
async def get_molecule(molecule_id: str, db: Session = Depends(get_db)):
    mol = db.query(SDFMolecule).filter(SDFMolecule.id == molecule_id).first()
    if not mol:
        raise MoleculeLibraryError(reason=f"分子不存在：{molecule_id}", library_id=molecule_id)
    return _serialize_molecule(mol)


@router.post("/sync")
async def trigger_sync(body: SyncRequest, db: Session = Depends(get_db)):
    from app.config import get_settings
    settings = get_settings()
    if body.sdf_directory:
        sdf_dir = str(ensure_safe_path(body.sdf_directory, must_exist=True))
    elif settings.sdf_directory:
        sdf_dir = str(ensure_safe_path(settings.sdf_directory, must_exist=True))
    else:
        sdf_dir = str(get_repo_root() / "molecules" / "sdf")
    if not os.path.isdir(sdf_dir):
        raise MoleculeLibraryError(reason=f"SDF 目录不存在：{sdf_dir}")
    sync_result = sync_sdf_library(db, sdf_dir)
    return {"status": "completed", "sdf_directory": sdf_dir, "sync_result": sync_result.to_dict()}


@router.get("/sync/status")
async def sync_status(db: Session = Depends(get_db)):
    total_molecules = get_sdf_molecule_count(db)
    total_files = get_sdf_file_count(db)
    file_stats = db.query(
        SDFMolecule.sdf_filename, SDFMolecule.sdf_file_path,
        func.count(SDFMolecule.id).label("conformer_count"),
        func.max(SDFMolecule.total_conformers).label("total_conformers"),
    ).group_by(SDFMolecule.sdf_filename, SDFMolecule.sdf_file_path).all()
    return {
        "total_molecules": total_molecules, "total_sdf_files": total_files,
        "sdf_files": [{"filename": r.sdf_filename, "file_path": r.sdf_file_path,
                        "conformers_in_db": r.conformer_count, "total_conformers_in_file": r.total_conformers}
                      for r in file_stats],
    }


@router.get("/stats")
async def library_statistics(
    search: Optional[str] = Query(None),
    min_mw: Optional[float] = Query(None), max_mw: Optional[float] = Query(None),
    min_logp: Optional[float] = Query(None), max_logp: Optional[float] = Query(None),
    min_qed: Optional[float] = Query(None), max_qed: Optional[float] = Query(None),
    min_sa_score: Optional[float] = Query(None), max_sa_score: Optional[float] = Query(None),
    min_tpsa: Optional[float] = Query(None), max_tpsa: Optional[float] = Query(None),
    min_rotatable_bonds: Optional[int] = Query(None), max_rotatable_bonds: Optional[int] = Query(None),
    min_hbd: Optional[int] = Query(None), max_hbd: Optional[int] = Query(None),
    min_hba: Optional[int] = Query(None), max_hba: Optional[int] = Query(None),
    min_heavy_atoms: Optional[int] = Query(None), max_heavy_atoms: Optional[int] = Query(None),
    lipinski_pass: Optional[bool] = Query(None),
    sdf_filename: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Statistics, optionally filtered to current selection."""
    filters = _extract_filters(
        search=search, min_mw=min_mw, max_mw=max_mw,
        min_logp=min_logp, max_logp=max_logp,
        min_qed=min_qed, max_qed=max_qed,
        min_sa_score=min_sa_score, max_sa_score=max_sa_score,
        min_tpsa=min_tpsa, max_tpsa=max_tpsa,
        min_rotatable_bonds=min_rotatable_bonds, max_rotatable_bonds=max_rotatable_bonds,
        min_hbd=min_hbd, max_hbd=max_hbd,
        min_hba=min_hba, max_hba=max_hba,
        min_heavy_atoms=min_heavy_atoms, max_heavy_atoms=max_heavy_atoms,
        lipinski_pass=lipinski_pass, sdf_filename=sdf_filename,
    )
    base = _apply_filters(db.query(SDFMolecule), **filters)
    st = base.with_entities(
        func.count(SDFMolecule.id).label("total"),
        func.avg(SDFMolecule.molecular_weight).label("avg_mw"),
        func.min(SDFMolecule.molecular_weight).label("min_mw"),
        func.max(SDFMolecule.molecular_weight).label("max_mw"),
        func.avg(SDFMolecule.logp).label("avg_logp"),
        func.avg(SDFMolecule.qed).label("avg_qed"),
        func.avg(SDFMolecule.sa_score).label("avg_sa"),
        func.avg(SDFMolecule.tpsa).label("avg_tpsa"),
        func.avg(SDFMolecule.num_rotatable_bonds).label("avg_rot"),
        func.avg(SDFMolecule.num_h_bond_donors).label("avg_hbd"),
        func.avg(SDFMolecule.num_h_bond_acceptors).label("avg_hba"),
        func.avg(SDFMolecule.num_heavy_atoms).label("avg_heavy"),
    ).first()

    lip_total = base.filter(
        SDFMolecule.molecular_weight.isnot(None), SDFMolecule.logp.isnot(None),
        SDFMolecule.num_h_bond_donors.isnot(None), SDFMolecule.num_h_bond_acceptors.isnot(None),
    ).count()
    lip_pass = base.filter(
        SDFMolecule.molecular_weight <= 500, SDFMolecule.logp <= 5,
        SDFMolecule.num_h_bond_donors <= 5, SDFMolecule.num_h_bond_acceptors <= 10,
    ).count()

    any_filter = any(
        v is not None for k, v in filters.items()
        if k not in ("search",)
    )

    def r(v, d=2):
        return round(v, d) if v is not None else None

    return {
        "total_molecules": st.total,
        "total_sdf_files": get_sdf_file_count(db),
        "filtered": any_filter,
        "statistics": {
            "molecular_weight": {"avg": r(st.avg_mw), "min": r(st.min_mw), "max": r(st.max_mw)},
            "logp_avg": r(st.avg_logp, 2),
            "qed_avg": r(st.avg_qed, 4),
            "sa_score_avg": r(st.avg_sa, 3),
            "tpsa_avg": r(st.avg_tpsa, 2),
            "rotatable_bonds_avg": r(st.avg_rot, 2),
            "hbd_avg": r(st.avg_hbd, 2),
            "hba_avg": r(st.avg_hba, 2),
            "heavy_atoms_avg": r(st.avg_heavy, 2),
            "lipinski": {
                "pass_count": lip_pass,
                "fail_count": lip_total - lip_pass,
                "total_evaluated": lip_total,
            } if lip_total > 0 else None,
        },
    }


@router.get("/distributions")
async def molecule_distributions(
    search: Optional[str] = Query(None),
    min_mw: Optional[float] = Query(None), max_mw: Optional[float] = Query(None),
    min_logp: Optional[float] = Query(None), max_logp: Optional[float] = Query(None),
    min_qed: Optional[float] = Query(None), max_qed: Optional[float] = Query(None),
    min_sa_score: Optional[float] = Query(None), max_sa_score: Optional[float] = Query(None),
    min_tpsa: Optional[float] = Query(None), max_tpsa: Optional[float] = Query(None),
    min_rotatable_bonds: Optional[int] = Query(None), max_rotatable_bonds: Optional[int] = Query(None),
    min_hbd: Optional[int] = Query(None), max_hbd: Optional[int] = Query(None),
    min_hba: Optional[int] = Query(None), max_hba: Optional[int] = Query(None),
    min_heavy_atoms: Optional[int] = Query(None), max_heavy_atoms: Optional[int] = Query(None),
    lipinski_pass: Optional[bool] = Query(None),
    sdf_filename: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Distribution histograms for every property, reflecting other active filters."""
    filters = _extract_filters(
        search=search, min_mw=min_mw, max_mw=max_mw,
        min_logp=min_logp, max_logp=max_logp,
        min_qed=min_qed, max_qed=max_qed,
        min_sa_score=min_sa_score, max_sa_score=max_sa_score,
        min_tpsa=min_tpsa, max_tpsa=max_tpsa,
        min_rotatable_bonds=min_rotatable_bonds, max_rotatable_bonds=max_rotatable_bonds,
        min_hbd=min_hbd, max_hbd=max_hbd,
        min_hba=min_hba, max_hba=max_hba,
        min_heavy_atoms=min_heavy_atoms, max_heavy_atoms=max_heavy_atoms,
        lipinski_pass=lipinski_pass, sdf_filename=sdf_filename,
    )

    def _hist(col, bins, exclude_key):
        f = {**filters}
        f.pop(f"min_{exclude_key}", None)
        f.pop(f"max_{exclude_key}", None)
        q = _apply_filters(db.query(SDFMolecule), **f)
        buckets = []
        for i, lo in enumerate(bins):
            hi = bins[i + 1] if i + 1 < len(bins) else None
            cond = col >= lo
            if hi is not None:
                cond = and_(col >= lo, col < hi)
            buckets.append({"min": lo, "max": hi, "count": q.filter(cond).count()})
        return buckets

    return {
        "molecular_weight": _hist(SDFMolecule.molecular_weight, [0, 100, 200, 300, 400, 500, 600, 800, 1000], "mw"),
        "logp": _hist(SDFMolecule.logp, [-10, -2, 0, 1, 2, 3, 4, 5, 8, 15], "logp"),
        "qed": _hist(SDFMolecule.qed, [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0], "qed"),
        "sa_score": _hist(SDFMolecule.sa_score, [1, 1.5, 2, 2.5, 3, 3.5, 4, 5, 6, 8, 10], "sa_score"),
        "tpsa": _hist(SDFMolecule.tpsa, [0, 20, 40, 60, 80, 100, 120, 140, 180, 250], "tpsa"),
        "rotatable_bonds": _hist(SDFMolecule.num_rotatable_bonds, [0, 1, 3, 5, 7, 10, 15, 20, 30], "rotatable_bonds"),
        "hbd": _hist(SDFMolecule.num_h_bond_donors, [0, 1, 2, 3, 5, 8, 12, 20], "hbd"),
        "hba": _hist(SDFMolecule.num_h_bond_acceptors, [0, 2, 4, 6, 8, 10, 12, 15, 20, 30], "hba"),
        "heavy_atoms": _hist(SDFMolecule.num_heavy_atoms, [0, 10, 20, 30, 40, 50, 60, 80, 100], "heavy_atoms"),
    }


@router.delete("/molecules/{molecule_id}")
async def delete_molecule(molecule_id: str, db: Session = Depends(get_db)):
    mol = db.query(SDFMolecule).filter(SDFMolecule.id == molecule_id).first()
    if not mol:
        raise MoleculeLibraryError(reason=f"分子不存在：{molecule_id}")
    db.delete(mol)
    db.commit()
    return {"status": "deleted", "molecule_id": molecule_id, "message": "分子记录已删除（SDF 源文件未受影响）"}


@router.get("/molecules/{molecule_id}/svg")
async def molecule_svg(molecule_id: str, db: Session = Depends(get_db)):
    from fastapi.responses import Response
    mol = db.query(SDFMolecule).filter(SDFMolecule.id == molecule_id).first()
    if not mol:
        raise MoleculeLibraryError(reason=f"分子不存在：{molecule_id}")
    smiles = mol.smiles
    if not smiles:
        return Response(
            '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="220">'
            '<text x="50%" y="50%" text-anchor="middle" fill="#999">No SMILES</text></svg>',
            media_type="image/svg+xml",
        )
    if not _HAS_RDKIT:
        return Response(
            '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="220">'
            '<text x="50%" y="50%" text-anchor="middle" fill="#999">RDKit not available</text></svg>',
            media_type="image/svg+xml",
        )
    try:
        m = Chem.MolFromSmiles(smiles)
        if m is None:
            raise ValueError("RDKit failed to parse SMILES")
        drawer = rdMolDraw2D.MolDraw2DSVG(320, 220)
        drawer.DrawMolecule(m)
        drawer.FinishDrawing()
        svg = drawer.GetDrawingText()
        return Response(svg, media_type="image/svg+xml")
    except Exception as e:
        return Response(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="320" height="220">'
            f'<text x="50%" y="50%" text-anchor="middle" fill="#c33">{e}</text></svg>',
            media_type="image/svg+xml",
        )
