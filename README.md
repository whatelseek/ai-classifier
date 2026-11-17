# IT Ticket Classifier

A ticket **description** in, a **decision** out: `database`, `security`, `network`, `it_infrastructure`, or `unclassified`.

Joey (`baselabs/joey-1`) answers through the System One API. On Spark that is `services/joey-qev-server` (port 8003). Why a chat server cannot serve this model, and how to deploy it: [docs/joey.md](docs/joey.md). The question it is asked, and the measured accuracy: [docs/baseten-joey-scoring.md](docs/baseten-joey-scoring.md).

## API

`POST /api/v1/decide` takes JSON `{"description": "..."}`, a form field, or a `text/plain` body, and returns `{"decision", "confidence"}`. A failure is an HTTP error (422 empty text, 502 Joey failed, 503 URL not set, 504 timed out), not a decision of `unclassified`.

`POST /api/v1/classify` and `POST /api/v1/score` are the same call. They take a form field `description` and return the decision, the winning probability, the runner-up teams, and token usage. A file part is rejected with 422: attachments are not read, so they cannot change the answer.

`confidence` is the probability Joey gave the winning option. There is no cutoff below which the service rewrites the label. `unclassified` is one of the five options.

Before the text is sent, the service drops the L1 wrapper (headers, greetings, inline `Вложения:` blocks), then masks secrets and, unless `MASK_INTERNAL_HOSTS=false`, private IP addresses.

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"description": "Не работает VPN туннель до филиала"}' \
  http://localhost:8000/api/v1/decide
```

`GET /health`, `GET /ready`, `GET /api/v1/functions`. `/ready` reports `joey_uses_systemone: true` when `JOEY_SYSTEMONE_URL` is set.

## Run

```bash
cp .env.example .env   # set JOEY_SYSTEMONE_URL
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Docker: `docker compose up --build` after the same `.env`. Kubernetes: `scripts/deploy-k8s.sh`.

## Configuration

See `.env.example`. The routing policy is `JOEY_ROUTE_INSTRUCTIONS` and `JOEY_CRITERIA_*`. Changing them and restarting the process changes decisions; Joey and the image stay as they are.

## Tests

```bash
ruff check app tests
pytest tests/unit tests/integration -q
```
