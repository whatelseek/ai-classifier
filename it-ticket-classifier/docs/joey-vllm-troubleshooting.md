# Joey (vLLM) troubleshooting for classification

Joey (`baselabs/joey-1` on Spark, `:8001`) is only reliable when vLLM has enough GPU memory and is not competing with Qwen on the same device.

## Symptoms

- Free-text output repeats garbage tokens (e.g. `ówczas…`).
- `json_schema` completions pad with tabs after `"confidence"` or return nonsense (`"confidence": -9`).
- Salvage extracts `database` or `needs_review` for unrelated tickets.
- Near-zero accuracy on L1 ticket eval sets despite healthy `/v1/models`.

## Root cause

Not established. An earlier theory was GPU contention: on `spark1`, **Qwen** (`:8000`, `--gpu-memory-utilization 0.8`) and **Joey** (`:8001`, `0.1`) share one GPU.

That theory does not explain the state seen on 2026-11-17: Joey's `/metrics` reported `gpu_memory_utilization="0.55"`, Qwen was not listening on `:8000`, and Joey still produced garbage. Evidence from that day, all from Joey's HTTP API:

- A raw `/v1/completions` call with `"The capital of France is"` returns `ówczasówczas…`, so the chat template and `json_schema` are not involved.
- With `logprobs: 5`, the top five next tokens all sit near `-10.6`, a near-uniform distribution over the vocabulary. The model behaves as if its weights were not loaded.
- `vllm:request_success_total` showed 2223 requests finished by `length` and 1 by `stop` since process start: no generation ended naturally.

The same model answers correctly on OpenRouter, so look at how this server loads it: the vLLM startup log (weight-loading warnings), the vLLM build (`0.1.dev21818`), and the launch flags against the model card.

## Things to try (none confirmed to fix it)

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