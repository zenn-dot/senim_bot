"""DEMO MODE - NOT LIVE AI ANALYSIS. Deterministic keyword rules that work only on the synthetic sample files
(they must contain the marker below). Real uploads never use this path."""
import re
from .ai import ReqProposal, MatchResult
from .grounding import norm

MARKER = "SYNTHETIC DEMO DATA"
STOP = {"shall", "should", "must", "that", "with", "after", "this", "from", "have", "been", "attached",
        "showing", "evidence", "contractor", "submit", "recorded"}
LINE_RE = re.compile(r"^\s*(\d+(?:\.\d+)+)\s+(.*)$")
TAG_RE = re.compile(
    r"\(Evidence:\s*([a-z_]+)\)",
    re.IGNORECASE
)


def is_demo_package(docs) -> bool:
    return bool(docs) and all(MARKER in (d.get("text") or "") for d in docs)


def demo_extract(proc_doc):
    out = []

    for page in (proc_doc.get("text") or "").split("\f"):
        for line in page.splitlines():
            m = LINE_RE.match(line)

            if not m:
                continue

            body = m.group(2).strip()
            up = body.upper()

            status = (
                "mandatory"
                if re.search(r"\b(SHALL|MUST)\b", up)
                else "optional"
                if re.search(r"\b(SHOULD|MAY)\b", up)
                else None
            )

            if status is None:
                continue

            # PDF extraction may cut off the Evidence tag.
            # Infer the expected type from the requirement wording.
            low = body.lower()

            if "repair completion report" in low:
                etype = "repair_report"
            elif "maintenance record" in low:
                etype = "maintenance_record"
            elif "leak test report" in low or "test report" in low:
                etype = "test_report"
            else:
                mm = TAG_RE.search(body)
                etype = mm.group(1).lower() if mm else "other"

            clean = TAG_RE.sub("", body).strip()

            out.append(
                ReqProposal(
                    description=clean,
                    mandatory_status=status,
                    source_quote=clean,
                    expected_evidence_type=etype,
                    confidence="high",
                    uncertainty="Demo rule: keyword SHALL/MUST/SHOULD/MAY.",
                )
            )

    return out


def _kw(text):
    return {w for w in re.findall(r"[a-z0-9\-]+", text.lower()) if len(w) >= 4 and w not in STOP}


def demo_match(req, candidates) -> MatchResult:
    pool = [d for d in candidates if d["document_type"] == req["expected_evidence_type"]] or []
    kws = _kw(req["description"])
    best = (0, None, None)
    for d in pool:
        for line in (d.get("text") or "").replace("\f", "\n").splitlines():
            score = len(kws & _kw(line))
            if score > best[0]:
                best = (score, d, line.strip())
    if best[1] is None or best[0] < max(2, int(len(kws) * 0.4)):
        return MatchResult(status="NOT_FOUND",
                           explanation="No supporting evidence was found in the uploaded package. "
                                       "This does not establish that the action was not performed.",
                           missing_evidence=f"A document of type '{req['expected_evidence_type']}' "
                                            "supporting this requirement.")
    _, d, line = best
    if re.search(r"\bFAIL", line, re.I):
        return MatchResult(status="MANUAL_REVIEW_REQUIRED", evidence_document_id=d["id"], evidence_quote=line,
                           explanation="Relevant text found but it indicates a failed result.",
                           uncertainty_reason="Failed or conflicting result; needs a specialist.")
    return MatchResult(status="EVIDENCE_FOUND", evidence_document_id=d["id"], evidence_quote=line,
                       explanation=f"Keyword match with the requirement in {d['filename']} (demo rule).")
