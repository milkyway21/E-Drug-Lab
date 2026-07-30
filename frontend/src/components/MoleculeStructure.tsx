"use client";

import { apiClient } from "@/lib/api-client";
import { FlaskConical } from "lucide-react";

interface MoleculeStructureProps {
  moleculeId?: string;
  width?: number;
  height?: number;
}

export function MoleculeStructure({
  moleculeId,
  width = 320,
  height = 220,
}: MoleculeStructureProps) {
  if (!moleculeId) {
    return (
      <div
        className="flex flex-col items-center justify-center gap-2 rounded-lg text-xs text-muted bg-slate-50 border border-slate-200"
        style={{ width, height }}
      >
        <FlaskConical size={24} className="text-slate-300" />
        <span>No molecule</span>
      </div>
    );
  }

  const src = `${apiClient.apiBaseUrl}/api/v1/molecule-db/molecules/${moleculeId}/svg`;

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-2">
      <div className="flex items-center justify-center rounded overflow-hidden bg-slate-50">
        <img
          src={src}
          width={width - 16}
          height={height - 16}
          alt="2D structure"
          className="block"
        />
      </div>
    </div>
  );
}
