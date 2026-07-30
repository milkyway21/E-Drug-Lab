# Code Review — Working Tree Diff (2026-06-06)

Scope: all uncommitted changes across backend + frontend (package-lock.json excluded from findings).

---

## Findings (severity: 🔴 high → 🟡 medium → 🔵 low)

---

### 1. 🔴 Event-loop blocking: synchronous `urlopen()` in async endpoints

**Files:** `backend/app/api/routes/drugclip.py:84,114`, `backend/app/api/routes/targets.py:100-115`

**Problem:** Both the DrugCLIP `/screen` endpoint (timeout default 600s) and the target `/download` endpoint (timeout 30s) call `urllib.request.urlopen()` inside `async def` handlers. This **freezes the entire asyncio event loop** — no other request can be served until the blocking call returns.

**Failure scenario:** A DrugCLIP screening takes 2 minutes → all other endpoints (health, molecule queries, library CRUD) are completely unresponsive for 2 minutes. With the 600s timeout, the server is effectively down.

**Fix:** Replace with one of:
- `httpx.AsyncClient` (preferred — already used elsewhere in the codebase)
- `asyncio.to_thread(urlopen, url, timeout=timeout)` as a minimal patch
- For the PDB download, also consider streaming the response to avoid loading the whole file into memory.

---

### 2. 🔴 Stale docstring hides 10x penalty miscalculation

**File:** `backend/app/services/orthogonal_scoring.py:12`

**Problem:** The docstring says *"A gap of 10 points above threshold yields a 6.5-point penalty"* — this describes the **old** linear formula `max(0, gap-35) * 0.65`. The **new** formula is quadratic: `max(0, gap-35)² * 0.65 / 100.0`. At gap=10 the actual penalty is **0.65**, not 6.5 (off by 10×).

Additionally, the `artifact_flag` branch (line 140) applies a **second, undocumented** penalty: `final_score *= 0.3` (70% reduction). This compounds with the quadratic penalty in a way that makes the quadratic effectively dead code for the cases it targets:

| gap | orthogonal_desirability | quadratic penalty | after artifact slash |
|-----|------------------------|-------------------|---------------------|
| 36  | 50                     | 0.0065            | 15.0                |
| 45  | 50                     | 0.65              | 14.8                |
| 60  | 50                     | 0.41              | 14.9                |

The artifact `*0.3` dominates so completely that gap=36 and gap=60 produce nearly identical scores.

**Fix:**
1. Update the docstring to match the new formula.
2. Add unit tests covering edge cases (gap just above threshold, moderate gap, large gap).
3. Decide whether the two-penalty interaction is intentional — if so, document it; if not, simplify.

---

### 3. 🔴 Broken `get_db` error contract

**File:** `backend/app/db.py:26` (new file)

**Problem:** Old per-route helpers raised a structured `AppError(message="数据库未连接", code="DATABASE_NOT_CONNECTED", status_code=503)`. The new centralized `get_db` raises a bare `RuntimeError("数据库引擎未初始化")`, which the generic handler renders as an **unstructured HTTP 500**. Frontend code checking for `code == "DATABASE_NOT_CONNECTED"` or expecting 503 will break.

**Fix:** In `get_db()`, raise `AppError(message="数据库引擎未初始化", code="DATABASE_NOT_CONNECTED", status_code=503)` instead of `RuntimeError`.

---

### 4. 🟡 Silently dropped auth model for DrugCLIP

**File:** `backend/app/config.py:29`

**Problem:** Old `DrugClipSettings` had `api_key: str` (required) and `base_url: str`. New version replaces them with `service_url`, `timeout`, `image_name`, `wsl_exe`, etc. Any existing `.env` with `DRUGCLIP__API_KEY` is silently ignored due to `extra = "ignore"`. The entire auth model was dropped without migration or warning.

**Fix:** Either:
- Keep `api_key` as an optional field and pass it as a header in `DrugClipClient.screen()` / `health()`.
- Or log a deprecation warning when `DRUGCLIP__API_KEY` is detected in the environment.

---

### 5. 🟡 `request_id` removed from all response bodies

**Files:** `backend/app/api/routes/molecule_db.py:47,75,96,118,144,166`, `targets.py`, `libraries.py`

**Problem:** All `request_id` fields removed from JSON responses. The middleware still sets `X-Request-ID` header, but frontend code parsing `response.request_id` from the body will get `undefined`.

**Fix:** Audit `frontend/src/lib/api-client.ts` and all page components that read `request_id` from response JSON. Either remove those references or keep the field for backward compat.

---

### 6. 🟡 `SDF_DIRECTORY` config fallback removed

**File:** `backend/app/api/routes/molecule_db.py:115`

**Problem:** `trigger_sync` no longer falls back to `settings.sdf_directory`. Any deployment using the `SDF_DIRECTORY` env var will silently lose that configuration and fall through to a hardcoded project-relative path.

**Fix:** Restore the `settings.sdf_directory` fallback:
```python
if body.sdf_directory:
    sdf_dir = os.path.abspath(body.sdf_directory)
elif settings and hasattr(settings, 'sdf_directory') and settings.sdf_directory:
    sdf_dir = os.path.abspath(settings.sdf_directory)
else:
    ...
```

---

### 7. 🟡 Redundant DB queries in `sdf_sync.py`

**File:** `backend/app/services/sdf_sync.py:30-41`

**Problem:** `_get_existing_hashes()` and `_get_existing_paths()` issue **two separate SELECT DISTINCT** queries against the same table. The paths query already returns `(path, hash)` pairs, so the hash set can be derived from its values.

**Fix:** Merge into one function:
```python
def _get_existing_state(db: Session) -> tuple[dict[str, str], set[str]]:
    rows = db.execute(select(SDFMolecule.sdf_file_path, SDFMolecule.sdf_file_hash).distinct()).all()
    paths = {r[0]: r[1] for r in rows}
    return paths, set(paths.values())
```

---

### 8. 🟡 Orphan cleanup issues N separate DELETEs

**File:** `backend/app/services/sdf_sync.py:143-150`

**Problem:** Each orphan hash triggers an individual `DELETE ... WHERE hash = ?` + a separate commit. For 500 orphan groups that's 500 round-trips.

**Fix:** Batch into a single statement:
```python
if orphan_hashes:
    db.execute(delete(SDFMolecule).where(SDFMolecule.sdf_file_hash.in_(orphan_hashes)))
    db.commit()
```

---

### 9. 🟡 `combined_routes.py` is dead code

**File:** `backend/app/api/routes/combined_routes.py`

**Problem:** Now a 5-line re-export shim. But `main.py` already imports directly from `screening.py`, `admet.py`, etc. — it does **not** import from `combined_routes.py`. The file has zero consumers.

**Fix:** Delete `combined_routes.py`. If backward compat is needed for external importers, add a deprecation comment.

---

### 10. 🔵 Schrodinger client: 380 lines of pure stubs

**File:** `backend/app/api/integrations/schrodinger.py`

**Problem:** 8 dataclass definitions + 10 method bodies that all return hardcoded dummy instances and log "stub". Every real implementation is commented out behind TODO. The stubs create a false sense that the integration works — `wait_for_job` will poll forever then raise `TimeoutError` at 3600s.

**Fix:** Either:
- Reduce to a 30-line module with config + `raise NotImplementedError("Schrodinger integration pending API access")`.
- Or mark the entire module with a clear `STUB = True` flag that route handlers check before calling.

---

### 11. 🔵 Three duplicate `_serialize_*` functions

**Files:** `targets.py:44`, `libraries.py:40`, `molecule_db.py:26`

**Problem:** Nearly identical manual dict-mapping with `str(id)` and `.isoformat()`. A new column added to any model will be silently omitted from the API.

**Fix:** Create a shared utility:
```python
def model_to_dict(instance, exclude: list[str] = None) -> dict:
    exclude = set(exclude or [])
    return {
        c.name: str(getattr(instance, c.name)) if c.name == "id" else getattr(instance, c.name)
        for c in instance.__table__.columns
        if c.name not in exclude
    }
```

---

### 12. 🔵 Celery proxy is over-engineered

**File:** `backend/app/workers/celery_app.py:5`

**Problem:** 16-line proxy class vs a 5-line lazy-init function. The proxy's `__getattr__` silently swallows attribute errors and forwards them to the real Celery, making stack traces confusing.

**Fix:** Replace with:
```python
_celery_app: Celery | None = None

def get_celery_app() -> Celery:
    global _celery_app
    if _celery_app is None:
        from app.config import get_settings
        settings = get_settings()
        _celery_app = Celery("edrug_lab", broker=settings.celery.broker_url, ...)
        _celery_app.conf.update(...)
    return _celery_app
```

---

### 13. 🔵 `upload_library` reads entire file into memory

**File:** `backend/app/api/routes/libraries.py:94`

**Problem:** `content = await file.read()` buffers the whole upload (potentially 100MB+) into RAM before writing.

**Fix:** Stream to disk:
```python
with open(file_path, "wb") as f:
    async for chunk in file.iter(1024 * 1024):
        f.write(chunk)
```

---

### 14. 🔵 rdkit imported inside handler on every request

**File:** `backend/app/api/routes/molecule_db.py:160-178`

**Problem:** `from rdkit import Chem` inside the SVG handler body. If rdkit is absent, every request hits `ImportError` → caught by broad `except` → error SVG. 50 gallery images = 50 wasted import attempts.

**Fix:** Move import to module level with a lazy flag:
```python
try:
    from rdkit import Chem
    from rdkit.Chem.Draw import rdMolDraw2D
    _HAS_RDKIT = True
except ImportError:
    _HAS_RDKIT = False
```

---

## Summary

| Severity | Count | Theme |
|----------|-------|-------|
| 🔴 High  | 3     | Event-loop blocking, scoring formula bug, DB error contract |
| 🟡 Medium | 4    | Silent config drops, removed response fields, redundant I/O |
| 🔵 Low   | 7     | Dead code, duplication, over-engineering, memory |

**Top 3 to fix before merge:**
1. Wrap all `urlopen()` calls in `asyncio.to_thread()` or switch to `httpx` (crashes the server under load)
2. Update orthogonal_scoring docstring + add tests (misleads users by 10×)
3. Restore structured `AppError` in `get_db()` (breaks frontend error handling)
