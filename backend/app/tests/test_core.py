"""Tests use plain asserts and no fixtures, so they run with pytest (and with a bare loop)."""
import json, os, tempfile
import docx
from reportlab.pdfgen import canvas

from app.services import extraction, ai, demo, pipeline, grounding
from app.services.status import calculate_overall_status as calc
from app.services.report import build_report_pdf
from app.services.ai import AIError, ReqProposal, parse_model, MatchResult
from sample_data.generate_samples import generate

TMP = tempfile.mkdtemp()
REVIEW = {"equipment_id": "P-101"}


def _pdf(name, pages):
    p = os.path.join(TMP, name)
    c = canvas.Canvas(p)
    for t in pages:
        if t:
            c.drawString(50, 800, t)
        c.showPage()
    c.save()
    return p


def _docx(name, lines):
    p = os.path.join(TMP, name)
    d = docx.Document()
    for ln in lines:
        d.add_paragraph(ln)
    d.save(p)
    return p


def _doc(i, name, typ, text, status="ok", pages=None):
    return {"id": i, "filename": name, "document_type": typ, "text": text,
            "extraction_status": status, "page_count": pages}


def _req(i, desc, mand="mandatory", etype="test_report", src=1):
    return {"id": i, "description": desc, "mandatory_status": mand, "expected_evidence_type": etype,
            "source_document_id": src, "source_quote": desc, "source_page": None}


def _llm(**kw):
    return lambda prompt: json.dumps(kw)


# ---- extraction ----
def test_pdf_extraction_pages():
    r = extraction.extract(_pdf("a.pdf", ["First page text is here", "Second page text is here"]), "a.pdf")
    assert r.status == "ok" and r.page_count == 2 and "Second page" in r.pages[1]


def test_docx_extraction():
    r = extraction.extract(_docx("a.docx", ["Repair completed on pump P-101 today."]), "a.docx")
    assert r.status == "ok" and r.page_count is None and "P-101" in r.text


def test_corrupted_files():
    p = os.path.join(TMP, "bad.pdf"); open(p, "wb").write(b"not a pdf")
    q = os.path.join(TMP, "bad.docx"); open(q, "wb").write(b"not a docx")
    assert extraction.extract(p, "bad.pdf").status == "failed"
    assert extraction.extract(q, "bad.docx").status == "failed"
    assert extraction.extract(p, "x.txt").status == "failed"


def test_empty_and_scanned_documents():
    assert extraction.extract(_docx("e.docx", [""]), "e.docx").status == "empty"
    r = extraction.extract(_pdf("scan.pdf", [""]), "scan.pdf")
    assert r.status == "scanned" and "OCR" in r.message


# ---- schema / AI output ----
def test_requirement_schema_validation():
    ok = ReqProposal(description="Leak test report", mandatory_status="mandatory", source_quote="shall attach",
                     expected_evidence_type="test_report")
    assert ok.confidence == "medium"
    for bad in ({"description": "x"}, {"description": "Leak test", "mandatory_status": "maybe",
                                       "source_quote": "abc def", "expected_evidence_type": "t"}):
        try:
            ReqProposal(**bad); assert False, "should fail"
        except Exception:
            pass


def test_invalid_ai_response_and_api_failure():
    for raw in ("not json", '{"status": "VERIFIED_SAFE", "explanation": "x"}', ""):
        try:
            parse_model(raw, MatchResult); assert False
        except AIError:
            pass
    def boom(prompt): raise AIError("Gemini API call failed (URLError).")
    docs = [_doc(2, "t.pdf", "test_report", "Leak test PASS on P-101", pages=1)]
    try:
        pipeline.verify(REVIEW, docs, [_req(1, "Leak test report")], "live", llm=boom); assert False
    except AIError:
        pass
    try:
        pipeline.verify(REVIEW, docs, [_req(1, "Leak test report")], "live", llm=lambda p: "garbage"); assert False
    except AIError:
        pass


# ---- verification ----
DOC_TEXT = "Leak test result: PASS. Test pressure 6.0 bar for P-101"


def test_evidence_found_with_page():
    docs = [_doc(1, "proc.pdf", "procedure", "x"), _doc(2, "t.pdf", "test_report", "intro\fLeak test result: PASS. Test pressure 6.0 bar for P-101", pages=2)]
    llm = _llm(status="EVIDENCE_FOUND", evidence_document_id=2, evidence_quote="Leak test result: PASS.", explanation="Matches")
    out = pipeline.verify(REVIEW, docs, [_req(1, "Leak test report")], "live", llm)
    r = out["results"][0]
    assert r["status"] == "EVIDENCE_FOUND" and r["evidence_page"] == 2
    assert out["overall_status"] == "DOCUMENTATION_COMPLETE"


def test_fabricated_quote_is_rejected():
    docs = [_doc(1, "proc.pdf", "procedure", "x"), _doc(2, "t.pdf", "test_report", DOC_TEXT, pages=1)]
    llm = _llm(status="EVIDENCE_FOUND", evidence_document_id=2, evidence_quote="Everything inspected and safe.", explanation="ok")
    out = pipeline.verify(REVIEW, docs, [_req(1, "Leak test report")], "live", llm)
    assert out["results"][0]["status"] == "MANUAL_REVIEW_REQUIRED"
    assert out["results"][0]["evidence_quote"] is None


def test_mandatory_evidence_missing():
    docs = [_doc(1, "proc.pdf", "procedure", "x"), _doc(3, "r.docx", "repair_report", "Repair done on P-101")]
    llm = _llm(status="NOT_FOUND", explanation="No test report", missing_evidence="leak test report")
    out = pipeline.verify(REVIEW, docs, [_req(1, "Leak test report")], "live", llm)
    assert out["results"][0]["status"] == "NOT_FOUND"
    assert out["overall_status"] == "DOCUMENTATION_INCOMPLETE"


def test_conflicting_equipment_ids():
    docs = [_doc(1, "proc.pdf", "procedure", "x"), _doc(2, "t.pdf", "test_report", "Leak test PASS for pump P-102", pages=1)]
    llm = _llm(status="EVIDENCE_FOUND", evidence_document_id=2, evidence_quote="Leak test PASS for pump P-102", explanation="m")
    out = pipeline.verify(REVIEW, docs, [_req(1, "Leak test")], "live", llm)
    assert out["contradictions"] and "P-102" in out["contradictions"][0]["description"]
    assert out["overall_status"] == "MANUAL_REVIEW_REQUIRED"


def test_contradictory_evidence_reported_by_ai():
    docs = [_doc(1, "proc.pdf", "procedure", "x"), _doc(2, "t.pdf", "test_report", DOC_TEXT, pages=1)]
    llm = _llm(status="MANUAL_REVIEW_REQUIRED", evidence_document_id=2, evidence_quote="Leak test result: PASS.",
               explanation="Dates differ", uncertainty_reason="Conflicting dates", contradiction="Date 12 Oct vs 14 Oct")
    out = pipeline.verify(REVIEW, docs, [_req(1, "Leak test")], "live", llm)
    assert out["contradictions"] and out["overall_status"] == "MANUAL_REVIEW_REQUIRED"


def test_unreadable_source_blocks_not_found():
    docs = [_doc(1, "proc.pdf", "procedure", "x"), _doc(2, "scan.pdf", "test_report", "", status="scanned", pages=1)]
    llm = _llm(status="NOT_FOUND", explanation="nothing", missing_evidence="x")
    out = pipeline.verify(REVIEW, docs, [_req(1, "Leak test")], "live", llm)
    assert out["results"][0]["status"] == "MANUAL_REVIEW_REQUIRED"
    assert out["overall_status"] == "MANUAL_REVIEW_REQUIRED" and out["notes"]


def test_extract_requirements_flags_ungrounded_quote():
    proc = _doc(1, "proc.pdf", "procedure", "4.2 A leak test report SHALL be attached.", pages=1)
    llm = _llm(requirements=[
        {"description": "Leak test report", "mandatory_status": "mandatory", "source_quote": "A leak test report SHALL be attached.", "expected_evidence_type": "test_report"},
        {"description": "Invented", "mandatory_status": "mandatory", "source_quote": "Quote not in document at all", "expected_evidence_type": "x"}])
    reqs, _ = pipeline.propose_requirements(proc, "live", llm)
    assert reqs[0]["mandatory_status"] == "mandatory" and reqs[0]["source_page"] == 1
    assert reqs[1]["mandatory_status"] == "unclear" and reqs[1]["confidence"] == "low"


# ---- status calculation ----
def _r(m, s): return {"mandatory_status": m, "status": s}


def test_overall_status_rules():
    F, N, M = "EVIDENCE_FOUND", "NOT_FOUND", "MANUAL_REVIEW_REQUIRED"
    assert calc([_r("mandatory", F), _r("optional", N)])[0] == "DOCUMENTATION_COMPLETE"
    assert calc([_r("mandatory", F), _r("mandatory", N)])[0] == "DOCUMENTATION_INCOMPLETE"
    assert calc([_r("mandatory", M), _r("mandatory", N)])[0] == "DOCUMENTATION_INCOMPLETE"
    assert any("manual review" in x for x in calc([_r("mandatory", M), _r("mandatory", N)])[1])
    assert calc([_r("mandatory", M)])[0] == "MANUAL_REVIEW_REQUIRED"
    assert calc([_r("mandatory", F)], contradictions=[{"description": "x"}])[0] == "MANUAL_REVIEW_REQUIRED"
    assert calc([_r("mandatory", F)], extraction_problems=["x"])[0] == "MANUAL_REVIEW_REQUIRED"
    assert calc([_r("unclear", N), _r("mandatory", F)])[0] == "MANUAL_REVIEW_REQUIRED"
    assert calc([])[0] == "MANUAL_REVIEW_REQUIRED"


# ---- demo scenarios + report (real extraction path) ----
def _load(folder):
    types = {"Procedure": "procedure", "Repair": "repair_report", "Leak": "test_report", "Maintenance": "maintenance_record"}
    docs = []
    for i, f in enumerate(sorted(os.listdir(folder)), 1):
        r = extraction.extract(os.path.join(folder, f), f)
        docs.append(_doc(i, f, types[f.split("_")[0]], r.text, r.status, r.page_count))
    return docs


def _run_demo(scenario):
    a, b = generate(tempfile.mkdtemp())
    docs = _load(a if scenario == "a" else b)
    assert demo.is_demo_package(docs)
    proc = next(d for d in docs if d["document_type"] == "procedure")
    props, _ = pipeline.propose_requirements(proc, "demo")
    reqs = [{**p, "id": i} for i, p in enumerate(props, 1)]
    return docs, reqs, pipeline.verify(REVIEW, docs, reqs, "demo")


def test_demo_scenario_a_complete():
    docs, reqs, out = _run_demo("a")
    assert len(reqs) == 4 and sum(r["mandatory_status"] == "mandatory" for r in reqs) == 3
    assert all(r["source_page"] in (1, 2) for r in reqs)
    assert [r["status"] for r in out["results"]] == ["EVIDENCE_FOUND"] * 4
    assert out["overall_status"] == "DOCUMENTATION_COMPLETE"


def test_demo_scenario_b_missing_test_report():
    docs, reqs, out = _run_demo("b")
    by = {r["requirement_id"]: r for r in out["results"]}
    assert by[2]["status"] == "NOT_FOUND" and "not performed" in by[2]["explanation"]
    assert out["overall_status"] == "DOCUMENTATION_INCOMPLETE"


def test_demo_mode_refuses_real_documents():
    assert not demo.is_demo_package([_doc(1, "real.pdf", "procedure", "4.1 The operator SHALL do things.")])


def test_report_generation():
    docs, reqs, out = _run_demo("b")
    results = []
    for r in out["results"]:
        q = next(x for x in reqs if x["id"] == r["requirement_id"])
        results.append({**r, "description": q["description"], "source_quote": q["source_quote"],
                        "source_page": q["source_page"], "evidence_filename": next((d["filename"] for d in docs if d["id"] == r["evidence_document_id"]), None),
                        "source_filename": "Procedure_MP-017.pdf"})
    bundle = {"review": {"equipment_id": "P-101", "equipment_type": "Pump", "maintenance_description": "Seal",
                         "review_date": "2026-10-25", "notes": "", "overall_status": out["overall_status"],
                         "status_reasons": out["reasons"], "contradictions": out["contradictions"],
                         "analysis_notes": out["notes"], "analysis_mode": "demo", "is_demo": True},
              "documents": [{"filename": d["filename"], "document_type": d["document_type"], "extraction_status": d["extraction_status"], "page_count": d["page_count"]} for d in docs],
              "requirements": reqs, "results": results}
    pdf = build_report_pdf(bundle)
    assert pdf[:4] == b"%PDF" and len(pdf) > 2000
    p = os.path.join(TMP, "rep.pdf"); open(p, "wb").write(pdf)
    text = extraction.extract(p, "rep.pdf").text
    assert "SYNTHETIC" in text and "DOCUMENTATION INCOMPLETE" in text and "does not prove" in text
