# Baseten Joey — scoring-only (IT ticket routing)

Use this when you need the same **four-way score** as `POST /api/v1/classify`, without actions or custom downstream code.

## Playground setup

1. Open **Baseten → Joey 1 → Playground**.
2. Select the **Support routing** tab (not **Lead qualification** — that tab shows the “nurture sequence” placeholder).
3. **Input mode:** Form.
4. **Question (fixed):**

   ```text
   К какой категории относится обращение?
   ```

5. **Levels (lowest index = lowest score bar order; use four labels aligned with prod):**

   | Index | Label      | Maps to API `function` |
   |------:|------------|-------------------------|
   | 0     | `network`  | `network`               |
   | 1     | `linux`    | `linux`                   |
   | 2     | `security` | `security`                |
   | 3     | `database` | `database`                |

   Do **not** use `dbs` — that only matches half of prod and skews comparisons.

6. **State:** paste the ticket **body only** (same as the classifier after `extract_request_body`):
   - Text after `Описание:` plus `Вложения:` blocks (`<file name="...">…</file>`).
   - Omit L1 wrapper lines (`Классифицируй…`, номер, заявитель, телефон, сервис).
   - Keep under the form size limit; if the UI shows `truncation` at the top, shorten metadata, not CVE rows.

7. **Threshold:** leave default or set ~0.5 — routing in prod uses model JSON + confidence gating, not this slider.
8. **Your code would:** leave empty or disabled for scoring-only tests. Any text there (e.g. “Add to the nurture sequence”) is **not** model output.

## Example State (TCK-211291)

```text
отчет сканера что делать

<file name="scan_report.csv">
host;port;cve;cvss;title
10.50.1.11;443;CVE-2024-6387;8.1;OpenSSH regreSSHion RCE
10.50.1.11;22;CVE-2023-48795;5.9;SSH Terrapin prefix truncation
10.50.1.14;8080;CVE-2024-23897;9.8;Jenkins arbitrary file read
10.50.1.20;443;-;0.0;TLS certificate expires in 25 days
</file>
```

Expected top label: **`security`** (high share in Distribution).

## Production parity (`it-classifier`)

| Baseten Distribution winner | API field `classification.function` |
|----------------------------|-------------------------------------|
| `network`                  | `network`                           |
| `linux`                    | `linux`                             |
| `security`                 | `security`                          |
| `database`                 | `database`                          |

Classifier env (K8s): `OPENAI_TEXT_MODEL=Joey-1-Local`, `OPENAI_MAX_OUTPUT_TOKENS=128`, Joey body hints for CVE/scanner patterns when the model returns `database` from padding salvage.

Smoke test against prod:

```bash
curl -sS -H 'Host: it-classifier.apps.vexa.home' \
  --data-urlencode 'description=…' \
  http://10.80.10.29:32381/api/v1/classify
```

Read `classification.function` and `classification.confidence` only — no `suggested_actions` field.