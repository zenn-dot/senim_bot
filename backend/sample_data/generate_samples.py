"""Generates fictional SYNTHETIC DEMO DATA files for pump P-101 into sample_data/scenario_a and scenario_b."""
import os
import docx
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

HERE = os.path.dirname(os.path.abspath(__file__))
BANNER = "SYNTHETIC DEMO DATA - FICTIONAL DOCUMENT, NOT REAL"


def make_pdf(path, pages):
    c = canvas.Canvas(path, pagesize=A4)
    for lines in pages:
        y = 800
        for ln in [BANNER, ""] + lines:
            c.drawString(50, y, ln)
            y -= 18
        c.showPage()
    c.save()


def make_docx(path, lines):
    d = docx.Document()
    for ln in [BANNER, ""] + lines:
        d.add_paragraph(ln)
    d.save(path)


def generate(base=HERE):
    a, b = os.path.join(base, "scenario_a"), os.path.join(base, "scenario_b")
    os.makedirs(a, exist_ok=True); os.makedirs(b, exist_ok=True)
    make_pdf(os.path.join(a, "Procedure_MP-017.pdf"), [
        ["Internal Maintenance Procedure MP-017 - Return to operation of centrifugal pumps",
         "4.1 After mechanical seal replacement the contractor SHALL submit a repair completion report signed by the maintenance supervisor. (Evidence: repair_report)",
         "4.2 A post-repair leak test report SHALL be attached showing the leak test result and test pressure. (Evidence: test_report)"],
        ["4.3 The maintenance record for the equipment SHALL be updated with the date of mechanical seal replacement. (Evidence: maintenance_record)",
         "4.4 A vibration reading after repair SHOULD be recorded in the test report. (Evidence: test_report)"]])
    make_docx(os.path.join(a, "Repair_Completion_Report_P-101.docx"), [
        "Repair Completion Report", "Equipment: P-101 (centrifugal pump)",
        "Work performed: mechanical seal replacement completed on 2026-10-12.",
        "Repair completion report signed by the maintenance supervisor: A. Example (fictional)."])
    make_pdf(os.path.join(a, "Leak_Test_Report_P-101.pdf"), [[
        "Post-Repair Leak Test Report", "Equipment: P-101",
        "Leak test result: PASS. Test pressure: 6.0 bar (fictional value).",
        "Vibration reading after repair: 2.1 mm/s (fictional value)."]])
    make_docx(os.path.join(a, "Maintenance_Record_P-101.docx"), [
        "Maintenance Record - P-101",
        "Maintenance record entry: mechanical seal replacement date 2026-10-12 recorded for P-101."])
    # Scenario B = same package without the leak test report
    for f in ("Procedure_MP-017.pdf", "Repair_Completion_Report_P-101.docx", "Maintenance_Record_P-101.docx"):
        with open(os.path.join(a, f), "rb") as s, open(os.path.join(b, f), "wb") as t:
            t.write(s.read())
    return a, b


if __name__ == "__main__":
    print(generate())
