"""Deterministic overall-status calculation. Plain Python: the language model never decides this."""
EVIDENCE_FOUND = "EVIDENCE_FOUND"
NOT_FOUND = "NOT_FOUND"
MANUAL_REVIEW = "MANUAL_REVIEW_REQUIRED"

COMPLETE = "DOCUMENTATION_COMPLETE"
INCOMPLETE = "DOCUMENTATION_INCOMPLETE"
REVIEW = "MANUAL_REVIEW_REQUIRED"


def calculate_overall_status(results, contradictions=(), extraction_problems=()):
    """results: dicts with 'mandatory_status' and 'status'. Returns (status, reasons[])."""
    reasons = []
    if not results:
        return REVIEW, ["No approved requirements were verified."]

    mandatory = [r for r in results if r["mandatory_status"] == "mandatory"]
    missing = [r for r in mandatory if r["status"] == NOT_FOUND]
    review_items = [r for r in results if r["status"] == MANUAL_REVIEW]
    unclear_missing = [r for r in results
                       if r["mandatory_status"] == "unclear" and r["status"] == NOT_FOUND]

    if missing:
        reasons.append(f"{len(missing)} mandatory requirement(s) have no supporting evidence in the uploaded package.")
    if review_items:
        reasons.append(f"{len(review_items)} requirement(s) need manual review.")
    if unclear_missing:
        reasons.append(f"{len(unclear_missing)} requirement(s) of unclear mandatory status have no evidence.")
    if contradictions:
        reasons.append(f"{len(contradictions)} contradiction(s) detected between documents.")
    if extraction_problems:
        reasons.append(f"{len(extraction_problems)} document(s) could not be fully read.")
    if not mandatory:
        reasons.append("No mandatory requirements are configured.")

    if missing:                       # takes priority, other issues stay listed in reasons
        return INCOMPLETE, reasons
    if reasons:
        return REVIEW, reasons
    return COMPLETE, ["All mandatory requirements have supporting evidence. Human review is still required."]
