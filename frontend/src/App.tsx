import { useEffect, useState } from "react";
import { ShieldCheck, LayoutDashboard, FilePlus2, History, Settings as Cog, Upload, FileText, Download, Play,
  AlertTriangle, CheckCircle2, XCircle, Trash2, Check, FlaskConical } from "lucide-react";
import { api, Bundle, Health, Req, Result, Summary } from "./api";

const DISCLAIMER = "Senim Bot checks the availability and consistency of documentary evidence only. It does not certify equipment safety or authorize operation. Final decisions must be made by a qualified, authorized specialist.";
const OVERALL: Record<string, { label: string; cls: string }> = {
  DOCUMENTATION_COMPLETE: { label: "DOCUMENTATION COMPLETE — HUMAN REVIEW REQUIRED", cls: "bg-green-100 text-green-800 border-green-300" },
  DOCUMENTATION_INCOMPLETE: { label: "DOCUMENTATION INCOMPLETE", cls: "bg-red-100 text-red-800 border-red-300" },
  MANUAL_REVIEW_REQUIRED: { label: "MANUAL REVIEW REQUIRED", cls: "bg-amber-100 text-amber-800 border-amber-300" },
};
const ITEM: Record<string, { label: string; cls: string }> = {
  EVIDENCE_FOUND: { label: "EVIDENCE FOUND", cls: "bg-green-100 text-green-800" },
  NOT_FOUND: { label: "NOT FOUND", cls: "bg-red-100 text-red-800" },
  MANUAL_REVIEW_REQUIRED: { label: "MANUAL REVIEW REQUIRED", cls: "bg-amber-100 text-amber-800" },
};
const DOC_TYPES: [string, string][] = [["procedure", "Internal procedure"], ["repair_report", "Repair completion report"],
  ["test_report", "Inspection / test report"], ["work_permit", "Work permit"], ["maintenance_record", "Maintenance record"], ["other", "Other"]];

type View = "dashboard" | "new" | "review" | "history" | "settings";
const Pill = ({ s, map }: { s: string | null; map: Record<string, { label: string; cls: string }> }) =>
  s && map[s] ? <span className={`rounded px-2 py-0.5 text-xs font-semibold ${map[s].cls}`}>{map[s].label}</span> : <span className="text-xs text-slate-500">Not verified</span>;

export default function App() {
  const [view, setView] = useState<View>("dashboard");
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [list, setList] = useState<Summary[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const refresh = () => api.list().then(setList).catch(e => setError(e.message));
  useEffect(() => { refresh(); api.health().then(setHealth).catch(() => setError("Backend is not reachable. Start it with: uvicorn app.main:app --port 8000")); }, []);

  const run = async <T,>(label: string, fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(label); setError("");
    try { return await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(""); }
  };
  const open = async (id: number) => { const b = await run("Loading review…", () => api.get(id)); if (b) { setBundle(b); setView("review"); } };
  const demo = async (s: "a" | "b") => { const b = await run("Creating synthetic demo…", () => api.demo(s)); if (b) { setBundle(b); setView("review"); refresh(); } };

  const nav: [View, string, JSX.Element][] = [["dashboard", "Dashboard", <LayoutDashboard size={16} />], ["new", "New review", <FilePlus2 size={16} />],
    ["history", "History", <History size={16} />], ["settings", "Settings / API", <Cog size={16} />]];

  return (
    <div className="min-h-screen md:flex">
      <aside className="border-b border-slate-200 bg-navy p-4 text-white md:min-h-screen md:w-56 md:border-b-0">
        <div className="mb-1 flex items-center gap-2 text-lg font-bold"><ShieldCheck /> Senim Bot</div>
        <p className="mb-4 text-xs text-slate-300">Documentary evidence checks before return to operation</p>
        <nav className="flex gap-1 md:flex-col">
          {nav.map(([v, l, icon]) => (
            <button key={v} onClick={() => { setView(v); refresh(); }}
              className={`flex items-center gap-2 rounded px-3 py-2 text-left text-sm ${view === v ? "bg-brand" : "hover:bg-white/10"}`}>{icon}{l}</button>))}
        </nav>
      </aside>
      <main className="flex-1 p-4 md:p-6">
        <div className="mb-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">{DISCLAIMER}</div>
        {error && <div className="mb-4 flex items-start gap-2 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800"><XCircle size={16} className="mt-0.5 shrink-0" />{error}</div>}
        {busy && <div className="mb-4 text-sm text-brand">{busy}</div>}
        {view === "dashboard" && <Dashboard list={list} onOpen={open} onNew={() => setView("new")} onDemo={demo} />}
        {view === "new" && <NewReview run={run} onCreated={b => { setBundle(b); setView("review"); refresh(); }} />}
        {view === "review" && bundle && <ReviewPage bundle={bundle} setBundle={setBundle} run={run} health={health} />}
        {view === "history" && <HistoryList list={list} onOpen={open} />}
        {view === "settings" && <SettingsPage health={health} />}
      </main>
    </div>
  );
}

type RunFn = <T>(label: string, fn: () => Promise<T>) => Promise<T | undefined>;

function Dashboard({ list, onOpen, onNew, onDemo }: { list: Summary[]; onOpen: (id: number) => void; onNew: () => void; onDemo: (s: "a" | "b") => void }) {
  const count = (s: string) => list.filter(r => r.overall_status === s).length;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2"><h1 className="text-2xl font-bold">Dashboard</h1>
        <button className="btn-primary" onClick={onNew}><FilePlus2 size={16} /> New review</button></div>
      <p className="text-sm text-slate-600">Compares requirements from an internal procedure with the documents you upload and shows where evidence is present, missing or needs a specialist.</p>
      <div className="grid gap-3 sm:grid-cols-4">
        {[["Reviews", list.length, ""], ["Complete", count("DOCUMENTATION_COMPLETE"), "text-green-700"], ["Incomplete", count("DOCUMENTATION_INCOMPLETE"), "text-red-700"], ["Manual review", count("MANUAL_REVIEW_REQUIRED"), "text-amber-700"]].map(([l, n, c]) => (
          <div key={String(l)} className="card"><div className="text-xs text-slate-500">{l}</div><div className={`text-2xl font-bold ${c}`}>{n}</div></div>))}
      </div>
      <div className="card border-brand/40"><div className="mb-2 flex items-center gap-2 font-semibold"><FlaskConical size={16} /> Synthetic demo project — pump P-101, mechanical seal replacement</div>
        <p className="mb-3 text-sm text-slate-600">Fictional documents labeled SYNTHETIC DEMO DATA. Runs in DEMO MODE — NOT LIVE AI ANALYSIS (no API key needed).</p>
        <div className="flex flex-wrap gap-2"><button className="btn-ghost" onClick={() => onDemo("a")}>Scenario A — evidence available</button>
          <button className="btn-ghost" onClick={() => onDemo("b")}>Scenario B — leak test report missing</button></div></div>
      <HistoryList list={list.slice(0, 5)} onOpen={onOpen} title="Recent reviews" />
    </div>);
}

function HistoryList({ list, onOpen, title = "Review history" }: { list: Summary[]; onOpen: (id: number) => void; title?: string }) {
  return (
    <div className="card overflow-x-auto"><h2 className="mb-2 font-semibold">{title}</h2>
      {list.length === 0 ? <p className="text-sm text-slate-500">No reviews yet.</p> :
        <table className="w-full text-left text-sm"><thead className="text-xs text-slate-500"><tr><th>Equipment</th><th>Date</th><th>Documents</th><th>Status</th><th /></tr></thead>
          <tbody>{list.map(r => (<tr key={r.id} className="border-t">
            <td className="py-2">{r.equipment_id} <span className="text-slate-500">{r.equipment_type}</span>{r.is_demo ? <span className="ml-2 rounded bg-slate-200 px-1 text-xs">DEMO</span> : null}</td>
            <td>{r.review_date}</td><td>{r.document_count}</td><td><Pill s={r.overall_status} map={OVERALL} /></td>
            <td><button className="btn-ghost" onClick={() => onOpen(r.id)}>Open</button></td></tr>))}</tbody></table>}
    </div>);
}

function NewReview({ run, onCreated }: { run: RunFn; onCreated: (b: Bundle) => void }) {
  const [f, setF] = useState({ equipment_id: "", equipment_type: "", maintenance_description: "", review_date: new Date().toISOString().slice(0, 10), notes: "" });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const ok = f.equipment_id && f.equipment_type && f.maintenance_description && f.review_date;
  return (
    <form className="card max-w-xl space-y-3" onSubmit={async e => { e.preventDefault(); const b = await run("Creating review…", () => api.create(f)); if (b) onCreated(b); }}>
      <h1 className="text-xl font-bold">New equipment review</h1>
      <label className="block text-sm">Equipment ID<input className="input" placeholder="P-101" value={f.equipment_id} onChange={set("equipment_id")} /></label>
      <label className="block text-sm">Equipment type<input className="input" placeholder="Centrifugal pump" value={f.equipment_type} onChange={set("equipment_type")} /></label>
      <label className="block text-sm">Repair / maintenance description<textarea className="input" placeholder="Mechanical seal replacement" value={f.maintenance_description} onChange={set("maintenance_description")} /></label>
      <label className="block text-sm">Review date<input type="date" className="input" value={f.review_date} onChange={set("review_date")} /></label>
      <label className="block text-sm">Notes (optional)<textarea className="input" value={f.notes} onChange={set("notes")} /></label>
      <button className="btn-primary" disabled={!ok}>Create review</button>
    </form>);
}

function ReviewPage({ bundle, setBundle, run, health }: { bundle: Bundle; setBundle: (b: Bundle) => void; run: RunFn; health: Health | null }) {
  const { review, documents, results } = bundle;
  const [procId, setProcId] = useState<number | "">("");
  const [reqs, setReqs] = useState<Req[]>(bundle.requirements);
  const [sel, setSel] = useState<Result | null>(null);
  useEffect(() => { setReqs(bundle.requirements); setSel(null); }, [bundle]);
  useEffect(() => { const p = documents.find(d => d.document_type === "procedure"); if (p && procId === "") setProcId(p.id); }, [documents]);

  const upd = (i: number, patch: Partial<Req>) => setReqs(reqs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const counts = (s: string) => results.filter(r => r.status === s).length;
  const liveMissing = !health?.ai_configured && !review.is_demo;
  const doVerify = async () => {
    const saved = await run("Saving requirements…", () => api.saveReqs(review.id, reqs));
    if (!saved) return;
    const b = await run("Verifying documents…", () => api.verify(review.id));
    if (b) setBundle(b);
  };

  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-bold">{review.equipment_id} — {review.equipment_type}</h1>
        <p className="text-sm text-slate-600">{review.maintenance_description} · {review.review_date}</p>
        {review.is_demo && <p className="mt-1 text-xs font-semibold text-red-700">SYNTHETIC DEMO DATA · DEMO MODE — NOT LIVE AI ANALYSIS</p>}
        {liveMissing && <p className="mt-1 text-xs text-amber-700">Gemini is not configured: real documents cannot be analyzed. See Settings / API.</p>}</div>

      <section className="card"><h2 className="mb-2 font-semibold">1. Documents</h2>
        <label className="btn-ghost cursor-pointer"><Upload size={16} /> Upload PDF / DOCX
          <input type="file" multiple accept=".pdf,.docx" className="hidden" onChange={async e => {
            const files = Array.from(e.target.files ?? []); e.target.value = "";
            if (files.length) { const b = await run("Uploading and extracting…", () => api.upload(review.id, files)); if (b) setBundle(b); } }} /></label>
        <table className="mt-3 w-full text-left text-sm"><thead className="text-xs text-slate-500"><tr><th>File</th><th>Category</th><th>Extraction</th><th>Pages</th></tr></thead>
          <tbody>{documents.map(d => (<tr key={d.id} className="border-t align-top">
            <td className="py-2"><FileText size={14} className="mr-1 inline" />{d.filename}</td>
            <td><select className="input py-1" value={d.document_type} onChange={async e => { const b = await run("Updating…", () => api.setType(review.id, d.id, e.target.value)); if (b) setBundle(b); }}>
              {DOC_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></td>
            <td className={d.extraction_status === "ok" ? "text-green-700" : "text-red-700"}>{d.extraction_status === "ok" ? "Text extracted" : d.extraction_message}</td>
            <td>{d.page_count ?? "n/a"}</td></tr>))}</tbody></table>
        {documents.length === 0 && <p className="mt-2 text-sm text-slate-500">No documents uploaded yet.</p>}</section>

      <section className="card"><h2 className="mb-2 font-semibold">2. Requirements</h2>
        <div className="flex flex-wrap items-center gap-2">
          <select className="input w-auto" value={procId} onChange={e => setProcId(Number(e.target.value))}>
            <option value="">Select the internal procedure…</option>{documents.map(d => <option key={d.id} value={d.id}>{d.filename}</option>)}</select>
          <button className="btn-primary" disabled={procId === ""} onClick={async () => { const b = await run("Extracting requirements…", () => api.extract(review.id, Number(procId))); if (b) setBundle(b); }}><Play size={16} /> Extract requirements</button></div>
        {review.analysis_notes.map((n, i) => <p key={i} className="mt-2 text-xs text-amber-700">{n}</p>)}
        {reqs.length > 0 && <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-xs text-slate-500">
          <tr><th>Approve</th><th>Requirement</th><th>Mandatory</th><th>Source quotation</th><th>Evidence type</th><th>Confidence</th><th /></tr></thead>
          <tbody>{reqs.map((r, i) => (<tr key={i} className="border-t align-top">
            <td className="py-2"><input type="checkbox" checked={!!r.approved_by_user} onChange={e => upd(i, { approved_by_user: e.target.checked })} /></td>
            <td><textarea className="input min-w-[14rem]" value={r.description} onChange={e => upd(i, { description: e.target.value })} /></td>
            <td><select className="input" value={r.mandatory_status} onChange={e => upd(i, { mandatory_status: e.target.value as Req["mandatory_status"] })}>
              <option value="mandatory">mandatory</option><option value="optional">optional</option><option value="unclear">unclear</option></select></td>
            <td className="max-w-xs text-xs italic text-slate-600">“{r.source_quote}” <span className="not-italic">— {r.source_page ? `page ${r.source_page}` : "Page unavailable"}</span>
              {r.uncertainty && <div className="not-italic text-amber-700">{r.uncertainty}</div>}</td>
            <td><input className="input" value={r.expected_evidence_type} onChange={e => upd(i, { expected_evidence_type: e.target.value })} /></td>
            <td className="text-xs">{r.confidence}</td>
            <td><button title="Remove" className="text-red-600" onClick={() => setReqs(reqs.filter((_, j) => j !== i))}><Trash2 size={16} /></button></td></tr>))}</tbody></table>
          <div className="mt-3 flex flex-wrap gap-2">
            <button className="btn-ghost" onClick={() => setReqs(reqs.map(r => ({ ...r, approved_by_user: true })))}><Check size={16} /> Approve all</button>
            <button className="btn-primary" disabled={!reqs.some(r => r.approved_by_user)} onClick={doVerify}><Play size={16} /> Verify documents</button></div></div>}</section>

      {review.overall_status && (<section className="card space-y-3"><h2 className="font-semibold">3. Verification results</h2>
        <div className={`rounded-md border p-3 text-lg font-bold ${OVERALL[review.overall_status].cls}`}>{OVERALL[review.overall_status].label}</div>
        <ul className="list-disc pl-5 text-sm">{review.status_reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        <p className="text-xs text-slate-600">Mode: {review.analysis_mode === "demo" ? "DEMO MODE — NOT LIVE AI ANALYSIS" : "Gemini-assisted analysis with deterministic validation"}. This result is not proof of equipment safety.</p>
        <div className="grid gap-2 sm:grid-cols-3">
          <div className="card"><CheckCircle2 className="text-green-600" /> Found: <b>{counts("EVIDENCE_FOUND")}</b></div>
          <div className="card"><XCircle className="text-red-600" /> Not found: <b>{counts("NOT_FOUND")}</b></div>
          <div className="card"><AlertTriangle className="text-amber-600" /> Manual review: <b>{counts("MANUAL_REVIEW_REQUIRED")}</b></div></div>
        {review.contradictions.length > 0 && <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm"><b>Contradictions detected</b>
          <ul className="list-disc pl-5">{review.contradictions.map((c, i) => <li key={i}>{c.description}</li>)}</ul></div>}
        {review.analysis_notes.map((n, i) => <p key={i} className="text-xs text-amber-700">{n}</p>)}
        <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-xs text-slate-500"><tr><th>Requirement</th><th>Status</th><th>Source</th><th /></tr></thead>
          <tbody>{results.map(r => (<tr key={r.id} className="border-t align-top">
            <td className="py-2">{r.description}<div className="text-xs text-slate-500">{r.mandatory_status}</div></td>
            <td><Pill s={r.status} map={ITEM} /></td>
            <td className="text-xs">{r.evidence_filename ? `${r.evidence_filename}, ${r.evidence_page ? "page " + r.evidence_page : "Page unavailable"}` : "—"}</td>
            <td><button className="btn-ghost" onClick={() => setSel(r)}>Evidence</button></td></tr>))}</tbody></table></div>
        {results.some(r => r.status === "NOT_FOUND") && <div className="text-sm"><b>Missing evidence</b> (not found in the uploaded package; this does not prove the action did not happen):
          <ul className="list-disc pl-5">{results.filter(r => r.status === "NOT_FOUND").map(r => <li key={r.id}>{r.missing_evidence || r.description}</li>)}</ul></div>}
        {sel && <div className="rounded-md border border-brand/40 bg-blue-50 p-3 text-sm"><div className="mb-1 font-semibold">Evidence viewer</div>
          <div><b>Requirement:</b> {sel.description} <Pill s={sel.status} map={ITEM} /></div>
          <div><b>Procedure quotation:</b> <i>“{sel.source_quote}”</i> ({sel.source_filename ?? "n/a"}, {sel.source_page ? "page " + sel.source_page : "Page unavailable"})</div>
          <div><b>Evidence source:</b> {sel.evidence_filename ?? "none"}{sel.evidence_filename ? `, ${sel.evidence_page ? "page " + sel.evidence_page : "Page unavailable"}` : ""}</div>
          {sel.evidence_quote && <div><b>Quotation:</b> <i>“{sel.evidence_quote}”</i></div>}
          <div><b>Explanation:</b> {sel.explanation}</div>
          {sel.missing_evidence && <div><b>Missing:</b> {sel.missing_evidence}</div>}
          {sel.uncertainty_reason && <div className="text-amber-800"><b>Reason for manual review:</b> {sel.uncertainty_reason}</div>}</div>}
        <a className="btn-primary" href={api.reportUrl(review.id)}><Download size={16} /> Download PDF report</a></section>)}
    </div>);
}

function SettingsPage({ health }: { health: Health | null }) {
  return (
    <div className="card max-w-xl space-y-2"><h1 className="text-xl font-bold">Settings / API status</h1>
      <p className="text-sm">Backend: <b>{health ? "reachable" : "not reachable"}</b></p>
      <p className="text-sm">Gemini integration: <b className={health?.ai_configured ? "text-green-700" : "text-amber-700"}>{health?.ai_configured ? `configured (model: ${health.model})` : "not configured"}</b></p>
      {!health?.ai_configured && <div className="text-sm text-slate-700">Copy <code>backend/.env.example</code> to <code>backend/.env</code>, set <code>GEMINI_API_KEY</code> and <code>GEMINI_MODEL</code>, then restart the backend. The key is never shown in the browser. Without a key, only the synthetic demo reviews work (DEMO MODE — NOT LIVE AI ANALYSIS).</div>}
    </div>);
}
