import { CheckCircle2, Loader2, AlertTriangle } from "lucide-react";

export type StepStatus = "idle" | "loading" | "done" | "error";

export interface StepResult {
  status: StepStatus;
  message: string;
  data?: Record<string, unknown>;
}

export function ResultCard({ result, title }: { result: StepResult; title?: string }) {
  if (result.status === "idle") return null;

  const styles = {
    done: { border: '#c8e6c9', bg: '#f1f8e9', icon: "text-green-600" },
    error: { border: '#ffcdd2', bg: '#ffebee', icon: "text-red-600" },
    loading: { border: '#e5ebf0', bg: '#f8fafb', icon: "text-primary" },
  };

  const s = styles[result.status] || styles.loading;

  return (
    <div
      className="mt-4 flex items-start gap-3 rounded-lg p-4 text-sm"
      style={{ border: `1px solid ${s.border}`, background: s.bg }}
    >
      {result.status === "loading" && <Loader2 size={16} className={`mt-0.5 shrink-0 animate-spin ${s.icon}`} />}
      {result.status === "done" && <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-green-600" />}
      {result.status === "error" && <AlertTriangle size={16} className="mt-0.5 shrink-0 text-red-600" />}
      <div className="min-w-0 flex-1">
        {title && <p className="font-display font-semibold text-ink">{title}</p>}
        <p className={result.status === "error" ? "text-red-700" : "text-muted"}>{result.message}</p>
        {result.data && (
          <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 rounded-lg p-3 text-xs bg-white border border-slate-100">
            {Object.entries(result.data).map(([key, value]) => (
              <span key={key} className="contents">
                <span className="text-muted">{key}</span>
                <span className="font-mono text-ink font-medium">{String(value ?? "—")}</span>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
