# ERCA&RIS — Enterprise Root Cause Analysis & Recommendation Intelligence System

A production-style AI-powered Incident RCA and Auto-Remediation platform.

```
Demo/Main Application (Flask :5000)
        v
Incident Detection & Creation
        v
Database (SQLite by default / Postgres+pgvector optional)
        v
RAG Historical Incident Retrieval
        v
Code Intelligence (AST scan) + CODEOWNERS Ownership
        v
RCA Engine (structured JSON, evidence-based confidence)
        v
Developer Assignment + Notification (email / Slack / GitHub)
        v
Patch Generation -> Branch -> Tests -> GitHub PR
        v
Developer Approval -> Merge -> Resolved
        v
Resolved incident indexed back into RAG knowledge
```

The ERCA&RIS backend (FastAPI) runs on **http://127.0.0.1:5001**.
The demo application (Flask) runs on **http://127.0.0.1:5000**.

---

## 1. Project layout

```
app/                        FastAPI backend ("ERCA&RIS v2")
  config.py                 env-driven settings (SQLite by default)
  db/                       SQLAlchemy models (8 tables) + additive migrations + init
  schemas.py                Pydantic request/response models
  rag/                      embeddings, vector_store, retriever, indexer, rag_service
  code_intelligence/        AST scanner + CODEOWNERS resolver
  rca/                      LLM provider abstraction + RCA engine
  remediation/               patch_generator, fixer, test_runner, github_client, pr_service
  notifications/            email, Slack, unified notifier
  services/incident_service.py   full lifecycle orchestrator
  api/                      FastAPI routers (health, incidents, rag)
  main.py                   FastAPI app entrypoint (CORS, lifespan, dashboard route)

erca_ris/                   legacy prototype (kept for reference) + new launcher
  api.py                    `python -m erca_ris.api` -> runs app.main:app on :5001
  templates/dashboard.html  new incident dashboard (served by the FastAPI app)
  store.py, incident_analysis.py, code_analysis.py, ...   legacy JSON-file prototype,
                             superseded by app/ but left in place per "don't remove
                             existing functionality" -- not used by the new startup path.

sample_app/                 Flask demo application (unchanged failure scenarios)
repositories/repo/CODEOWNERS + developer_roster.json (demo identity mapping)
scripts/                    init_db.py, seed_data.py, index_rag.py
tests/                      pytest suite (33 tests + 1 dependency-conditional skip)
docker-compose.yml, Dockerfile.backend, Dockerfile.demo
.env.example
```

## 2. Why the old `python erca_ris/api.py` bug is fixed

The demo previously failed because `erca_ris/api.py` didn't exist / was executed as a
loose script instead of a package, breaking `from erca_ris.incident_analysis import ...`.
`erca_ris/api.py` is now a proper module with `__init__.py`s throughout, and simply
launches the new FastAPI app:

```bash
python -m erca_ris.api                 # recommended
# or, for auto-reload during development:
uvicorn app.main:app --reload --port 5001
```

## 3. Setup

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # edit if you have real credentials; all optional
```

By default `DATABASE_URL` is unset, which means **SQLite** is used automatically
(`runtime/erca_ris.db`) — zero external setup required. To use PostgreSQL+pgvector
instead, set in `.env`:

```
DATABASE_URL=postgresql+psycopg2://erca:erca@localhost:5432/erca_ris
```

and enable the `postgres` service in `docker-compose.yml` (commented out by default).
The RAG layer works identically either way — vector similarity is computed in Python
on SQLite, or can use pgvector natively on Postgres.

## 4. Database setup

```bash
python -m scripts.init_db      # creates all 8 tables
```

## 5. Seed data (10+ historical incidents)

```bash
python -m scripts.seed_data
```

This creates 10 RESOLVED historical incidents (payment timeout, auth failure, DB pool
exhaustion, inventory unavailable, email provider outage, search timeout, storage
outage, report query timeout, plus 2 variants) and immediately indexes each one into
the RAG knowledge base via `app/rag/indexer.py`.

## 6. RAG indexing (re-index on demand)

```bash
python -m scripts.index_rag    # re-embeds every RESOLVED incident currently in the DB
```

Useful after switching `EMBEDDING_PROVIDER` (offline <-> openai) so vectors stay
consistent.

## 7. Start the backend

```bash
python -m erca_ris.api
# backend now listening on http://127.0.0.1:5001
# dashboard: http://127.0.0.1:5001/
```

## 8. Start the demo application

```bash
python -m sample_app.app
# demo now listening on http://127.0.0.1:5000
```

## 9. Health check

```bash
curl http://127.0.0.1:5001/api/health
```

```json
{"status":"ok","service":"ERCA&RIS","environment":"development",
 "database":"sqlite","llm_provider":"auto","github_integration":false}
```

## 10. Create an incident directly

```bash
curl -X POST http://127.0.0.1:5001/api/incidents \
  -H "Content-Type: application/json" \
  -d '{"service":"Payment Service","scenario":"payment",
       "error_message":"Payment gateway connection timed out",
       "environment":"production","severity":"HIGH","priority":"P2"}'
```

Creation automatically runs the full analysis pipeline (RAG + code intelligence +
RCA) and returns the complete incident record, e.g.:

```json
{
  "incident_id": "INC-20260817-FAB9",
  "status": "ASSIGNED",
  "analysis": {
    "root_cause": "Downstream payment gateway introduced excessive latency, exceeding the configured client timeout.",
    "confidence": 0.88,
    "agreement_ratio": 0.32,
    "analysis_status": "HIGH",
    "recommended_resolution": "Validate the downstream dependency, correct timeout/configuration conditions, then replay the affected workload.",
    "recommended_prevention": "Add dependency latency monitoring, timeout alerts, and integration/recovery tests."
  },
  "ownership": {
    "owner": "Payment Team", "team": "@payment-team",
    "developer": "Payment Service Developer",
    "file_path": "sample_app/services/payment/payment_service.py",
    "function_name": "process_payment", "line_number": 5
  },
  "evidence": [
    {"source_type": "code", "content": "raise TimeoutError(\"Payment gateway connection timed out\")"},
    {"source_type": "rag_history", "source_reference": "INC-20260817-7D86", "similarity_score": 0.6092}
  ]
}
```

## 11. Trigger a payment failure via the demo app

```bash
curl -X POST http://127.0.0.1:5000/api/demo/payment
```

The demo app captures the exception, POSTs it to `/api/incidents` on the backend,
and returns the full ERCA&RIS result alongside its own error payload. Open
http://127.0.0.1:5000 in a browser and click **Payment** to see it rendered live,
with a link into the incident on the dashboard.

## 12. How RAG works

* Every RESOLVED incident is converted into a structured knowledge document
  (`app/rag/indexer.py: build_knowledge_text`) and embedded
  (`app/rag/embeddings.py`).
* Embeddings default to an **offline, dependency-light hashing vectorizer**
  (`sklearn.HashingVectorizer`, 256-dim, L2-normalized) so semantic search works
  with zero network access. Set `OPENAI_API_KEY` to switch to real OpenAI
  embeddings automatically (`EMBEDDING_PROVIDER=auto`).
* New incidents are embedded the same way and compared via cosine similarity
  against every stored knowledge document (`app/rag/vector_store.py`).
* The top-K matches become **evidence** for the RCA engine, and the single best
  match is checked against `RAG_KNOWN_INCIDENT_THRESHOLD` (default 0.92) to
  surface a **KNOWN INCIDENT** banner — the system still performs a fresh RCA
  regardless.

## 13. How developer notification works

`app/notifications/notifier.py` formats the incident (root cause, confidence,
file/function/line, owner, developer, PR link) into the exact message format from
the spec and dispatches to:

* **Email** — real SMTP if `SMTP_HOST`/`SMTP_USERNAME`/`SMTP_PASSWORD` are set,
  otherwise logs and records a `MOCKED` notification.
* **Slack** — real webhook if `SLACK_WEBHOOK_URL` is set, otherwise `MOCKED`.
* **GitHub** — comments the RCA summary on the PR if GitHub integration is live.

Every dispatch is persisted to the `notifications` table regardless of mode.

## 14. How GitHub PR creation works

`app/remediation/github_client.py` wraps PyGithub. If `GITHUB_TOKEN` and
`GITHUB_REPOSITORY` are set, it really creates a branch, commits the patch file,
opens a PR against `GITHUB_BASE_BRANCH` (default `main`), adds labels, assigns the
resolved developer, and comments the RCA summary. If no credentials are configured,
every call returns a clearly-labeled `mocked: true` response so the full pipeline
(and the dashboard) still works end-to-end. **Nothing is ever pushed to
main/master** — only a dedicated `erca-ris/fix-<incident-id>` branch + PR, and merge
always requires manual developer approval on GitHub.

## 15. How resolved incidents become RAG knowledge

`POST /api/incidents/{id}/resolve` calls `incident_service.resolve_incident`, which:
1. Marks the incident `RESOLVED` and stamps `resolved_at`.
2. Persists the `RESOLVED` state transition.
3. Calls `rag.indexer.index_resolved_incident`, which builds the structured
   knowledge document (incident, root cause, resolution, prevention, code, owner,
   developer, PR, test result), embeds it, and stores it in `knowledge_documents`.

From that point on, any new incident's RAG retrieval step
(`app/rag/rag_service.get_historical_evidence`) can find and use it.

## 16. Example incident lifecycle

```
OPEN -> ANALYZING -> RCA_READY -> ASSIGNED -> FIX_GENERATED -> TESTING
     -> PR_CREATED -> WAITING_FOR_APPROVAL -> RESOLVED
```

Every transition is persisted to `incident_transitions` and visible via
`GET /api/incidents/{id}/timeline`.

## 17. Frontend and operational views

The FastAPI dashboard at `http://127.0.0.1:5001/` now includes: Dashboard, Incidents, RCA Analysis, RAG Historical Knowledge, Code Intelligence, Ownership & Developers, Remediation, Pull Requests, Notifications, Analytics, Reports and Settings. The UI is dependency-free (HTML/CSS/JavaScript) so it works without a separate frontend build step.

The dashboard also exposes incident creation, RAG search, code snippets, notification history, CSV reporting, remediation actions and lifecycle timeline in one place.

## 18. API reference

```
GET  /api/health
POST /api/incidents                          create + auto-analyze
GET  /api/incidents
GET  /api/incidents/{id}
POST /api/incidents/{id}/analyze
GET  /api/incidents/{id}/evidence
GET  /api/incidents/{id}/ownership
POST /api/incidents/{id}/remediation          generate patch + branch
POST /api/incidents/{id}/tests                pytest + lint + security scan
POST /api/incidents/{id}/github-pr
POST /api/incidents/{id}/notify               body: {"channels": ["email","slack","github"]}
POST /api/incidents/{id}/resolve
GET  /api/incidents/{id}/timeline
GET  /api/incidents/{id}/code
GET  /api/incidents/{id}/notifications
GET  /api/analytics/summary
GET  /api/analytics/timeseries
GET  /api/ownership
GET  /api/remediation
GET  /api/pull-requests
GET  /api/notifications
GET  /api/reports/incidents.csv
POST /api/rag/search                          body: {"query": "...", "top_k": 5}
POST /api/rag/index                           body: {"document": "...", "metadata": {}}
```

## 19. Running tests

```bash
pytest tests -q
```

33 tests covering: incident creation, lifecycle transitions, code intelligence (AST
matching), CODEOWNERS resolution, RAG retrieval, RCA confidence scoring, new
(unknown) incident handling, resolved-incident indexing, remediation patch
generation, GitHub integration (mocked), notifications (mocked), and all API
endpoints.

Note: the `/api/incidents/{id}/tests` endpoint itself runs this full suite as part
of the remediation workflow, which takes ~2-3 minutes since it's a real pytest
invocation, not a shortcut.

## 20. Docker

```bash
docker compose up --build
```

Starts the backend (`:5001`) and demo app (`:5000`) against SQLite by default
(shared named volume for `runtime/`). Uncomment the `postgres` service in
`docker-compose.yml` and set `DATABASE_URL` in `.env` to use Postgres+pgvector
instead.

## 21. Safety guarantees

* No automated commit ever targets `main`/`master` — only `erca-ris/fix-<id>` branches.
* CODEOWNERS remains the authoritative team/path ownership signal; a current developer username/email is resolved from the configured roster or connected SCM where available.
* Demo identities are intentionally fake (`*@example.com`) and must be replaced with real organization identities before enabling live notifications.
* No source file is silently modified — patches are generated as reviewable diffs
  and written to `remediation_patches/<incident_id>.patch`.
* No destructive commands, no `.env` files committed, no secrets logged.
* Every remediation requires a GitHub PR + human review before merge.
* CORS is restricted to explicit origins (`ALLOWED_ORIGINS`), never `*`.
