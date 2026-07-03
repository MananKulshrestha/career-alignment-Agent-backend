# Career Alignment Agent Backend

FastAPI backend for the job ingestion, match filtering, and truthful resume-tailoring workflow described in `../final-project-workflow.md`.

## Stack

- FastAPI for the HTTP API.
- SQLModel over SQLAlchemy for ORM models.
- PostgreSQL through Supabase in production.
- Pydantic AI for structured LLM extraction, verification, matching, selection, and wording.
- Jinja2 HTML templates rendered to ATS-readable PDFs with WeasyPrint.

## Quick Start

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

The app defaults to a local SQLite database so development and tests are not blocked by API keys or Supabase credentials. For Supabase, set `DATABASE_URL` to the pooled Postgres connection string.

## Important Environment Variables

See `.env.example` for the full list.

- `DATABASE_URL`: Supabase Postgres URL.
- `OPENAI_API_KEY`: key used by Pydantic AI's OpenAI provider.
- `ENABLE_LLM`: set to `true` when API keys are available.
- `ARTIFACTS_DIR`: where HTML, PDF, and archival `.tex` resume artifacts are stored.

## Resume Rendering

Resume PDFs are rendered with Jinja2 HTML templates and WeasyPrint. A `resume.tex`
file is still written beside each PDF for archival/debugging, but no LaTeX engine
is used to render PDFs.

WeasyPrint requires native Pango/Cairo libraries. Verify the local environment with:

```powershell
python -m weasyprint --info
```

`LATEX_ENGINE` is kept only as legacy configuration and is not used by the
current renderer.

## API Surface

- `GET /health`
- `POST /api/v1/jobs/ingest`
- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `POST /api/v1/jobs/{job_id}/match`
- `POST /api/v1/jobs/maintenance/sweep-expired`
- `POST /api/v1/profiles/{user_id}/items`
- `GET /api/v1/profiles/{user_id}`
- `POST /api/v1/tailoring/sessions`
- `POST /api/v1/tailoring/sessions/{session_id}/approve-selection`
- `POST /api/v1/tailoring/sessions/{session_id}/generate`
- `POST /api/v1/tailoring/sessions/{session_id}/compile`
- `POST /api/v1/tailoring/sessions/{session_id}/approve-final`
- `GET /api/v1/tailoring/sessions/{session_id}/artifact/pdf`

## Development Checks

```powershell
pytest
ruff check .
ruff format --check .
```
