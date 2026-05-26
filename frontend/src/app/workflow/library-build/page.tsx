"use client";

import { useState } from "react";
import { Filter, Plus } from "lucide-react";
import { WorkflowHeader, WorkflowShell } from "@/components/workflow/WorkflowLayout";
import { apiClient } from "@/lib/api-client";

export default function LibraryBuildPage() {
  const [name, setName] = useState("Starter SDF library");
  const [source, setSource] = useState("custom");
  const [message, setMessage] = useState("Create a library record and prepare property filters.");

  async function createLibrary() {
    const result = await apiClient.createLibrary({
      name,
      source,
      description: "Recovered frontend starter library"
    });
    setMessage(result.ok ? `Created library: ${result.data.id}` : result.error);
  }

  return (
    <WorkflowShell current="/workflow/library-build">
      <WorkflowHeader
        badge="Library build"
        title="Library build"
        description="Manage candidate molecule sources and prepare filters for MW, LogP, HBD, HBA, TPSA, and QED."
      />
      <div className="panel p-6">
        <div className="grid gap-4 md:grid-cols-2">
          <label>
            <span className="stat-label">Library name</span>
            <input value={name} onChange={(event) => setName(event.target.value)} className="mt-2 h-10 w-full border border-slate-200 px-3 text-sm outline-none focus:border-teal" />
          </label>
          <label>
            <span className="stat-label">Source</span>
            <select value={source} onChange={(event) => setSource(event.target.value)} className="mt-2 h-10 w-full border border-slate-200 px-3 text-sm outline-none focus:border-teal">
              <option value="custom">custom</option>
              <option value="zinc">zinc</option>
              <option value="chembl">chembl</option>
              <option value="generated">generated</option>
            </select>
          </label>
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-4">
          {["MW 150-500", "LogP -2-5", "HBD <= 5", "QED >= 0.4"].map((item) => (
            <div key={item} className="border border-slate-200 p-3 text-sm text-slate-600">
              <Filter size={15} className="mb-2 text-amber" />
              {item}
            </div>
          ))}
        </div>
        <button onClick={createLibrary} className="mt-5 inline-flex h-10 items-center gap-2 bg-teal px-4 text-sm font-medium text-white">
          <Plus size={16} />
          Create library
        </button>
        <p className="mt-5 border border-slate-200 bg-mist p-3 text-sm text-slate-600">{message}</p>
      </div>
    </WorkflowShell>
  );
}
