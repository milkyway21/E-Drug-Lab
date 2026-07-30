"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, ArrowDown, ArrowUp, CheckCircle2, ChevronLeft, ChevronRight,
  Database, FileCode, RefreshCw, Search, X, Beaker, SlidersHorizontal
} from "lucide-react";
import { useLang } from "@/lib/i18n/i18n-context";
import { apiClient, MoleculeDBStats, MoleculeDistributions, MoleculeFilterParams, SDFMolecule, SyncResultResponse } from "@/lib/api-client";
import { MoleculeStructure } from "@/components/MoleculeStructure";

const PAGE_SIZE = 50;

const SORT_FIELDS = [
  { key: "name", label: "Name" }, { key: "molecular_weight", label: "MW" },
  { key: "logp", label: "LogP" }, { key: "qed", label: "QED" },
  { key: "sa_score", label: "SA" },
  { key: "num_heavy_atoms", label: "Heavy" }, { key: "num_rotatable_bonds", label: "Rot" },
  { key: "num_h_bond_donors", label: "HBD" }, { key: "num_h_bond_acceptors", label: "HBA" },
  { key: "tpsa", label: "TPSA" }, { key: "molecular_formula", label: "Formula" },
  { key: "created_at", label: "Added" }
];

// ── Filter dropdown definitions ────────────────────────────────
// Each defines a <select> with distribution-category options.
// Index 0 = "All" (no filter). Selecting a category applies min/max.

interface FilterOption { label: string; min?: number; max?: number; }
interface FilterDropdown {
  key: string;
  label: string;
  dbMin: string;
  dbMax: string;
  options: FilterOption[];
}

const FILTER_DROPDOWNS: FilterDropdown[] = [
  {
    key: "mw", label: "MW", dbMin: "min_mw", dbMax: "max_mw",
    options: [
      { label: "MW: All" },
      { label: "< 200", max: 200 },
      { label: "200–400", min: 200, max: 400 },
      { label: "400–600", min: 400, max: 600 },
      { label: "> 600", min: 600 },
    ],
  },
  {
    key: "logp", label: "LogP", dbMin: "min_logp", dbMax: "max_logp",
    options: [
      { label: "LogP: All" },
      { label: "< 0", max: 0 },
      { label: "0–3", min: 0, max: 3 },
      { label: "3–5", min: 3, max: 5 },
      { label: "> 5", min: 5 },
    ],
  },
  {
    key: "qed", label: "QED", dbMin: "min_qed", dbMax: "max_qed",
    options: [
      { label: "QED: All" },
      { label: "< 0.3", max: 0.3 },
      { label: "0.3–0.5", min: 0.3, max: 0.5 },
      { label: "0.5–0.7", min: 0.5, max: 0.7 },
      { label: "0.7–0.9", min: 0.7, max: 0.9 },
      { label: "≥ 0.9", min: 0.9 },
    ],
  },
  {
    key: "sa_score", label: "SA", dbMin: "min_sa_score", dbMax: "max_sa_score",
    options: [
      { label: "SA: All" },
      { label: "< 2.0", max: 2 },
      { label: "2.0–3.0", min: 2, max: 3 },
      { label: "3.0–4.0", min: 3, max: 4 },
      { label: "4.0–5.0", min: 4, max: 5 },
      { label: "> 5.0", min: 5 },
    ],
  },
  {
    key: "tpsa", label: "TPSA", dbMin: "min_tpsa", dbMax: "max_tpsa",
    options: [
      { label: "TPSA: All" },
      { label: "< 40 Å²", max: 40 },
      { label: "40–80 Å²", min: 40, max: 80 },
      { label: "80–140 Å²", min: 80, max: 140 },
      { label: "> 140 Å²", min: 140 },
    ],
  },
  {
    key: "rotatable_bonds", label: "Rot", dbMin: "min_rotatable_bonds", dbMax: "max_rotatable_bonds",
    options: [
      { label: "Rot: All" },
      { label: "0", min: 0, max: 0 },
      { label: "1–5", min: 1, max: 5 },
      { label: "6–10", min: 6, max: 10 },
      { label: "> 10", min: 11 },
    ],
  },
  {
    key: "hbd", label: "HBD", dbMin: "min_hbd", dbMax: "max_hbd",
    options: [
      { label: "HBD: All" },
      { label: "0", min: 0, max: 0 },
      { label: "1–3", min: 1, max: 3 },
      { label: "4–5", min: 4, max: 5 },
      { label: "> 5", min: 6 },
    ],
  },
  {
    key: "hba", label: "HBA", dbMin: "min_hba", dbMax: "max_hba",
    options: [
      { label: "HBA: All" },
      { label: "0–2", min: 0, max: 2 },
      { label: "3–5", min: 3, max: 5 },
      { label: "6–10", min: 6, max: 10 },
      { label: "> 10", min: 11 },
    ],
  },
  {
    key: "heavy_atoms", label: "Heavy", dbMin: "min_heavy_atoms", dbMax: "max_heavy_atoms",
    options: [
      { label: "Heavy: All" },
      { label: "< 20", max: 20 },
      { label: "20–40", min: 20, max: 40 },
      { label: "40–70", min: 40, max: 70 },
      { label: "> 70", min: 71 },
    ],
  },
  {
    key: "lipinski", label: "Lipinski", dbMin: "", dbMax: "",
    options: [
      { label: "Lipinski: All" },
      { label: "Pass", min: 1 },   // lipinski_pass = true
      { label: "Fail", min: 2 },   // lipinski_pass = false
    ],
  },
];

// ── Page component ─────────────────────────────────────────────
export default function DatabasePage() {
  const { t } = useLang();

  // Data
  const [molecules, setMolecules] = useState<SDFMolecule[]>([]);
  const [selected, setSelected] = useState<SDFMolecule | null>(null);
  const [stats, setStats] = useState<MoleculeDBStats | null>(null);
  const [distributions, setDistributions] = useState<MoleculeDistributions | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<SyncResultResponse | null>(null);

  // List params
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("molecular_weight");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);

  // Filter state: key → selected option index (0 = All)
  const [filterIdxs, setFilterIdxs] = useState<Record<string, number>>({});

  // Sync trigger
  const [syncTrigger, setSyncTrigger] = useState(0);
  const filterDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Derived filter params ────────────────────────────────────
  const activeFilterParams = useMemo((): MoleculeFilterParams => {
    const p: MoleculeFilterParams = {};
    if (search) p.search = search;

    for (const dd of FILTER_DROPDOWNS) {
      const idx = filterIdxs[dd.key];
      if (!idx || idx === 0) continue; // 0 = All

      if (dd.key === "lipinski") {
        if (idx === 1) p.lipinski_pass = true;
        else if (idx === 2) p.lipinski_pass = false;
        continue;
      }

      const opt = dd.options[idx];
      if (!opt) continue;
      if (opt.min !== undefined) (p as any)[dd.dbMin] = opt.min;
      if (opt.max !== undefined) (p as any)[dd.dbMax] = opt.max;
    }
    return p;
  }, [filterIdxs, search]);

  const activeFilterCount = useMemo(() => {
    let c = 0;
    for (const dd of FILTER_DROPDOWNS) {
      if ((filterIdxs[dd.key] ?? 0) > 0) c++;
    }
    return c;
  }, [filterIdxs]);

  // ── Data loading ─────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;

    async function fetchAll() {
      setLoading(true);
      setError(null);
      const params: Record<string, string | number | boolean | undefined> = {
        page, page_size: PAGE_SIZE, sort_by: sortBy, sort_order: sortOrder,
      };
      for (const [k, v] of Object.entries(activeFilterParams)) {
        if (v !== undefined) params[k] = v;
      }
      const [molR, statsR, distR] = await Promise.all([
        apiClient.listMolecules(params),
        apiClient.moleculeStats(activeFilterParams),
        apiClient.moleculeDistributions(activeFilterParams),
      ]);
      if (cancelled) return;
      if (molR.ok) {
        setMolecules(molR.data.molecules);
        setTotal(molR.data.pagination.total);
        setTotalPages(molR.data.pagination.total_pages);
      } else { setError(molR.error); }
      if (statsR.ok) setStats(statsR.data);
      if (distR.ok) setDistributions(distR.data);
      setLoading(false);
    }

    fetchAll();
    return () => { cancelled = true; };
  }, [page, sortBy, sortOrder, activeFilterParams, syncTrigger]);

  // Debounce: reset to page 1 on filter change
  useEffect(() => {
    if (filterDebounce.current) clearTimeout(filterDebounce.current);
    filterDebounce.current = setTimeout(() => {
      if (page !== 1) setPage(1);
    }, 200);
    return () => { if (filterDebounce.current) clearTimeout(filterDebounce.current); };
  }, [activeFilterParams]);

  // Init filter state
  useEffect(() => {
    const init: Record<string, number> = {};
    for (const dd of FILTER_DROPDOWNS) init[dd.key] = 0;
    setFilterIdxs(init);
  }, []);

  // ── Sync ─────────────────────────────────────────────────────
  async function sync() {
    setSyncing(true);
    setSyncResult(null);
    const r = await apiClient.syncMolecules();
    setSyncResult(r.ok ? r.data : null);
    if (!r.ok) setError(r.error);
    setSyncing(false);
    setSyncTrigger(s => s + 1);
  }

  // ── Helpers ──────────────────────────────────────────────────
  function handleSort(key: string) {
    if (sortBy === key) setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    else { setSortBy(key); setSortOrder("asc"); }
    setPage(1);
  }

  function clearAllFilters() {
    const reset: Record<string, number> = {};
    for (const dd of FILTER_DROPDOWNS) reset[dd.key] = 0;
    setFilterIdxs(reset);
    setSearch("");
  }

  function fmt(val: number | null | undefined, digits = 2) {
    return val != null ? val.toFixed(digits) : "—";
  }

  function qedBadge(val: number | null) {
    if (val == null) return <span className="text-slate-400">—</span>;
    const cls = val >= 0.7 ? "bg-green-50 text-green-700 border border-green-100" :
                val >= 0.4 ? "bg-amber-50 text-amber-700 border border-amber-100" :
                "bg-red-50 text-red-700 border border-red-100";
    return <span className={`inline-flex rounded px-2 py-0.5 text-xs font-mono font-semibold ${cls}`}>{val.toFixed(3)}</span>;
  }

  function saBadge(val: number | null) {
    if (val == null) return <span className="text-slate-400">—</span>;
    const cls = val <= 3 ? "bg-green-50 text-green-700 border border-green-100" :
                val <= 4 ? "bg-amber-50 text-amber-700 border border-amber-100" :
                "bg-red-50 text-red-700 border border-red-100";
    return <span className={`inline-flex rounded px-2 py-0.5 text-xs font-mono font-semibold ${cls}`}>{val.toFixed(2)}</span>;
  }

  // ── Render ───────────────────────────────────────────────────
  return (
    <section className="mx-auto max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="stat-label mb-2 flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-primary" />
            {t("molDbLabel")}
          </div>
          <h1 className="font-display text-3xl font-bold text-ink tracking-tight">{t("molTitle")}</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">
            {t("molDesc")}
            {stats && <span className="ml-2 text-slate-400">· {stats.total_molecules} {t("molTotalMols")} · {stats.total_sdf_files} SDF</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {activeFilterCount > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-primary-50 px-3 py-1.5 text-xs font-semibold text-primary">
              <SlidersHorizontal size={14} />
              {activeFilterCount} active
            </span>
          )}
          <button onClick={sync} disabled={syncing} className="btn-primary">
            <RefreshCw size={16} className={syncing ? "animate-spin" : ""} />
            {syncing ? t("molSyncing") : t("molSync")}
          </button>
        </div>
      </div>

      {/* Stats bar — updates reactively when filters change */}
      {stats && (
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-8">
          <div className="panel p-3">
            <div className="stat-label">{stats.filtered ? "Filtered" : t("molTotalMols")}</div>
            <div className="mt-1 font-display text-lg font-bold text-ink">{stats.total_molecules}</div>
          </div>
          <div className="panel p-3">
            <div className="stat-label">{t("molAvgMW")}</div>
            <div className="mt-1 font-display text-base font-bold text-ink">{fmt(stats.statistics.molecular_weight.avg)}</div>
            <div className="mt-0.5 text-[10px] text-slate-400">{fmt(stats.statistics.molecular_weight.min,0)}–{fmt(stats.statistics.molecular_weight.max,0)}</div>
          </div>
          <div className="panel p-3">
            <div className="stat-label">{t("molAvgLogP")}</div>
            <div className="mt-1 font-display text-base font-bold text-ink">{fmt(stats.statistics.logp_avg, 2)}</div>
          </div>
          <div className="panel p-3">
            <div className="stat-label">{t("molAvgQED")}</div>
            <div className="mt-1 font-display text-base font-bold text-ink">{fmt(stats.statistics.qed_avg, 3)}</div>
          </div>
          <div className="panel p-3">
            <div className="stat-label">Avg SA</div>
            <div className="mt-1 font-display text-base font-bold text-ink">{fmt(stats.statistics.sa_score_avg, 2)}</div>
          </div>
          <div className="panel p-3">
            <div className="stat-label">{t("molAvgTPSA")}</div>
            <div className="mt-1 font-display text-base font-bold text-ink">{fmt(stats.statistics.tpsa_avg, 1)}</div>
          </div>
          <div className="panel p-3">
            <div className="stat-label">Avg HBD</div>
            <div className="mt-1 font-display text-base font-bold text-ink">{fmt(stats.statistics.hbd_avg, 1)}</div>
          </div>
          <div className="panel p-3">
            <div className="stat-label">Avg HBA</div>
            <div className="mt-1 font-display text-base font-bold text-ink">{fmt(stats.statistics.hba_avg, 1)}</div>
          </div>
        </div>
      )}

      {/* Lipinski summary */}
      {stats?.statistics.lipinski && (
        <div className="mb-4 flex items-center gap-3 text-xs text-muted">
          <span className="font-semibold">Lipinski:</span>
          <span className="inline-flex items-center gap-1 rounded-full bg-green-50 px-2.5 py-0.5 font-mono font-semibold text-green-700">
            {stats.statistics.lipinski.pass_count} pass
          </span>
          <span className="text-slate-400">/ {stats.statistics.lipinski.total_evaluated}</span>
          <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-0.5 font-mono font-semibold text-red-700">
            {stats.statistics.lipinski.fail_count} fail
          </span>
        </div>
      )}

      {/* Sync result */}
      {syncResult && (
        <div className="mb-4 rounded-lg p-4 text-sm" style={{
          border: `1px solid ${syncResult.sync_result.errors.length ? '#ffe0b2' : '#c8e6c9'}`,
          background: syncResult.sync_result.errors.length ? '#fff8e1' : '#f1f8e9',
        }}>
          <div className="mb-2 flex items-center gap-2 font-semibold text-ink">
            {syncResult.sync_result.errors.length ? <AlertTriangle size={16} className="text-amber-600" /> : <CheckCircle2 size={16} className="text-green-600" />}
            {t("molSyncDone")}: {syncResult.sync_result.total_files} {t("molSyncFiles")}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
            <span>{t("molSyncNew")} {syncResult.sync_result.new_files}</span>
            <span>{t("molSyncUpdated")} {syncResult.sync_result.updated_files}</span>
            <span>{t("molSyncUnchanged")} {syncResult.sync_result.unchanged_files}</span>
            <span>+{syncResult.sync_result.total_conformers_added} conformers</span>
            {syncResult.sync_result.deleted_records > 0 && <span className="text-red-600">-{syncResult.sync_result.deleted_records} records</span>}
          </div>
          {syncResult.sync_result.errors.length > 0 && (
            <div className="mt-2 text-xs text-red-600">
              {syncResult.sync_result.errors.map((e, i) => <div key={i}>{e.file}: {e.error}</div>)}
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mb-4 flex items-center gap-2 rounded-lg p-4 text-sm text-red-700 bg-red-50 border border-red-100">
          <AlertTriangle size={16} />
          <span className="flex-1">{error}</span>
          <button onClick={() => setError(null)}><X size={16} /></button>
        </div>
      )}

      {/* Toolbar: search + filter dropdowns + clear */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[180px] max-w-xs">
          <Search size={16} className="pointer-events-none absolute left-3 top-3 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("molSearch")}
            className="input-field pl-9 pr-9"
          />
          {search && (
            <button onClick={() => setSearch("")} className="absolute right-3 top-3">
              <X size={14} className="text-slate-400 hover:text-ink" />
            </button>
          )}
        </div>

        {FILTER_DROPDOWNS.map((dd) => (
          <select
            key={dd.key}
            value={filterIdxs[dd.key] ?? 0}
            onChange={(e) => setFilterIdxs(prev => ({ ...prev, [dd.key]: Number(e.target.value) }))}
            className={`select-field h-9 w-auto min-w-[100px] text-xs ${
              (filterIdxs[dd.key] ?? 0) > 0
                ? "border-primary bg-primary-50 text-primary font-semibold"
                : ""
            }`}
          >
            {dd.options.map((opt, i) => (
              <option key={i} value={i}>{opt.label}</option>
            ))}
          </select>
        ))}

        {activeFilterCount > 0 && (
          <button
            onClick={clearAllFilters}
            className="inline-flex h-9 items-center gap-1 rounded-lg border border-red-200 px-2.5 text-xs font-semibold text-red-600 hover:bg-red-50 transition-all"
          >
            <X size={14} /> Clear
          </button>
        )}

        <span className="ml-auto text-xs text-muted whitespace-nowrap">{total} results</span>
      </div>

      {/* ── Molecule table ────────────────────────────────────── */}
      <div className="panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="bg-slate-50">
                <th className="px-3 py-3 text-xs font-semibold text-muted w-10">#</th>
                {SORT_FIELDS.map((f) => (
                  <th key={f.key} onClick={() => handleSort(f.key)}
                    className="cursor-pointer px-3 py-3 text-xs font-semibold text-muted hover:text-ink whitespace-nowrap transition-colors">
                    <span className="inline-flex items-center gap-1">
                      {f.label}
                      {sortBy === f.key && (sortOrder === "asc" ? <ArrowUp size={12} className="text-primary" /> : <ArrowDown size={12} className="text-primary" />)}
                    </span>
                  </th>
                ))}
                <th className="px-3 py-3 text-xs font-semibold text-muted whitespace-nowrap">{t("molSdfFile")}</th>
                <th className="px-3 py-3 text-xs font-semibold text-muted whitespace-nowrap">{t("molSdfPath")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr><td colSpan={SORT_FIELDS.length + 3} className="px-4 py-20 text-center">
                  <Beaker size={40} className="mx-auto mb-3 text-slate-200 animate-pulse" />
                  <p className="text-muted">{t("molLoading")}</p>
                </td></tr>
              ) : molecules.length === 0 ? (
                <tr><td colSpan={SORT_FIELDS.length + 3} className="px-4 py-20 text-center">
                  <FileCode size={40} className="mx-auto mb-3 text-slate-200" />
                  <p className="mb-1 text-muted">{t("molNoData")}</p>
                  <p className="text-xs text-slate-400">{t("molNoDataHint")}</p>
                </td></tr>
              ) : molecules.map((m, i) => (
                <tr key={m.id} onClick={() => setSelected(m)}
                  className={`cursor-pointer transition-colors hover:bg-primary-50/30 ${selected?.id === m.id ? "bg-primary-50/50" : ""}`}>
                  <td className="px-3 py-3 text-xs text-slate-400">{(page-1)*PAGE_SIZE+i+1}</td>
                  <td className="px-3 py-3 font-semibold text-ink max-w-[160px] truncate" title={m.name || ""}>
                    {m.name || <span className="italic text-slate-400">{t("molUnnamed")}</span>}
                  </td>
                  <td className="px-3 py-3 font-mono text-xs text-primary">{fmt(m.molecular_weight)}</td>
                  <td className="px-3 py-3 font-mono text-xs text-muted">{fmt(m.logp, 2)}</td>
                  <td className="px-3 py-3">{qedBadge(m.qed)}</td>
                  <td className="px-3 py-3">{saBadge(m.sa_score)}</td>
                  <td className="px-3 py-3 text-xs text-muted">{m.num_heavy_atoms ?? "—"}</td>
                  <td className="px-3 py-3 text-xs text-muted">{m.num_rotatable_bonds ?? "—"}</td>
                  <td className="px-3 py-3 text-xs text-muted">{m.num_h_bond_donors ?? "—"}</td>
                  <td className="px-3 py-3 text-xs text-muted">{m.num_h_bond_acceptors ?? "—"}</td>
                  <td className="px-3 py-3 text-xs text-muted">{fmt(m.tpsa, 1)}</td>
                  <td className="px-3 py-3 font-mono text-xs text-muted max-w-[120px] truncate" title={m.molecular_formula || ""}>{m.molecular_formula || "—"}</td>
                  <td className="px-3 py-3 text-xs text-slate-400">{m.created_at ? new Date(m.created_at).toLocaleDateString() : "—"}</td>
                  <td className="px-3 py-3">
                    <span className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-mono bg-primary-50 text-primary border border-primary-100">
                      <FileCode size={12} />{m.sdf_filename}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-xs text-slate-400 font-mono max-w-[200px] truncate" title={m.sdf_file_path}>{m.sdf_file_path}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100">
            <span className="text-xs text-muted">{t("commonPage")}{page}{t("commonOf")}{totalPages} · {total}{t("commonRecords")}</span>
            <div className="flex items-center gap-2">
              <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1}
                className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 px-2 text-xs text-muted hover:border-primary/30 hover:text-ink disabled:opacity-30 transition-all">
                <ChevronLeft size={14} />{t("commonPrev")}
              </button>
              {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                const start = Math.max(1, Math.min(page - 2, totalPages - 4));
                const p = start + i;
                if (p > totalPages) return null;
                return (
                  <button key={p} onClick={() => setPage(p)}
                    className={`h-8 w-8 rounded-lg text-xs font-semibold transition-all ${page === p ? "bg-primary text-white" : "border border-slate-200 text-muted hover:border-primary/30 hover:text-ink"}`}>{p}</button>
                );
              })}
              <button onClick={() => setPage(Math.min(totalPages, page + 1))} disabled={page === totalPages}
                className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 px-2 text-xs text-muted hover:border-primary/30 hover:text-ink disabled:opacity-30 transition-all">
                {t("commonNext")}<ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── Detail panel ──────────────────────────────────────── */}
      {selected && (
        <div className="panel mt-6 p-6 animate-slide-up">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 font-display text-lg font-bold text-ink">
              <Database size={20} className="text-primary" />
              {selected.name || t("molDetail")}
            </h2>
            <button onClick={() => setSelected(null)} className="rounded-lg p-1 text-muted hover:text-ink transition-colors hover:bg-slate-50"><X size={20} /></button>
          </div>

          <div className="grid gap-6 md:grid-cols-[340px_1fr]">
            <div>
              <div className="stat-label mb-2">2D</div>
              <MoleculeStructure moleculeId={selected.id} width={320} height={220} />
              {selected.smiles && (
                <div className="mt-2 break-all rounded-lg px-3 py-2 font-mono text-[10px] leading-4 text-muted select-all bg-slate-50 border border-slate-100">
                  {selected.smiles}
                </div>
              )}
            </div>
            <div className="grid grid-cols-2 gap-x-6 gap-y-3 md:grid-cols-4">
              {[
                [t("molFieldName"), selected.name],
                [t("molFieldFormula"), selected.molecular_formula],
                [t("molFieldWeight"), selected.molecular_weight != null ? `${selected.molecular_weight.toFixed(4)} g/mol` : null],
                ["LogP", fmt(selected.logp, 2)],
                ["TPSA", selected.tpsa != null ? `${selected.tpsa.toFixed(2)} Å²` : null],
                ["QED", fmt(selected.qed, 4)],
                ["SA Score", fmt(selected.sa_score, 2)],
                [t("molFieldHeavyAtoms"), selected.num_heavy_atoms],
                [t("molFieldRotBonds"), selected.num_rotatable_bonds],
                [t("molFieldHDonors"), selected.num_h_bond_donors],
                [t("molFieldHAcceptors"), selected.num_h_bond_acceptors],
                ["InChI Key", selected.inchikey],
                [t("molFieldConformers"), `${(selected.conformer_index||0)+1} / ${selected.total_conformers||1}`],
              ].map(([label, val]) => (
                <div key={label as string} className="rounded-lg p-2 bg-slate-50">
                  <div className="text-xs text-slate-400">{label as string}</div>
                  <div className="mt-0.5 truncate text-sm font-semibold text-ink font-mono" title={String(val ?? "")}>{val ?? "—"}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-4 pt-4 border-t border-slate-100">
            <div className="stat-label mb-2">{t("molSdfPath")}</div>
            <code className="block break-all rounded-lg px-4 py-3 font-mono text-xs text-muted select-all bg-slate-50 border border-slate-100">{selected.sdf_file_path}</code>
          </div>

          {selected.sdf_properties && (() => {
            const props = Object.entries(selected.sdf_properties);
            const meaningful = props.filter(([k]) => isNaN(Number(k)));
            const bitCount = props.length - meaningful.length;
            if (props.length === 0) return null;
            return (
              <div className="mt-4 pt-4 border-t border-slate-100">
                <div className="stat-label mb-2">{t("molSdfProps")}{bitCount > 0 && <span className="ml-2 text-slate-400">(+ {bitCount} fingerprint bits)</span>}</div>
                {meaningful.length > 0 ? (
                  <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                    {meaningful.map(([k, v]) => (
                      <div key={k} className="surface px-3 py-2 rounded-lg">
                        <div className="text-xs text-slate-400">{k}</div>
                        <div className="mt-0.5 truncate text-sm font-mono text-ink">{String(v)}</div>
                      </div>
                    ))}
                  </div>
                ) : <p className="text-xs text-slate-400">All {bitCount} columns are fingerprint bits (0/1).</p>}
              </div>
            );
          })()}
        </div>
      )}
    </section>
  );
}
