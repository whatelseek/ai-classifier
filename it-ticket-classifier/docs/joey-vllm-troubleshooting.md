# Joey on Spark: why vLLM returns garbage, and how it is served instead

## Root cause

`baselabs/joey-1` is a **decision model**, not a text generator. Its model card and `config.json` say so:

- `modeling_overrides.attention.full_attention = "block_bidirectional"`: the full-attention layers were trained with a mask that is bidirectional inside the prompt prefix and inside the question suffix.
- `readout = "slot_lm"`: the answer is read from the logits of the option letters at one position. No token is ever sampled.
- The repository ships `setup.sh` and `serve.patch`, which install the only supported runtime: OneJev `qev` at commit `81ce62f` plus the patch.

vLLM resolves the checkpoint as `Qwen3_5ForConditionalGeneration`, ignores `modeling_overrides`, runs it with a causal mask and samples from the LM head. The weights load without warnings, so nothing in the vLLM log points at the problem. The output is noise.

GPU contention with Qwen, `--gpu-memory-utilization`, prompts and `json_schema` have nothing to do with it. No vLLM flag fixes this.

## Symptoms under vLLM

- Any completion repeats tokens such as `ówczasówczas…`, including a raw `/v1/completions` call.
- With `logprobs`, the top next tokens all sit near `-10.6` (close to uniform over the vocabulary).
- `vllm:request_success_total` shows almost every request finished by `length`.
- `/v1/models` and `/health` look healthy.

## How Joey is served

`services/joey-qev-server` runs the checkpoint with the `qev` `DecisionEngine` and exposes the System One API on spark1 port **8003**:

```bash
services/joey-qev-server/deploy.sh
```

The script builds an image on Spark from `vllm-node-b12x` (used only for its GB10 build of torch and transformers 5.19.0, the version the model pins), clones OneJev at the pinned commit, applies the `serve.patch` from the model snapshot in the HF cache, and starts container `joey-qev` with `--restart unless-stopped`. It uses about 7 GB of GPU memory and answers a ticket in about 0.1 s.

Two details that silently break it:

- `DecisionEngine` reads `readout.json` and `modeling_overrides` only when given a **local directory**. Given the Hub id `baselabs/joey-1` it falls back to causal attention. `serve.py` resolves the snapshot path and refuses to start unless the engine reports `attention=noncausal`.
- `qev serve` picks the multimodal engine for this checkpoint (it has a `vision_config`), and `serve.patch` does not patch that engine. `serve.py` builds the text `DecisionEngine` directly, as the model card does.

The classifier reaches it through `JOEY_SYSTEMONE_URL=http://10.70.0.121:8003/v1/systemone` (see `k8s/deployment.yaml`). No API key is needed.

## Smoke test

```bash
curl -s http://10.70.0.121:8003/health
curl -s http://10.70.0.121:8003/v1/systemone -H 'Content-Type: application/json' -d '{
  "model": "joey-1",
  "state": "Не работает VPN туннель до филиала",
  "questions": {"team": {"type": "choice", "criteria": {"network": "VPN, firewall", "database": "PostgreSQL"}}}
}'
```

A healthy answer has `answers.team.choice = "network"` with a probability well above 0.5. `docker logs joey-qev` must contain `attention=noncausal`.

## The old vLLM endpoint

The vLLM container `vllm_joey` (spark1 `:8001`, model id `Joey-1-Local`, also the Envoy route) cannot serve this model. The classifier's routing no longer calls it. `OPENAI_TEXT_MODEL=Joey-1-Local` stays in the deployment because a model name containing `joey` is what selects the System One code path.
