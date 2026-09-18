// Todo lo que toca estas variables corre server-side (Server Components / Server Actions) —
// las API keys de extractor/approval-gate nunca deben llegar al bundle del browser. Por eso
// esto es una función, no una constante evaluada al importar el módulo: si se llama desde el
// cliente por error, Next.js ya bloquea el acceso a process.env de variables sin prefijo
// NEXT_PUBLIC_, pero mantener esto perezoso además evita romper `next build` si todavía no
// hay `.env.local` cargado en esa máquina.
function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Falta la variable de entorno ${name} — ver .env.local.example`);
  }
  return value;
}

export function getConfig() {
  return {
    extractorUrl: process.env.EXTRACTOR_URL ?? "http://localhost:8000",
    extractorApiKey: required("EXTRACTOR_INTERNAL_API_KEY"),
    approvalGateUrl: process.env.APPROVAL_GATE_URL ?? "http://localhost:8001",
    approvalGateApiKey: required("APPROVAL_GATE_INTERNAL_API_KEY"),
    defaultTenantId: process.env.DEFAULT_TENANT_ID ?? "alba",
  };
}
