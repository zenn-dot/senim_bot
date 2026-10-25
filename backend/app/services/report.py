"""PDF report generation with reportlab. Input is the dict returned by database.review_bundle()."""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

DISCLAIMER = ("Senim Bot checks the availability and consistency of documentary evidence only. It does not "
              "certify equipment safety or authorize operation. Final decisions must be made by a qualified, "
              "authorized specialist.")
LABELS = {"DOCUMENTATION_COMPLETE": "DOCUMENTATION COMPLETE - HUMAN REVIEW REQUIRED",
          "DOCUMENTATION_INCOMPLETE": "DOCUMENTATION INCOMPLETE",
          "MANUAL_REVIEW_REQUIRED": "MANUAL REVIEW REQUIRED",
          "EVIDENCE_FOUND": "EVIDENCE FOUND", "NOT_FOUND": "NOT FOUND"}


def _p(text, style):
    return Paragraph(escape(str(text if text is not None else "")), style)


def build_report_pdf(bundle: dict) -> bytes:
    rev, docs, results = bundle["review"], bundle["documents"], bundle["results"]
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9, leading=11)
    small = ParagraphStyle("s", parent=body, fontSize=8, leading=10)
    h = ParagraphStyle("h", parent=ss["Heading2"], textColor=colors.HexColor("#0B1F3A"))
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36,
                            title=f"Senim Bot report {rev['equipment_id']}")
    s = [Paragraph("Senim Bot - Documentary Verification Report", ss["Title"])]
    if rev["is_demo"]:
        s.append(_p("SYNTHETIC DEMONSTRATION - fictional data. DEMO MODE - NOT LIVE AI ANALYSIS.",
                    ParagraphStyle("d", parent=body, textColor=colors.red, fontSize=10)))
    s += [Spacer(1, 6), _p(DISCLAIMER, ParagraphStyle("x", parent=body, backColor=colors.HexColor("#FFF4D6"),
                                                         borderPadding=6)), Spacer(1, 10)]
    s.append(Paragraph("Overall documentary status", h))
    s.append(_p(LABELS.get(rev["overall_status"], rev["overall_status"] or "NOT VERIFIED"), ss["Heading3"]))
    for r in rev["status_reasons"]:
        s.append(_p("- " + r, body))
    s.append(Paragraph("Equipment", h))
    for k, v in [("Equipment ID", rev["equipment_id"]), ("Type", rev["equipment_type"]),
                 ("Maintenance", rev["maintenance_description"]), ("Review date", rev["review_date"]),
                 ("Notes", rev["notes"]), ("Analysis mode", rev["analysis_mode"])]:
        s.append(_p(f"{k}: {v or '-'}", body))

    s.append(Paragraph("Uploaded documents", h))
    s.append(_table([["File", "Category", "Extraction", "Pages"]] +
                    [[d["filename"], d["document_type"], d["extraction_status"],
                      d["page_count"] if d["page_count"] is not None else "n/a"] for d in docs], small))

    def section(title, items, fn):
        s.append(Paragraph(title, h))
        if not items:
            s.append(_p("None.", body))
        for it in items:
            s.extend(fn(it))

    def evid(r):
        pg = f"page {r['evidence_page']}" if r["evidence_page"] else "Page unavailable"
        return [_p(f"{r['description']} [{r['mandatory_status']}]", body),
                _p(f"Source: {r['evidence_filename']}, {pg}", small),
                _p(f"Quotation: \"{r['evidence_quote']}\"", small), _p(r["explanation"], small), Spacer(1, 4)]

    def miss(r):
        return [_p(f"{r['description']} [{r['mandatory_status']}]", body),
                _p(f"Procedure quotation: \"{r['source_quote']}\" ({r['source_filename']}, "
                   f"{'page ' + str(r['source_page']) if r['source_page'] else 'Page unavailable'})", small),
                _p(f"Missing: {r['missing_evidence'] or r['explanation']}", small), Spacer(1, 4)]

    def man(r):
        return [_p(f"{r['description']} [{r['mandatory_status']}]", body),
                _p(f"Reason: {r['uncertainty_reason'] or r['explanation']}", small),
                _p(f"Quotation: \"{r['evidence_quote']}\"" if r["evidence_quote"] else "No quotation.", small),
                Spacer(1, 4)]

    s.append(Paragraph("Requirements evaluated", h))
    s.append(_table([["Requirement", "Mandatory", "Status"]] +
                    [[r["description"], r["mandatory_status"], LABELS[r["status"]] if r["status"] in LABELS
                      else "MANUAL REVIEW REQUIRED"] for r in results], small))
    section("Evidence found", [r for r in results if r["status"] == "EVIDENCE_FOUND"], evid)
    section("Missing evidence (not found in the uploaded package; this does not prove the action did not happen)",
            [r for r in results if r["status"] == "NOT_FOUND"], miss)
    section("Items requiring manual review", [r for r in results if r["status"] == "MANUAL_REVIEW_REQUIRED"], man)
    section("Detected contradictions", rev["contradictions"], lambda c: [_p("- " + c["description"], body)])
    if rev["analysis_notes"]:
        section("Processing notes", rev["analysis_notes"], lambda n: [_p("- " + n, body)])
    s += [Spacer(1, 12), _p(DISCLAIMER, small)]
    doc.build(s)
    return buf.getvalue()


def _table(data, style):
    t = Table([[_p(c, style) for c in row] for row in data], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6F5")),
                           ("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t
