"""SQLite persistence (stdlib sqlite3). Path comes from SENIM_DB, files from SENIM_STORAGE."""
import json, os, sqlite3
from datetime import datetime, timezone

DOC_TYPES = ("procedure", "repair_report", "test_report", "work_permit", "maintenance_record", "other")
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS reviews(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  equipment_id TEXT NOT NULL CHECK(length(equipment_id) > 0),
  equipment_type TEXT NOT NULL,
  maintenance_description TEXT NOT NULL,
  review_date TEXT NOT NULL,
  notes TEXT DEFAULT '',
  overall_status TEXT,
  status_reasons TEXT DEFAULT '[]',
  contradictions TEXT DEFAULT '[]',
  analysis_notes TEXT DEFAULT '[]',
  analysis_mode TEXT,
  is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  review_id INTEGER NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  document_type TEXT NOT NULL CHECK(document_type IN {DOC_TYPES}),
  storage_path TEXT NOT NULL,
  extraction_status TEXT NOT NULL CHECK(extraction_status IN ('ok','empty','scanned','failed')),
  extraction_message TEXT DEFAULT '',
  extracted_text TEXT DEFAULT '',
  page_count INTEGER,
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS requirements(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  review_id INTEGER NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
  description TEXT NOT NULL,
  mandatory_status TEXT NOT NULL CHECK(mandatory_status IN ('mandatory','optional','unclear')),
  source_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
  source_page INTEGER, source_quote TEXT DEFAULT '',
  expected_evidence_type TEXT DEFAULT 'other',
  confidence TEXT DEFAULT 'medium', uncertainty TEXT DEFAULT '',
  approved_by_user INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS verification_results(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  requirement_id INTEGER NOT NULL REFERENCES requirements(id) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK(status IN ('EVIDENCE_FOUND','NOT_FOUND','MANUAL_REVIEW_REQUIRED')),
  evidence_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
  evidence_page INTEGER, evidence_quote TEXT,
  explanation TEXT, missing_evidence TEXT, uncertainty_reason TEXT,
  created_at TEXT NOT NULL);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def storage_dir():
    p = os.environ.get("SENIM_STORAGE", "storage")
    os.makedirs(p, exist_ok=True)
    return p


def connect():
    path = os.environ.get("SENIM_DB", "senim.db")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with connect() as c:
        c.executescript(SCHEMA)


def rows(conn, sql, args=()):
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def get_review(conn, rid):
    r = rows(conn, "SELECT * FROM reviews WHERE id=?", (rid,))
    return r[0] if r else None


def get_documents(conn, rid, with_text=True):
    cols = "*" if with_text else "id,review_id,filename,document_type,extraction_status,extraction_message,page_count,created_at"
    out = rows(conn, f"SELECT {cols} FROM documents WHERE review_id=? ORDER BY id", (rid,))
    if with_text:
        for d in out:
            d["text"] = d.get("extracted_text") or ""
    return out


def get_requirements(conn, rid):
    return rows(conn, "SELECT * FROM requirements WHERE review_id=? ORDER BY id", (rid,))


def get_results(conn, rid):
    return rows(conn, """SELECT v.*, r.description, r.mandatory_status, r.source_quote, r.source_page,
        r.source_document_id, d.filename AS evidence_filename, sd.filename AS source_filename
        FROM verification_results v JOIN requirements r ON r.id=v.requirement_id
        LEFT JOIN documents d ON d.id=v.evidence_document_id
        LEFT JOIN documents sd ON sd.id=r.source_document_id
        WHERE r.review_id=? ORDER BY r.id""", (rid,))


def review_bundle(conn, rid):
    rev = get_review(conn, rid)
    if not rev:
        return None
    for k in ("status_reasons", "contradictions", "analysis_notes"):
        rev[k] = json.loads(rev.get(k) or "[]")
    rev["is_demo"] = bool(rev["is_demo"])
    return {"review": rev, "documents": get_documents(conn, rid, with_text=False),
            "requirements": get_requirements(conn, rid), "results": get_results(conn, rid)}
