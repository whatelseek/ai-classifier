# IT ticket classifier — agent rules

This repository implements **scoring / routing only**. Do not run free-text chat completion for tickets.

## Required integration

- Call **`POST /api/v1/score`** (preferred) or **`POST /api/v1/classify`** on `it-classifier`.
- Read only: `classification.function`, `classification.confidence`, and optional `alternatives`.
- Do **not** generate “предложи действия”, triage playbooks, or user replies in agent output unless the user explicitly asks for prose outside classification.

## What not to do

- Do not call vLLM / Joey / OpenAI **chat completions** with the L1 prompt “Классифицируй обращение и предложи действия”.
- Do not use Baseten **Lead qualification** or “Your code would” blocks for IT routing.
- Do not treat attachment inline `<file>` tags as a reason to narrate remediation steps.

## Example

```bash
curl -sS -H 'Host: it-classifier.apps.vexa.home' \
  --data-urlencode 'description=…ticket text…' \
  http://it-classifier.apps.vexa.home/api/v1/score
```

Return the API JSON to the user (or `function` + `confidence` only).

## Labels

Routing uses three teams: **`it_infrastructure`** (IT-infrastructure), **`security`**, **`database`**. Classification uses **description text only** (`CLASSIFY_DESCRIPTION_ONLY=true`); attachments are parsed but not sent to the scorer.

## Joey = Baseten Playground (score)

In cluster, Joey routing uses **System One** (`JOEY_ROUTING_MODE=auto`) when `BASETEN_API_KEY` is set — same `state` + score question as Playground. Without the key, the service falls back to Spark vLLM `json_schema` (not Playground-identical). Check `GET /ready`: `joey_uses_systemone` must be `true` for parity.