# Joey routing through System One

Joey answers through the **System One** API only: a `state` plus typed `questions` in, a probability per option out. The same request works against the self-hosted server on Spark and against Baseten.

## Endpoints

Self-hosted on Spark (what `k8s/deployment.yaml` uses; deploy and why vLLM cannot serve it: [joey.md](joey.md)):

```bash
JOEY_ROUTING_MODE=systemone
JOEY_SYSTEMONE_URL=http://10.70.0.121:8003/v1/systemone
JOEY_DECISION_MODEL=joey-1
```

Baseten instead:

```bash
JOEY_ROUTING_MODE=systemone
JOEY_SYSTEMONE_URL=https://inference.baseten.co/v1/systemone
BASETEN_API_KEY=<your key>          # or JOEY_SYSTEMONE_API_KEY
JOEY_DECISION_MODEL=decision-models/baseten-joey-2b-latest
```

`GET /ready` reports `joey_uses_systemone: true` when a URL is set. The API key is optional and is sent as a bearer token only when present.

## What the classifier sends

- `state`: the ticket description after `extract_request_body` (no attachments, headers or signatures).
- `questions.route`: one `choice` question, instructions `Какая команда поддержки должна обработать это обращение?`.
- `criteria`: `database`, `security`, `network`, `it_infrastructure` and `unclassified`, each with a one-sentence description of what the team handles. The question is `JOEY_ROUTE_INSTRUCTIONS` and the descriptions are `JOEY_CRITERIA_DATABASE`, `JOEY_CRITERIA_SECURITY`, `JOEY_CRITERIA_NETWORK`, `JOEY_CRITERIA_IT_INFRASTRUCTURE`, and `JOEY_CRITERIA_UNCLASSIFIED` (`k8s/deployment.yaml`, or `.env` locally).

The decision is the option with the highest probability, and `confidence` is that probability. `unclassified` is a real option the model can pick, not a confidence threshold.

## Why `choice` with descriptions

Measured on the 176 labeled descriptions (`train_messages_labeled.jsonl`), same server, same sanitized state:

| Question | Accuracy |
|---|---:|
| `score`, four team names as levels (the earlier Playground-style question) | 52.8% |
| `choice`, team names only | 61.9% |
| `choice`, team descriptions | 81.8% |
| `choice`, team descriptions + `unclassified` (in use) | 80.1% |

`score` is meant for ordered levels; team names are not ordered. A probability threshold on the four-way answer does not catch off-topic text (for example a request for an income certificate scored `database` at 0.74), while the explicit `unclassified` option caught all ten off-topic probes tried.

The descriptions were written from the service catalog of the same dataset, so these numbers are not a held-out estimate. To change routing policy, edit the descriptions and re-run the evaluation.

## Comparing with the Baseten Playground

The Playground's **Support routing** tab asks a `score` question over levels, so its distribution is not directly comparable with production any more. To compare like with like, send the production request body (above) to Baseten's `/v1/systemone` endpoint.

## Smoke test against prod

```bash
curl -sS -H 'Host: it-classifier.apps.vexa.home' -H 'Content-Type: application/json' \
  -d '{"description": "много failed password в логах"}' \
  http://10.80.10.29:32381/api/v1/decide
```

Expected: `{"decision":"security","confidence":…}`.
