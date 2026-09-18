"use client";

import { useState } from "react";
import { getRunStatus, triggerRun } from "@/app/actions";
import type { RunStatus } from "@/lib/types";

const POLL_INTERVAL_MS = 2000;
const MAX_POLLS = 15; // ~30s -- suficiente para ver "completed" en la mayoría de los runs reales

export function TriggerRunForm({ defaultTenantId }: { defaultTenantId: string }) {
  const [query, setQuery] = useState("");
  const [tenantId, setTenantId] = useState(defaultTenantId);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function pollUntilDone(runId: string) {
    for (let attempt = 0; attempt < MAX_POLLS; attempt++) {
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      const result = await getRunStatus(runId);
      if ("ok" in result && !result.ok) {
        setError(result.error ?? "No se pudo consultar el estado del run");
        return;
      }
      const runStatus = result as RunStatus;
      setStatus(runStatus);
      if (runStatus.status === "completed" || runStatus.status === "failed") {
        return;
      }
    }
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    setIsSubmitting(true);
    try {
      const result = await triggerRun({ tenantId, query });
      if ("ok" in result && !result.ok) {
        setError(result.error ?? "No se pudo disparar el run");
        return;
      }
      const { runId } = result as { runId: string };
      setStatus({ run_id: runId, tenant_id: tenantId, query, status: "queued" });
      await pollUntilDone(runId);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="bg-white border border-navy/10 rounded-lg p-4 space-y-3">
      <h2 className="font-semibold text-navy">Nuevo run</h2>
      <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-2">
        <input
          type="text"
          value={tenantId}
          onChange={(event) => setTenantId(event.target.value)}
          placeholder="tenant_id"
          className="border border-navy/20 rounded-md px-3 py-2 text-sm sm:w-32"
          required
        />
        <input
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="ej. taquerias en Guadalajara"
          className="border border-navy/20 rounded-md px-3 py-2 text-sm flex-1"
          required
        />
        <button
          type="submit"
          disabled={isSubmitting}
          className="bg-orange text-white text-sm font-medium px-4 py-2 rounded-md disabled:opacity-50 whitespace-nowrap"
        >
          {isSubmitting ? "Corriendo…" : "Disparar run"}
        </button>
      </form>

      {error && <p className="text-sm text-red">{error}</p>}

      {status && (
        <div className="text-sm text-navy/70 border-t border-navy/10 pt-3">
          <p>
            Run <code className="text-xs bg-navy/5 px-1 py-0.5 rounded">{status.run_id}</code> —{" "}
            <span className="font-medium">{status.status}</span>
          </p>
          {status.status === "completed" && (
            <p>
              {status.places_found} negocios encontrados, {status.places_published} nuevos (van a
              agent-worker a calificar), {status.places_duplicate} ya se habían visto antes.
            </p>
          )}
          {status.status === "failed" && status.error && <p className="text-red">{status.error}</p>}
        </div>
      )}
    </div>
  );
}
