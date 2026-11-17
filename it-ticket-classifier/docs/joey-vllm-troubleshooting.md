# Joey (vLLM) troubleshooting for classification

Joey (`baselabs/joey-1` on Spark, `:8001`) is only reliable when vLLM has enough GPU memory and is not competing with Qwen on the same device.

## Symptoms

- Free-text output repeats garbage tokens (e.g. `ówczas…`).
- `json_schema` completions pad with tabs after `"confidence"` or return nonsense (`"confidence": -9`).
- Salvage extracts `database` or `needs_review` for unrelated tickets.
- Near-zero accuracy on L1 ticket eval sets despite healthy `/v1/models`.

## Root cause (observed)

On `spark1`, **Qwen** (`:8000`, `--gpu-memory-utilization 0.8`) and **Joey** (`:8001`, `0.1`) share one GPU. Joey keeps a small slice of VRAM while Qwen dominates; generations become invalid.

## Fixes

1. **Prefer Qwen for routing** (recommended today): point the classifier at Spark Qwen with the real served model id, `OPENAI_MAX_OUTPUT_TOKENS=256`, low concurrency.
2. **Joey solo**: stop the Qwen container, restart Joey with `gpu_memory_utilization` ≥ **0.25** (see `k8s-apps/ai-platform/spark-vllm/recipes/baselabs-joey-1-solo.yaml`).
3. **Envoy**: use `OPENAI_BASE_URL` to Envoy and set `x-ai-eg-model` (see `OpenAIClassificationClient`) plus matching `--served-model-name` on vLLM.
4. **Do not** expect prompt or schema tweaks alone to fix starved Joey; validate with a plain completion (`max_tokens: 16`) before running batch evals.

## Quick smoke test

```bash
curl -s "http://SPARK:8001/v1/chat/completions" -H 'Content-Type: application/json' \
  -d '{"model":"Joey-1-Local","messages":[{"role":"user","content":"Say: ok"}],"max_tokens":8,"temperature":0}'
```

If the content is not a short sensible string, Joey is unhealthy—restart solo or switch models.