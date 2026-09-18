// Reflejan los modelos reales de packages/shared-types — mantener en sync a mano, no hay
// generación automática de tipos entre Python y TypeScript en este monorepo todavía.

export interface PendingLead {
  run_id: string;
  tenant_id: string;
  place_id: string;
  display_name: string;
  phone_e164: string;
  message_text: string;
  gap_analysis: string;
  model: string;
  landing_url: string; // "" si no se generó sitio (cupo semanal agotado) -- ver Módulo 7
}

export interface RunStatus {
  run_id: string;
  tenant_id: string;
  query: string;
  status: "queued" | "running" | "completed" | "failed";
  places_found?: string;
  places_published?: string;
  places_duplicate?: string;
  error?: string;
}

export interface TriggerRunInput {
  tenantId: string;
  query: string;
  latitude?: number;
  longitude?: number;
  radiusMeters?: number;
  maxResults?: number;
}
