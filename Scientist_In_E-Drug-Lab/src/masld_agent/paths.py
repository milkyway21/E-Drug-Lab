"""Safe path helpers — prevent traversal outside project roots."""
from __future__ import annotations

from pathlib import Path


class UnsafePathError(ValueError):
    pass


def resolve_under(root: Path, user_path: str | Path | None, *, default: Path) -> Path:
    """Resolve user_path under root; reject .. escape. Empty/None → default (also under root)."""
    root = root.resolve()
    if user_path is None or str(user_path).strip() == "":
        candidate = default.resolve()
    else:
        p = Path(user_path)
        candidate = (p if p.is_absolute() else (root / p)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise UnsafePathError(
            f"path escapes allowed root: {candidate} not under {root}"
        ) from exc
    return candidate


def resolve_under_any(
    roots: list[Path],
    user_path: str | Path | None,
    *,
    default: Path,
) -> Path:
    """Allow path under any of the given roots (e.g. PKG_ROOT or /tmp/runs)."""
    last: Exception | None = None
    for root in roots:
        try:
            return resolve_under(root, user_path, default=default)
        except UnsafePathError as exc:
            last = exc
    assert last is not None
    raise last
