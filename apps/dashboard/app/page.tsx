import { listPending } from "@/app/actions";
import { getConfig } from "@/lib/config";
import { PendingLeadCard } from "@/components/PendingLeadCard";
import { TriggerRunForm } from "@/components/TriggerRunForm";

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ tenant?: string }>;
}) {
  const { defaultTenantId } = getConfig();
  const { tenant } = await searchParams;
  const tenantId = tenant || defaultTenantId;

  let pending: Awaited<ReturnType<typeof listPending>> = [];
  let loadError: string | null = null;
  try {
    pending = await listPending(tenantId);
  } catch (error) {
    loadError = error instanceof Error ? error.message : "Error desconocido";
  }

  return (
    <div className="space-y-8">
      <TriggerRunForm defaultTenantId={tenantId} />

      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-navy">Pendientes de aprobación</h2>
        <form className="flex items-center gap-2 text-sm">
          <label htmlFor="tenant" className="text-navy/50">
            tenant:
          </label>
          <input
            id="tenant"
            name="tenant"
            defaultValue={tenantId}
            className="border border-navy/20 rounded-md px-2 py-1 text-sm w-28"
          />
          <button type="submit" className="text-sky underline">
            Cambiar
          </button>
        </form>
      </div>

      {loadError && (
        <p className="text-sm text-red">
          No se pudo conectar con approval-gate: {loadError}. ¿Está corriendo{" "}
          <code className="bg-navy/5 px-1 py-0.5 rounded">uvicorn approval_gate.api:app</code>?
        </p>
      )}

      {!loadError && pending.length === 0 && (
        <p className="text-sm text-navy/50">No hay leads pendientes de aprobación para &quot;{tenantId}&quot;.</p>
      )}

      <div className="space-y-4">
        {pending.map((lead) => (
          <PendingLeadCard key={lead.place_id} lead={lead} />
        ))}
      </div>
    </div>
  );
}
