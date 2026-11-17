# IT Ticket Classifier

Production-oriented AI agent: input is a ticket **description**, output is a **decision** — `database`, `security`, `network`, `it_infrastructure`, or `unclassified` (`POST /api/v1/decide`).

Built with **FastAPI**, **LangGraph**, **OpenAI Responses API**, and **Docling** for document extraction.

## Features

- `POST /api/v1/score` — scoring-only routing (one structured classify call; use for agents)
- `POST /api/v1/classify` — multipart ticket classification
- LangGraph `StateGraph` with conditional routing, bounded retries, and parallel attachment processing (`Send` fan-out)
- Parsers for PDF/DOCX/PPTX (Docling), XLSX/CSV, images (OpenAI vision), VSDX (XML), text/JSON/XML/YAML
- Structured JSON classification output with confidence, alternatives, and evidence
- Heuristic fallback when `OPENAI_API_KEY` is unset (for local tests)
- Security: file validation, signature checks, secret masking, prompt-injection-aware prompts

## Quick start (Docker)

```bash
cp .env.example .env
# Set OPENAI_API_KEY for live LLM classification
docker compose up --build
```

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

OpenAPI docs: http://localhost:8000/docs

## curl examples

Text only:

```bash
curl -X POST http://localhost:8000/api/v1/classify \
  -F "description=IPsec VPN tunnel is not working"
```

With metadata:

```bash
curl -X POST http://localhost:8000/api/v1/classify \
  -F "description=PostgreSQL replication failure" \
  -F "issue_key=SUP-101" \
  -F "client=ACME"
```

File upload:

```bash
curl -X POST http://localhost:8000/api/v1/classify \
  -F "files=@system.log"
```

Multiple attachments:

```bash
curl -X POST http://localhost:8000/api/v1/classify \
  -F "description=Investigate infrastructure issue" \
  -F "files=@network.vsdx" \
  -F "files=@error.pdf" \
  -F "files=@system.log"
```

Health:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/api/v1/functions
```

## Configuration

See `.env.example` for all settings (models, timeouts, upload limits, logging).

## Testing

```bash
ruff check app tests
pytest tests/unit tests/integration -q
python tests/evals/run_eval.py
```

Live OpenAI tests (optional):

```bash
OPENAI_API_KEY=sk-... pytest -m live_openai  # none shipped enabled by default
```

## Architecture

- `app/api` — REST layer
- `app/graph` — LangGraph workflow nodes and edges
- `app/parsers` — format-specific extraction
- `app/llm` — OpenAI client, prompts, structured schemas
- `app/services` — request orchestration and temp file lifecycle

Classification logic is transport-agnostic so a future Jira webhook adapter can call the same graph.

## Joey

Routing runs on Spark through the System One API, not through vLLM. Deploy and the reason the chat server returns noise: [docs/joey.md](docs/joey.md). The question the classifier sends, and how it compares with Baseten: [docs/baseten-joey-scoring.md](docs/baseten-joey-scoring.md).

## Known limitations (MVP)

- Legacy `.doc`, `.xls`, `.ppt`, `.vsd` require external conversion adapters (explicit failure today)
- Confidence scores are model estimates, not calibrated probabilities
- Docling first run may download models (cache in container image for production)
- Synchronous HTTP response; long-running jobs should use client timeouts ≤ `REQUEST_TIMEOUT_SECONDS`