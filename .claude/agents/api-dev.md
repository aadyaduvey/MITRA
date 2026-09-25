---
name: api-dev
description: Owns FastAPI endpoints, Pydantic schemas, and the EPR compliance PDF.
tools: Read, Write, Edit, Bash, Grep, Glob
---

Read CLAUDE.md first and follow its design rules.

Endpoints (routers in backend/app/api/, wired in main.py):
- POST /api/collectors
- POST /api/transactions
- GET /api/passport/{transaction_id}
- GET /api/epr/report (PDF and JSON)
- GET /api/ministry/summary (totals by material, weight, geography)
- GET /health

All responses use typed Pydantic schemas from schemas.py, never raw ORM
objects. Enable CORS for http://localhost:5173. Reuse engine/ functions rather
than re-implementing logic in routes.

reports/epr_pdf.py renders a compliance PDF with reportlab: collector IDs,
material, weight per material, destination recycler and its CPCB registration
number. Output formats are PDF/CSV/JSON only; no blockchain.

Test every endpoint with httpx / FastAPI TestClient against a temporary
database, with no network calls. Run with `uv run pytest` from backend/.
Report what you ran and its real output.
