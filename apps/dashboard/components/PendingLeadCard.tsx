"use client";

import { useState, useTransition } from "react";
import { approveLead, rejectLead } from "@/app/actions";
import type { PendingLead } from "@/lib/types";

export function PendingLeadCard({ lead }: { lead: PendingLead }) {
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [resolved, setResolved] = useState<"approved" | "rejected" | null>(null);

  function handleApprove() {
    setError(null);
    startTransition(async () => {
      const result = await approveLead(lead.place_id, lead.tenant_id);
      if (!result.ok) {
        setError(result.error ?? "Error desconocido al aprobar");
        return;
      }
      setResolved("approved");
    });
  }

  function handleReject() {
    setError(null);
    startTransition(async () => {
      const result = await rejectLead(lead.place_id, lead.tenant_id);
      if (!result.ok) {
        setError(result.error ?? "Error desconocido al rechazar");
        return;
      }
      setResolved("rejected");
    });
  }

  if (resolved === "approved") {
    return (
      <div className="border border-lime rounded-lg p-4 bg-white/60">
        <p className="text-lime font-medium">✓ {lead.display_name} — aprobado, va a dispatcher.</p>
      </div>
    );
  }
  if (resolved === "rejected") {
    return (
      <div className="border border-charcoal/30 rounded-lg p-4 bg-white/60">
        <p className="text-charcoal font-medium">{lead.display_name} — rechazado.</p>
      </div>
    );
  }

  return (
    <div className="border border-navy/10 rounded-lg p-4 bg-white shadow-sm space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-semibold text-navy">{lead.display_name}</h3>
          <p className="text-sm text-navy/60">{lead.phone_e164}</p>
        </div>
        {lead.landing_url ? (
          <a
            href={lead.landing_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sky text-sm underline shrink-0"
          >
            Ver preview del sitio →
          </a>
        ) : (
          <span className="text-xs text-charcoal/50 shrink-0">Sin sitio (cupo semanal agotado)</span>
        )}
      </div>

      <div>
        <p className="text-xs uppercase tracking-wide text-navy/40 mb-1">Mensaje para WhatsApp</p>
        <p className="text-sm whitespace-pre-wrap">{lead.message_text}</p>
      </div>

      <div>
        <p className="text-xs uppercase tracking-wide text-navy/40 mb-1">Análisis de brecha digital</p>
        <p className="text-sm text-navy/70">{lead.gap_analysis}</p>
      </div>

      {error && <p className="text-sm text-red">{error}</p>}

      <div className="flex gap-2 pt-1">
        <button
          onClick={handleApprove}
          disabled={isPending}
          className="bg-lime text-white text-sm font-medium px-4 py-2 rounded-md disabled:opacity-50"
        >
          Aprobar
        </button>
        <button
          onClick={handleReject}
          disabled={isPending}
          className="bg-transparent border border-red text-red text-sm font-medium px-4 py-2 rounded-md disabled:opacity-50"
        >
          Rechazar
        </button>
      </div>
    </div>
  );
}
