# Senim Bot

AI-assisted **documentary completeness** check before industrial equipment returns to operation after repair.
It does **not** certify safety or authorize startup; a qualified specialist decides.

Flow: create review → upload PDF/DOCX → extract requirements from the procedure → edit/approve → verify → evidence viewer → PDF report.

## Run the backend (Python 3.10+)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # optional for demo mode
uvicorn app.main:app --reload --port 8000
```
## Run the frontend (Node 18+)
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api to :8000)
npm run build      # production build
```
## Gemini
Edit `backend/.env`: `GEMINI_API_KEY=...` and `GEMINI_MODEL=<a model name your key supports>`; restart the backend.
The key stays on the server. Check **Settings / API** in the UI.

## Demo without an API key
Dashboard → "Scenario A" or "Scenario B". Fictional files marked SYNTHETIC DEMO DATA are generated into
`backend/sample_data/` and pass through the real extraction pipeline. Analysis uses deterministic keyword rules
labeled **DEMO MODE — NOT LIVE AI ANALYSIS**, and only works when *every* file in the review carries the synthetic marker.

## Tests
```bash
cd backend && python -m pytest app/tests -q
```
## Design notes
- Statuses are computed in `services/status.py` (plain Python), never by the model.
- Every quotation is checked against extracted text (`services/grounding.py`); unverifiable quotes become MANUAL REVIEW.
- AI failure/invalid JSON → HTTP 502, nothing saved. Scanned PDFs: no OCR, flagged as not analyzed.
- Documents over 60,000 characters are truncated for the model and this is reported.

## Known limitations
No OCR; DOCX has no page numbers ("Page unavailable"); document-version and date contradictions rely on the model
(only equipment-ID conflicts are checked deterministically); document classification is a keyword heuristic; no auth.
