"""Orchestration: requirement proposal and verification with deterministic validation of AI output."""
from . import ai, demo
from .grounding import find_quote, detect_id_contradictions
from .status import EVIDENCE_FOUND, NOT_FOUND, MANUAL_REVIEW, calculate_overall_status


def choose_mode(docs) -> str:
    if ai.gemini_configured():
        return "live"
    if demo.is_demo_package(docs):
        return "demo"
    raise ai.AIError("Gemini API is not configured. Set GEMINI_API_KEY and GEMINI_MODEL in backend/.env, "
                     "or open a synthetic demo review to try demo mode.")


def propose_requirements(proc_doc, mode, llm=None):
    """Returns (list of requirement dicts, notes[]). Quotes not found in the procedure are flagged, never trusted."""
    if proc_doc["extraction_status"] != "ok":
        raise ai.AIError("The selected procedure could not be read, so requirements cannot be extracted.")
    notes = []
    if mode == "demo":
        props, cut = demo.demo_extract(proc_doc), False
    else:
        props, cut = ai.llm_extract_requirements(proc_doc, llm or ai.call_gemini)
    if cut:
        notes.append(f"{proc_doc['filename']} exceeded {ai.MAX_DOC_CHARS} characters; the remainder was NOT analyzed.")
    out = []
    for p in props:
        found, page = find_quote(p.source_quote, proc_doc)
        d = p.model_dump()
        if not found:
            d["mandatory_status"] = "unclear"
            d["confidence"] = "low"
            d["uncertainty"] = (d["uncertainty"] + " Quotation could not be found verbatim in the procedure; "
                                "verify or remove.").strip()
        out.append({**d, "source_page": page, "source_document_id": proc_doc["id"]})
    return out, notes


def verify(review, docs, requirements, mode, llm=None):
    """Returns dict(results, contradictions, overall_status, reasons, notes). Raises AIError on AI failure
    (no partial or fabricated results are produced)."""
    llm = llm or ai.call_gemini
    proc_ids = {r["source_document_id"] for r in requirements}
    evidence_docs = [d for d in docs if d["id"] not in proc_ids]
    readable = [d for d in evidence_docs if d["extraction_status"] == "ok"]
    problems = [d for d in docs if d["extraction_status"] != "ok"]
    truncated = [d for d in readable if len(d.get("text") or "") > ai.MAX_DOC_CHARS]
    by_id = {d["id"]: d for d in readable}
    notes = [f"{d['filename']} could not be read ({d['extraction_status']}): not analyzed." for d in problems]
    notes += [f"{d['filename']} exceeds {ai.MAX_DOC_CHARS} characters; the remainder was NOT analyzed." for d in truncated]

    contradictions = detect_id_contradictions(review["equipment_id"], readable)
    results = []
    for req in requirements:
        m = demo.demo_match(req, readable) if mode == "demo" else ai.llm_match(req, readable, llm)
        res = {"requirement_id": req["id"], "mandatory_status": req["mandatory_status"],
               "status": m.status, "evidence_document_id": None, "evidence_page": None,
               "evidence_quote": None, "explanation": m.explanation,
               "missing_evidence": m.missing_evidence, "uncertainty_reason": m.uncertainty_reason}
        if m.contradiction:
            contradictions.append({"kind": "ai", "document": None,
                                   "description": f"[{req['description'][:60]}] {m.contradiction}"})
        if m.status in (EVIDENCE_FOUND, MANUAL_REVIEW) and m.evidence_quote:
            d = by_id.get(m.evidence_document_id)
            found, page = find_quote(m.evidence_quote, d) if d else (False, None)
            if found:
                res.update(evidence_document_id=d["id"], evidence_page=page, evidence_quote=m.evidence_quote)
            elif m.status == EVIDENCE_FOUND:
                res.update(status=MANUAL_REVIEW, uncertainty_reason="The quotation returned by the analysis "
                           "could not be verified in the source text, so the evidence is not accepted.")
        elif m.status == EVIDENCE_FOUND:   # no quote at all = not traceable
            res.update(status=MANUAL_REVIEW, uncertainty_reason="No source quotation was provided.")
        if res["status"] == NOT_FOUND and (problems or truncated):
            res.update(status=MANUAL_REVIEW, uncertainty_reason="Some documents were unreadable or only "
                       "partly analyzed, so absence of evidence cannot be confirmed.")
        results.append(res)

    overall, reasons = calculate_overall_status(results, contradictions, problems)
    return {"results": results, "contradictions": contradictions, "overall_status": overall,
            "reasons": reasons, "notes": notes}
