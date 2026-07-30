"""Monorepo path helpers and lab-safe path validation."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from app.core.errors import AppError

_DATA_YE = Path("/data/ye")
_PDB_ID_RE = re.compile(r"^[a-z0-9]{4}$")


@lru_cache(maxsize=1)
def get_repo_root() -> Path:
    """Return e-drug-lab repository root (parent of backend/)."""
    return Path(__file__).resolve().parents[3]


def resolve_repo_path(path: str | Path) -> Path:
    """Resolve a path relative to repo root when not absolute."""
    p = Path(path)
    if p.is_absolute():
        return p.resolve()
    return (get_repo_root() / p).resolve()


@lru_cache(maxsize=1)
def get_allowed_roots() -> tuple[Path, ...]:
    """Directories that lab APIs may read/write under."""
    repo = get_repo_root()
    backend = repo / "backend"
    roots = {
        repo.resolve(),
        backend.resolve(),
        _DATA_YE.resolve(),
        Path("/tmp").resolve(),
    }
    for sub in ("data", "outputs", "molecules"):
        candidate = backend / sub
        if candidate.is_dir():
            roots.add(candidate.resolve())
    return tuple(sorted(roots, key=lambda p: len(str(p)), reverse=True))


def _is_under_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def is_safe_path(path: str | Path) -> bool:
    """Return True if resolved path is under an allowed lab root."""
    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, RuntimeError):
        return False
    return any(_is_under_root(resolved, root) for root in get_allowed_roots())


def ensure_safe_path(path: str | Path, *, must_exist: bool = False) -> Path:
    """Validate path is under allowed lab roots; raise AppError otherwise."""
    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise AppError(
            message=f"Invalid path: {path}",
            code="PATH_INVALID",
            status_code=400,
        ) from exc

    if not is_safe_path(resolved):
        raise AppError(
            message=f"Path not allowed (must be under project or /data/ye): {path}",
            code="PATH_NOT_ALLOWED",
            status_code=400,
        )
    if must_exist and not resolved.is_file() and not resolved.is_dir():
        raise AppError(
            message=f"Path does not exist: {resolved}",
            code="PATH_NOT_FOUND",
            status_code=404,
        )
    return resolved


def safe_upload_filename(filename: str | None, default: str = "upload") -> str:
    """Strip directory components from an upload filename."""
    name = Path(filename or default).name
    return name or default


def validate_pdb_id(pdb_id: str) -> str:
    """Normalize and validate a 4-character PDB ID."""
    normalized = pdb_id.lower().strip()
    if not _PDB_ID_RE.match(normalized):
        raise AppError(
            message=f"Invalid PDB ID (expected 4 alphanumeric chars): {pdb_id}",
            code="INVALID_PDB_ID",
            status_code=400,
        )
    return normalized
