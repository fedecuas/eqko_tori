"use server";

import { revalidatePath } from "next/cache";
import { getConfig } from "@/lib/config";
import type { PendingLead, RunStatus, TriggerRunInput } from "@/lib/types";

export interface ActionResult {
  ok: boolean;
  error?: string;
}

async function approvalGateFetch(path: string, init?: RequestInit): Promise<Response> {
  const config = getConfig();
  return fetch(`${config.approvalGateUrl}${path}`, {
    ...init,
    headers: { "X-Internal-Api-Key": config.approvalGateApiKey, ...init?.headers },
    cache: "no-store",
  });
}

async function extractorFetch(path: string, init?: RequestInit): Promise<Response> {
  const config = getConfig();
  return fetch(`${config.extractorUrl}${path}`, {
    ...init,
    headers: {
      "X-Internal-Api-Key": config.extractorApiKey,
      "Content-Type": "application/json",
      ...init?.headers,
    },
    cache: "no-store",
  });
}

export async function listPending(tenantId: string): Promise<PendingLead[]> {
  const response = await approvalGateFetch(`/pending?tenant_id=${encodeURIComponent(tenantId)}`);
  if (!response.ok) {
    throw new Error(`approval-gate /pending devolvió ${response.status}`);
  }
  return response.json();
}

export async function approveLead(placeId: string, tenantId: string): Promise<ActionResult> {
  const response = await approvalGateFetch(
    `/leads/${encodeURIComponent(placeId)}/approve?tenant_id=${encodeURIComponent(tenantId)}`,
    { method: "POST" },
  );
  revalidatePath("/");
  if (!response.ok) {
    return { ok: false, error: `approve devolvió ${response.status}` };
  }
  return { ok: true };
}

export async function rejectLead(placeId: string, tenantId: string): Promise<ActionResult> {
  const response = await approvalGateFetch(
    `/leads/${encodeURIComponent(placeId)}/reject?tenant_id=${encodeURIComponent(tenantId)}`,
    { method: "POST" },
  );
  revalidatePath("/");
  if (!response.ok) {
    return { ok: false, error: `reject devolvió ${response.status}` };
  }
  return { ok: true };
}

export async function triggerRun(input: TriggerRunInput): Promise<{ runId: string } | ActionResult> {
  const response = await extractorFetch("/runs", {
    method: "POST",
    body: JSON.stringify({
      tenant_id: input.tenantId,
      query: input.query,
      latitude: input.latitude,
      longitude: input.longitude,
      radius_meters: input.radiusMeters,
      max_results: input.maxResults ?? 20,
    }),
  });
  if (!response.ok) {
    const detail = await response.text();
    return { ok: false, error: `extractor /runs devolvió ${response.status}: ${detail}` };
  }
  const body = await response.json();
  return { runId: body.run_id };
}

export async function getRunStatus(runId: string): Promise<RunStatus | ActionResult> {
  const response = await extractorFetch(`/runs/${encodeURIComponent(runId)}`);
  if (!response.ok) {
    return { ok: false, error: `extractor /runs/:id devolvió ${response.status}` };
  }
  return response.json();
}
