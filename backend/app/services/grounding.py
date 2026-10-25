"""Quote grounding: every quotation shown to the user must exist in the extracted source text."""
import re

ID_RE = re.compile(r"\b[A-Z]{1,3}-\d{2,4}[A-Z]?\b")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def doc_pages(doc: dict) -> list:
    return (doc.get("text") or "").split("\f")


def find_quote(quote: str, doc: dict):
    """Returns (found, page). page is None when the doc has no page numbers or the quote spans pages."""
    q = norm(quote)
    if len(q) < 5:
        return False, None
    pages = doc_pages(doc)
    known = doc.get("page_count") is not None
    for i, p in enumerate(pages, 1):
        if q in norm(p):
            return True, (i if known else None)
    if q in norm(" ".join(pages)):
        return True, None
    return False, None


def detect_id_contradictions(equipment_id: str, docs: list) -> list:
    """Deterministic check: evidence documents mentioning a different equipment ID."""
    out = []
    for d in docs:
        if d.get("extraction_status") != "ok":
            continue
        ids = set(ID_RE.findall(d.get("text") or ""))
        others = sorted(i for i in ids if i != equipment_id)
        if others:
            tail = "" if equipment_id in ids else f" and does not mention {equipment_id}"
            out.append({"kind": "equipment_id", "document": d["filename"],
                        "description": f"{d['filename']} mentions {', '.join(others)}{tail}; "
                                       f"this review is for {equipment_id}."})
    return out
