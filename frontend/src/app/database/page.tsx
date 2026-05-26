"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle, ArrowDown, ArrowUp, CheckCircle2, ChevronLeft, ChevronRight,
  Database, FileCode, RefreshCw, Search, X
} from "lucide-react";
import { useLang } from "@/lib/i18n/i18n-context";
import { apiClient, MoleculeDBStats, SDFMolecule, SyncResultResponse } from "@/lib/api-client";

const PAGE_SIZE = 50;

const MW_RANGES: Array<{ label: string; min?: number; max?: number }> = [
  { label: "All" }, { label: "< 200", max: 200 }, { label: "200-400", min: 200, max: 400 },
  { label: "400-600", min: 400, max: 600 }, { label: "> 600", min: 600 }
];

const LOGP_RANGES: Array<{ label: string; min?: number; max?: number }> = [
  { label: "All" }, { label: "< 0", max: 0 }, { label: "0-3", min: 0, max: 3 },
  { label: "3-5", min: 3, max: 5 }, { label: "> 5", min: 5 }
];

const SORT_FIELDS = [
  { key: "name", label: "Name" }, { key: "molecular_weight", label: "MW" },
  { key: "logp", label: "LogP" }, { key: "qed", label: "QED" },
  { key: "num_heavy_atoms", label: "Heavy" }, { key: "num_rotatable_bonds", label: "Rot" },
  { key: "tpsa", label: "TPSA" }, { key: "molecular_formula", label: "Formula" },
  { key: "created_at", label: "Added" }
];

export default function DatabasePage() {
  const { t } = useLang();
  // --- data ---
  const [molecules, setMolecules] = useState<SDFMolecule[]>([]);
  const [selected, setSelected] = useState<SDFMolecule | null>(null);
  const [stats, setStats] = useState<MoleculeDBStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // --- sync ---
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<SyncResultResponse | null>(null);

  // --- filters ---
  const [search, setSearch] = useState("");
  const [mwIdx, setMwIdx] = useState(0);
  const [logpIdx, setLogpIdx] = useState(0);
  const [minQed, setMinQed] = useState<string>("");

  // --- sort & page ---
  const [sortBy, setSortBy] = useState("molecular_weight");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);

  // ============ fetch ============

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const result = await apiClient.listMolecules({
      page, page_size: PAGE_SIZE, sort_by: sortBy, sort_order: sortOrder,
      search: search || undefined,
      min_mw: MW_RANGES[mwIdx].min, max_mw: MW_RANGES[mwIdx].max,
      min_logp: LOGP_RANGES[logpIdx].min, max_logp: LOGP_RANGES[logpIdx].max,
      min_qed: minQed ? Number(minQed) : undefined
    });
    if (result.ok) {
      setMolecules(result.data.molecules);
      setTotal(result.data.pagination.total);
      setTotalPages(result.data.pagination.total_pages);
    } else {
      setError(result.error);
    }
    setLoading(false);
  }, [page, sortBy, sortOrder, search, mwIdx, logpIdx, minQed]);

  const loadStats = useCallback(async () => {
    const r = await apiClient.moleculeStats();
    if (r.ok) setStats(r.data);
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadStats(); }, [loadStats]);

  // ============ sync ============

  async function sync() {
    setSyncing(true);
    setSyncResult(null);
    const r = await apiClient.syncMolecules();
    setSyncResult(r.ok ? r.data : null);
    if (!r.ok) setError(r.error);
    setSyncing(false);
    await load();
    await loadStats();
  }

  // ============ helpers ============

  function handleSort(key: string) {
    if (sortBy === key) setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    else { setSortBy(key); setSortOrder("asc"); }
    setPage(1);
  }

  function fmt(val: number | null | undefined, digits = 2) {
    return val != null ? val.toFixed(digits) : "-";
  }

  function fileSize(bytes: number | null) {
    if (!bytes) return "-";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  }

  function qedBadge(val: number | null) {
    if (val == null) return <span className="text-slate-300">-</span>;
    const cls = val >= 0.7 ? "bg-teal/10 text-teal" : val >= 0.4 ? "bg-amber/10 text-amber" : "bg-rose/10 text-rose";
    return <span className={`inline-flex px-2 py-0.5 text-xs font-medium ${cls}`}>{val.toFixed(3)}</span>;
  }

  // ============ render ============

  return (
    <section className="mx-auto max-w-[1400px] px-4 py-8 sm:px-6 lg:px-8">
      {/* header */}
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="stat-label mb-2">Molecule database</div>
          <h1 className="text-3xl font-semibold text-ink">{t("molTitle")}</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            {t("molDesc")}
            {stats && (
              <span className="ml-2 text-slate-400">
                · {stats.total_molecules} {t("molTotalMols")} · {stats.total_sdf_files} SDF
              </span>
            )}
          </p>
        </div>
        <button
          onClick={sync}
          disabled={syncing}
          className={`inline-flex h-10 items-center gap-2 px-4 text-sm font-semibold text-white shadow-soft transition ${
            syncing ? "cursor-not-allowed bg-slate-400" : "bg-teal hover:bg-teal/90"
          }`}
        >
          <RefreshCw size={16} className={syncing ? "animate-spin" : ""} />
          {syncing ? t("molSyncing") : t("molSync")}
        </button>
      </div>

      {/* stats cards */}
      {stats && (
        <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
          {[
            [t("molTotalMols"), stats.total_molecules],
            [t("molAvgMW"), `${fmt(stats.statistics.molecular_weight.avg)} g/mol`],
            [t("molAvgLogP"), fmt(stats.statistics.logp_avg, 2)],
            [t("molAvgQED"), fmt(stats.statistics.qed_avg, 3)],
            [t("molAvgTPSA"), `${fmt(stats.statistics.tpsa_avg, 1)} Å²`]
          ].map(([l, v]) => (
            <div key={l as string} className="panel p-4">
              <div className="stat-label">{l as string}</div>
              <div className="mt-1 text-lg font-semibold text-ink">{v as string}</div>
            </div>
          ))}
        </div>
      )}

      {/* sync result banner */}
      {syncResult && (
        <div className={`mb-6 p-4 text-sm ${
          syncResult.sync_result.errors.length ? "border border-amber/20 bg-amber/5 text-amber" : "border border-teal/20 bg-teal/5 text-teal"
        }`}>
          <div className="mb-2 flex items-center gap-2 font-semibold">
            {syncResult.sync_result.errors.length ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}
            {t("molSyncDone")}：{syncResult.sync_result.total_files_found} 文件
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs opacity-80">
            <span>新增 {syncResult.sync_result.new_files}</span>
            <span>更新 {syncResult.sync_result.updated_files}</span>
            <span>未变 {syncResult.sync_result.unchanged_files}</span>
            <span>+{syncResult.sync_result.total_conformers_added} conformers</span>
            {syncResult.sync_result.deleted_records > 0 && <span>-{syncResult.sync_result.deleted_records} records</span>}
          </div>
          {syncResult.sync_result.errors.length > 0 && (
            <div className="mt-2 text-xs text-rose">
              {syncResult.sync_result.errors.map((e, i) => (
                <div key={i}>{e.file}: {e.error}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* error */}
      {error && (
        <div className="mb-6 flex items-center gap-2 border border-rose/20 bg-rose/5 p-4 text-sm text-rose">
          <AlertTriangle size={16} />
          {error}
          <button onClick={() => setError(null)} className="ml-auto"><X size={16} /></button>
        </div>
      )}

      {/* toolbar */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search size={16} className="pointer-events-none absolute left-3 top-3 text-slate-400" />
          <input
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            placeholder={t("molSearch")}
            className="h-10 w-full border border-slate-200 pl-9 pr-9 text-sm outline-none focus:border-teal"
          />
          {search && (
            <button onClick={() => { setSearch(""); setPage(1); }} className="absolute right-3 top-3">
              <X size={14} className="text-slate-400 hover:text-slate-600" />
            </button>
          )}
        </div>
        {MW_RANGES.map((r, i) => (
          <button key={r.label} onClick={() => { setMwIdx(i); setPage(1); }}
            className={`h-9 border px-2.5 text-xs font-medium transition ${
              mwIdx === i ? "border-ink bg-ink text-white" : "border-slate-200 bg-white text-slate-600 hover:border-teal"
            }`}>{r.label}</button>
        ))}
        <span className="text-slate-300">|</span>
        {LOGP_RANGES.map((r, i) => (
          <button key={r.label} onClick={() => { setLogpIdx(i); setPage(1); }}
            className={`h-9 border px-2.5 text-xs font-medium transition ${
              logpIdx === i ? "border-ink bg-ink text-white" : "border-slate-200 bg-white text-slate-600 hover:border-teal"
            }`}>{r.label}</button>
        ))}
        <select value={minQed} onChange={(e) => { setMinQed(e.target.value); setPage(1); }}
          className="h-9 border border-slate-200 bg-white px-2 text-xs text-slate-600 outline-none focus:border-teal">
          <option value="">QED: All</option>
          <option value="0.3">QED ≥ 0.3</option>
          <option value="0.5">QED ≥ 0.5</option>
          <option value="0.7">QED ≥ 0.7</option>
          <option value="0.9">QED ≥ 0.9</option>
        </select>
        <span className="ml-auto text-sm text-slate-400">{total} {t("molResults")}</span>
      </div>

      {/* table */}
      <div className="panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead>
              <tr className="bg-slate-50">
                <th className="px-3 py-3 text-xs font-semibold text-slate-500 w-10">#</th>
                {SORT_FIELDS.map((f) => (
                  <th key={f.key} onClick={() => handleSort(f.key)}
                    className="cursor-pointer px-3 py-3 text-xs font-semibold text-slate-500 hover:text-ink whitespace-nowrap">
                    <span className="inline-flex items-center gap-1">
                      {f.label}
                      {sortBy === f.key && (sortOrder === "asc" ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}
                    </span>
                  </th>
                ))}
                <th className="px-3 py-3 text-xs font-semibold text-slate-500 whitespace-nowrap">SDF 文件</th>
                <th className="px-3 py-3 text-xs font-semibold text-slate-500 whitespace-nowrap">{t("molSdfPath")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {loading ? (
                <tr><td colSpan={13} className="px-4 py-20 text-center text-slate-400">
                  <Database size={40} className="mx-auto mb-3 opacity-30 animate-pulse" /><p>{t("molLoading")}</p>
                </td></tr>
              ) : molecules.length === 0 ? (
                <tr><td colSpan={13} className="px-4 py-20 text-center text-slate-400">
                  <FileCode size={40} className="mx-auto mb-3 opacity-30" />
                  <p className="mb-1">{t("molNoData")}</p>
                  <p className="text-xs">{t("molNoDataHint")}</p>
                </td></tr>
              ) : molecules.map((m, i) => (
                <tr key={m.id}
                  onClick={() => setSelected(m)}
                  className={`cursor-pointer transition-colors hover:bg-mist ${
                    selected?.id === m.id ? "bg-teal/5" : ""
                  }`}>
                  <td className="px-3 py-3 text-xs text-slate-400">{(page-1)*PAGE_SIZE+i+1}</td>
                  <td className="px-3 py-3 font-medium text-ink max-w-[160px] truncate" title={m.name || ""}>
                    {m.name || <span className="italic text-slate-300">{t("molUnnamed")}</span>}
                  </td>
                  <td className="px-3 py-3 font-mono text-xs text-teal">{fmt(m.molecular_weight)}</td>
                  <td className="px-3 py-3 font-mono text-xs text-slate-600">{fmt(m.logp, 2)}</td>
                  <td className="px-3 py-3">{qedBadge(m.qed)}</td>
                  <td className="px-3 py-3 text-xs text-slate-500">{m.num_heavy_atoms ?? "-"}</td>
                  <td className="px-3 py-3 text-xs text-slate-500">{m.num_rotatable_bonds ?? "-"}</td>
                  <td className="px-3 py-3 text-xs text-slate-500">{fmt(m.tpsa, 1)}</td>
                  <td className="px-3 py-3 font-mono text-xs text-slate-500 max-w-[120px] truncate" title={m.molecular_formula || ""}>
                    {m.molecular_formula || "-"}
                  </td>
                  <td className="px-3 py-3 text-xs text-slate-400">
                    {m.created_at ? new Date(m.created_at).toLocaleDateString() : "-"}
                  </td>
                  <td className="px-3 py-3">
                    <span className="inline-flex items-center gap-1 border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs font-mono text-cobalt">
                      <FileCode size={12} />{m.sdf_filename}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-xs text-slate-400 font-mono max-w-[200px] truncate" title={m.sdf_file_path}>
                    {m.sdf_file_path}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3">
            <span className="text-xs text-slate-500">{t("commonPage")}{page}{t("commonOf")}{totalPages} · {total}{t("commonRecords")}</span>
            <div className="flex items-center gap-2">
              <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1}
                className="inline-flex h-8 items-center gap-1 border border-slate-200 bg-white px-2 text-xs text-slate-600 hover:border-teal disabled:opacity-40">
                <ChevronLeft size={14} />上一页
              </button>
              {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                const start = Math.max(1, Math.min(page - 2, totalPages - 4));
                const p = start + i;
                if (p > totalPages) return null;
                return (
                  <button key={p} onClick={() => setPage(p)}
                    className={`h-8 w-8 text-xs font-medium transition ${
                      page === p ? "bg-ink text-white" : "border border-slate-200 bg-white text-slate-600 hover:border-teal"
                    }`}>{p}</button>
                );
              })}
              <button onClick={() => setPage(Math.min(totalPages, page + 1))} disabled={page === totalPages}
                className="inline-flex h-8 items-center gap-1 border border-slate-200 bg-white px-2 text-xs text-slate-600 hover:border-teal disabled:opacity-40">
                下一页<ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* detail panel */}
      {selected && (
        <div className="panel mt-6 p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-lg font-semibold text-ink">
              <Database size={20} className="text-teal" />
              {selected.name || t("molDetail")}
            </h2>
            <button onClick={() => setSelected(null)} className="text-slate-400 hover:text-ink"><X size={20} /></button>
          </div>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            {[
              ["分子名称", selected.name],
              ["分子式", selected.molecular_formula, true],
              ["分子量", selected.molecular_weight != null ? `${selected.molecular_weight.toFixed(4)} g/mol` : null],
              ["SMILES", selected.smiles, true],
              ["InChI Key", selected.inchikey, true],
              ["LogP", fmt(selected.logp, 2)],
              ["TPSA", selected.tpsa != null ? `${selected.tpsa.toFixed(2)} Å²` : null],
              ["QED", fmt(selected.qed, 4)],
              ["重原子数", selected.num_heavy_atoms],
              ["可旋转键", selected.num_rotatable_bonds],
              ["H 键供体", selected.num_h_bond_donors],
              ["H 键受体", selected.num_h_bond_acceptors],
              ["构象", `${(selected.conformer_index||0)+1} / ${selected.total_conformers||1}`],
              ["SDF 文件名", selected.sdf_filename, true],
              ["文件大小", fileSize(selected.file_size_bytes)],
            ].map(([label, val, mono]) => (
              <div key={label as string}>
                <div className="stat-label mb-1">{label as string}</div>
                <div className={`text-sm text-ink ${mono ? "font-mono" : ""} truncate`} title={String(val ?? "")}>
                  {val ?? "-"}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-4 border-t border-slate-200 pt-4">
            <div className="stat-label mb-2">{t("molSdfPath")}</div>
            <code className="block break-all bg-slate-50 px-4 py-3 text-xs font-mono text-slate-700 select-all">
              {selected.sdf_file_path}
            </code>
          </div>
          {selected.sdf_properties && Object.keys(selected.sdf_properties).length > 0 && (
            <div className="mt-4 border-t border-slate-200 pt-4">
              <div className="stat-label mb-2">{t("molSdfProps")}</div>
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                {Object.entries(selected.sdf_properties).map(([k, v]) => (
                  <div key={k} className="surface px-3 py-2">
                    <div className="text-xs text-slate-400">{k}</div>
                    <div className="mt-0.5 truncate text-sm font-mono text-ink">{String(v)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
