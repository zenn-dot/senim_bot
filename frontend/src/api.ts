export interface Doc { id: number; filename: string; document_type: string; extraction_status: string; extraction_message: string; page_count: number | null }
export interface Req { id?: number; description: string; mandatory_status: "mandatory" | "optional" | "unclear"; source_document_id: number | null;
  source_page: number | null; source_quote: string; expected_evidence_type: string; confidence: string; uncertainty: string; approved_by_user: boolean | number }
export interface Result { id: number; requirement_id: number; status: string; description: string; mandatory_status: string; source_quote: string; source_page: number | null;
  source_filename: string | null; evidence_filename: string | null; evidence_page: number | null; evidence_quote: string | null; explanation: string;
  missing_evidence: string | null; uncertainty_reason: string | null }
export interface Contradiction { kind: string; document: string | null; description: string }
export interface Review { id: number; equipment_id: string; equipment_type: string; maintenance_description: string; review_date: string; notes: string;
  overall_status: string | null; status_reasons: string[]; contradictions: Contradiction[]; analysis_notes: string[]; analysis_mode: string | null; is_demo: boolean }
export interface Bundle { review: Review; documents: Doc[]; requirements: Req[]; results: Result[] }
export interface Summary { id: number; equipment_id: string; equipment_type: string; review_date: string; overall_status: string | null; is_demo: number; document_count: number }
export interface Health { status: string; ai_configured: boolean; model: string | null }

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch("/api" + path, init);
  if (!r.ok) {
    let msg = `Request failed (${r.status})`;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* keep default */ }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}
const json = (method: string, body?: unknown): RequestInit => ({ method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  health: () => call<Health>("/health"),
  list: () => call<Summary[]>("/reviews"),
  get: (id: number) => call<Bundle>(`/reviews/${id}`),
  create: (b: Pick<Review, "equipment_id" | "equipment_type" | "maintenance_description" | "review_date" | "notes">) => call<Bundle>("/reviews", json("POST", b)),
  demo: (s: "a" | "b") => call<Bundle>(`/demo/${s}`, { method: "POST" }),
  upload: (id: number, files: File[]) => { const f = new FormData(); files.forEach(x => f.append("files", x)); return call<Bundle>(`/reviews/${id}/documents`, { method: "POST", body: f }); },
  setType: (id: number, doc: number, document_type: string) => call<Bundle>(`/reviews/${id}/documents/${doc}`, json("PATCH", { document_type })),
  extract: (id: number, procedure_document_id: number) => call<Bundle>(`/reviews/${id}/requirements/extract`, json("POST", { procedure_document_id })),
  saveReqs: (id: number, requirements: Req[]) => call<Bundle>(`/reviews/${id}/requirements`, json("PUT", { requirements: requirements.map(r => ({ ...r, approved_by_user: !!r.approved_by_user })) })),
  verify: (id: number) => call<Bundle>(`/reviews/${id}/verify`, { method: "POST" }),
  reportUrl: (id: number) => `/api/reviews/${id}/report/download`,
};
