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