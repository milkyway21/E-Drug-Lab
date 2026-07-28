"""RL round state management."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.repositories.models import RLRound, RLRoundArtifact


def rounds_base_dir() -> Path:
    base = Path(__file__).resolve().parents[2] / "outputs" / "rl_rounds"
    base.mkdir(parents=True, exist_ok=True)
    return base


def round_dir(round_id: int) -> Path:
    d = rounds_base_dir() / f"round_{round_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def step_log_path(round_id: int) -> Path:
    return round_dir(round_id) / f"round_{round_id}_step_log.json"


def write_step_log(round_id: int, step: str, status: str, **extra) -> None:
    path = step_log_path(round_id)
    log: dict[str, Any] = {}
    if path.exists():
        log = json.loads(path.read_text())
    log[step] = {"status": status, "timestamp": datetime.utcnow().isoformat(), **extra}
    path.write_text(json.dumps(log, indent=2, ensure_ascii=False))


def read_step_log(round_id: int) -> dict[str, Any]:
    path = step_log_path(round_id)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def serialize_round(row: RLRound) -> dict[str, Any]:
    return {
        "id": row.id,
        "round_id": row.round_id,
        "target_id": row.target_id,
        "status": row.status,
        "checkpoint_path": row.checkpoint_path,
        "wetlab_count": row.wetlab_count,
        "config_json": row.config_json or {},
        "step_log_json": row.step_log_json or read_step_log(row.round_id),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def create_round(db: Session, *, round_id: int, target_id: Optional[str] = None, config: Optional[dict] = None) -> RLRound:
    existing = db.query(RLRound).filter(RLRound.round_id == round_id).first()
    if existing:
        return existing
    row = RLRound(
        round_id=round_id,
        target_id=target_id,
        status="created",
        config_json=config or {},
        step_log_json={},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    round_dir(round_id)
    return row


def get_round(db: Session, round_id: int) -> Optional[RLRound]:
    return db.query(RLRound).filter(RLRound.round_id == round_id).first()


def list_rounds(db: Session, limit: int = 50) -> list[RLRound]:
    return db.query(RLRound).order_by(RLRound.round_id.desc()).limit(limit).all()


def update_round(db: Session, round_id: int, **fields) -> Optional[RLRound]:
    row = get_round(db, round_id)
    if not row:
        return None
    for k, v in fields.items():
        if hasattr(row, k):
            setattr(row, k, v)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def add_artifact(db: Session, round_id: int, step: str, artifact_type: str, path: str) -> RLRoundArtifact:
    art = RLRoundArtifact(round_id=round_id, step=step, artifact_type=artifact_type, path=path)
    db.add(art)
    db.commit()
    db.refresh(art)
    return art
