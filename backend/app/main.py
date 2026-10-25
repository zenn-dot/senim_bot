"""Senim Bot API. Checks documentary completeness only; never certifies equipment safety."""
import json, os, uuid
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

load_dotenv()
from . import database as db
from .schemas import ReviewIn, ExtractIn, RequirementsIn, DocTypeIn, DocType
from .services import ai, extraction, pipeline
from .services.report import build_report_pdf

MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_FILES_PER_REQUEST = 10
ALLOWED_EXT = {".pdf", ".docx"}
SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"

app = FastAPI(title="Senim Bot API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _startup():
    db.init_db()


def _review_or_404(conn, rid):
    r = db.get_review(conn, rid)
    if not r:
        raise HTTPException(404, "Review not found")
    return r


def _ai_http(e: ai.AIError):
    code = 503 if "not configured" in str(e) else 502
    return HTTPException(code, str(e))


def ingest_file(conn, rid, filename, data: bytes, doc_type="auto"):
    """Validate, store safely (uuid name, no user-supplied path) and extract one file."""
    safe_name = os.path.basename(filename or "unnamed")
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(415, f"{safe_name}: only PDF and DOCX files are supported.")
    if not data:
        raise HTTPException(400, f"{safe_name}: file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, f"{safe_name}: file exceeds {MAX_FILE_BYTES // 1024 // 1024} MB.")
    folder = Path(db.storage_dir()) / f"review_{rid}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(data)
    res = extraction.extract(path, safe_name)
    if doc_type in (None, "", "auto"):
        doc_type = extraction.classify_document(safe_name, res.text) if res.status == "ok" else "other"
    cur = conn.execute(
        "INSERT INTO documents(review_id,filename,document_type,storage_path,extraction_status,extraction_message,"
        "extracted_text,page_count,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (rid, safe_name, doc_type, str(path), res.status, res.message,
         res.text if res.status in ("ok",) else "", res.page_count, db.now()))
    return cur.lastrowid


def _touch(conn, rid, clear_results=False):
    if clear_results:
        conn.execute("DELETE FROM verification_results WHERE requirement_id IN "
                     "(SELECT id FROM requirements WHERE review_id=?)", (rid,))
        conn.execute("UPDATE reviews SET overall_status=NULL,status_reasons='[]',contradictions='[]',"
                     "analysis_notes='[]',analysis_mode=NULL WHERE id=?", (rid,))
    conn.execute("UPDATE reviews SET updated_at=? WHERE id=?", (db.now(), rid))


@app.get("/api/health")
def health():
    return {"status": "ok", "ai_configured": ai.gemini_configured(),
            "model": os.environ.get("GEMINI_MODEL") or None}


@app.post("/api/reviews", status_code=201)
def create_review(body: ReviewIn):
    with db.connect() as c:
        t = db.now()
        cur = c.execute("INSERT INTO reviews(equipment_id,equipment_type,maintenance_description,review_date,notes,"
                        "created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                        (body.equipment_id.strip(), body.equipment_type, body.maintenance_description,
                         body.review_date, body.notes, t, t))
        return db.review_bundle(c, cur.lastrowid)


@app.get("/api/reviews")
def list_reviews():
    with db.connect() as c:
        return db.rows(c, "SELECT id,equipment_id,equipment_type,review_date,overall_status,is_demo,created_at,"
                          "(SELECT COUNT(*) FROM documents d WHERE d.review_id=reviews.id) AS document_count "
                          "FROM reviews ORDER BY id DESC")


@app.get("/api/reviews/{review_id}")
def get_review(review_id: int):
    with db.connect() as c:
        b = db.review_bundle(c, review_id)
        if not b:
            raise HTTPException(404, "Review not found")
        return b


@app.post("/api/reviews/{review_id}/documents", status_code=201)
async def upload_documents(review_id: int, files: list[UploadFile] = File(...),
                           document_types: list[str] = Form(default=[])):
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(400, f"At most {MAX_FILES_PER_REQUEST} files per upload.")
    contents = [(f.filename, await f.read()) for f in files]
    with db.connect() as c:
        _review_or_404(c, review_id)
        for i, (name, data) in enumerate(contents):
            t = document_types[i] if i < len(document_types) else "auto"
            if t not in ("auto", "", *DocType.__args__):
                raise HTTPException(422, f"Unknown document type: {t}")
            ingest_file(c, review_id, name, data, t)
        _touch(c, review_id, clear_results=True)
        return db.review_bundle(c, review_id)


@app.patch("/api/reviews/{review_id}/documents/{doc_id}")
def set_doc_type(review_id: int, doc_id: int, body: DocTypeIn):
    with db.connect() as c:
        cur = c.execute("UPDATE documents SET document_type=? WHERE id=? AND review_id=?",
                        (body.document_type, doc_id, review_id))
        if not cur.rowcount:
            raise HTTPException(404, "Document not found in this review")
        return db.review_bundle(c, review_id)


@app.post("/api/reviews/{review_id}/requirements/extract")
def extract_requirements(review_id: int, body: ExtractIn):
    with db.connect() as c:
        _review_or_404(c, review_id)
        docs = db.get_documents(c, review_id)
        proc = next((d for d in docs if d["id"] == body.procedure_document_id), None)
        if not proc:
            raise HTTPException(404, "Procedure document not found in this review")
        try:
            mode = pipeline.choose_mode(docs)
            props, notes = pipeline.propose_requirements(proc, mode)
        except ai.AIError as e:
            raise _ai_http(e)
        c.execute("DELETE FROM requirements WHERE review_id=?", (review_id,))
        for p in props:
            c.execute("INSERT INTO requirements(review_id,description,mandatory_status,source_document_id,source_page,"
                      "source_quote,expected_evidence_type,confidence,uncertainty,approved_by_user) "
                      "VALUES(?,?,?,?,?,?,?,?,?,0)",
                      (review_id, p["description"], p["mandatory_status"], p["source_document_id"], p["source_page"],
                       p["source_quote"], p["expected_evidence_type"], p["confidence"], p["uncertainty"]))
        c.execute("UPDATE reviews SET analysis_notes=?, analysis_mode=? WHERE id=?",
                  (json.dumps(notes), mode, review_id))
        _touch(c, review_id, clear_results=True)
        c.execute("UPDATE reviews SET analysis_mode=?, analysis_notes=? WHERE id=?",
                  (mode, json.dumps(notes), review_id))
        return db.review_bundle(c, review_id)


@app.put("/api/reviews/{review_id}/requirements")
def save_requirements(review_id: int, body: RequirementsIn):
    with db.connect() as c:
        _review_or_404(c, review_id)
        valid_docs = {d["id"] for d in db.get_documents(c, review_id, with_text=False)}
        c.execute("DELETE FROM requirements WHERE review_id=?", (review_id,))
        for r in body.requirements:
            src = r.source_document_id if r.source_document_id in valid_docs else None
            c.execute("INSERT INTO requirements(review_id,description,mandatory_status,source_document_id,source_page,"
                      "source_quote,expected_evidence_type,confidence,uncertainty,approved_by_user) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (review_id, r.description, r.mandatory_status, src, r.source_page, r.source_quote,
                       r.expected_evidence_type, r.confidence, r.uncertainty, int(r.approved_by_user)))
        _touch(c, review_id, clear_results=True)
        return db.review_bundle(c, review_id)


@app.post("/api/reviews/{review_id}/verify")
def verify(review_id: int):
    with db.connect() as c:
        review = _review_or_404(c, review_id)
        docs = db.get_documents(c, review_id)
        reqs = [r for r in db.get_requirements(c, review_id) if r["approved_by_user"]]
        if not reqs:
            raise HTTPException(409, "Approve at least one requirement before verification.")
        try:
            mode = pipeline.choose_mode(docs)
            out = pipeline.verify(review, docs, reqs, mode)
        except ai.AIError as e:
            raise _ai_http(e)   # nothing is saved: no fabricated result after an AI failure
        c.execute("DELETE FROM verification_results WHERE requirement_id IN "
                  "(SELECT id FROM requirements WHERE review_id=?)", (review_id,))
        for r in out["results"]:
            c.execute("INSERT INTO verification_results(requirement_id,status,evidence_document_id,evidence_page,"
                      "evidence_quote,explanation,missing_evidence,uncertainty_reason,created_at) "
                      "VALUES(?,?,?,?,?,?,?,?,?)",
                      (r["requirement_id"], r["status"], r["evidence_document_id"], r["evidence_page"],
                       r["evidence_quote"], r["explanation"], r["missing_evidence"], r["uncertainty_reason"], db.now()))
        c.execute("UPDATE reviews SET overall_status=?,status_reasons=?,contradictions=?,analysis_notes=?,"
                  "analysis_mode=?,updated_at=? WHERE id=?",
                  (out["overall_status"], json.dumps(out["reasons"]), json.dumps(out["contradictions"]),
                   json.dumps(out["notes"]), mode, db.now(), review_id))
        return db.review_bundle(c, review_id)


@app.get("/api/reviews/{review_id}/report")
def report(review_id: int):
    with db.connect() as c:
        b = db.review_bundle(c, review_id)
        if not b:
            raise HTTPException(404, "Review not found")
        if not b["review"]["overall_status"]:
            raise HTTPException(409, "Run verification before generating a report.")
        return b


@app.get("/api/reviews/{review_id}/report/download")
def report_download(review_id: int):
    b = report(review_id)
    pdf = build_report_pdf(b)
    name = f"senim-report-{b['review']['equipment_id']}-{review_id}.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.post("/api/demo/{scenario}", status_code=201)
def create_demo(scenario: str):
    if scenario not in ("a", "b"):
        raise HTTPException(404, "Scenario must be 'a' or 'b'")
    from sample_data.generate_samples import generate
    generate(str(SAMPLE_DIR))
    folder = SAMPLE_DIR / f"scenario_{scenario}"
    names = {"Procedure": "procedure", "Repair": "repair_report", "Leak": "test_report", "Maintenance": "maintenance_record"}
    label = "A - evidence available" if scenario == "a" else "B - leak test report missing"
    with db.connect() as c:
        t = db.now()
        cur = c.execute("INSERT INTO reviews(equipment_id,equipment_type,maintenance_description,review_date,notes,"
                        "is_demo,created_at,updated_at) VALUES('P-101','Centrifugal pump','Mechanical seal replacement',"
                        "'2026-10-25',?,1,?,?)", (f"SYNTHETIC DEMO DATA - scenario {label}", t, t))
        rid = cur.lastrowid
        for f in sorted(folder.iterdir()):
            ingest_file(c, rid, f.name, f.read_bytes(), names[f.name.split("_")[0]])
        return db.review_bundle(c, rid)
