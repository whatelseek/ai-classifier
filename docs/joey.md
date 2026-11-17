# Joey on Spark

`baselabs/joey-1` is the model that picks `database`, `security`, `network`, `it_infrastructure`, or `unclassified`. It runs on spark1 (`10.70.0.121`) port **8003**, and the classifier calls it at `http://10.70.0.121:8003/v1/systemone`.

## Why it works

Joey is a decision model. Two things in the checkpoint are load-bearing, and a normal chat server does neither of them:

- `modeling_overrides.attention.full_attention = "block_bidirectional"`. The full-attention layers were trained with a mask that is bidirectional inside the ticket text and bidirectional inside the question. A causal mask (the mask every chat server uses) makes the next-token distribution collapse.
- `readout = "slot_lm"`. The answer is the logits of the option letters at one position. Nothing is sampled. The runtime compares those logits and returns a probability per option.

The runtime that implements both is OneJev `qev` at commit `81ce62f`, plus the `serve.patch` shipped in the model snapshot. `services/joey-qev-server` runs that runtime. It caches the ticket as a shared prefix, forks one branch per option, and returns the probabilities. A ticket comes back in about 0.1 s and the process uses about 7 GB of GPU memory.

Stock vLLM on port 8001 loads the same weights as `Qwen3_5ForConditionalGeneration` and ignores `modeling_overrides`. The weights load without warnings, so `/health` and `/v1/models` look fine, and the output is noise: repeated tokens such as `ówczasówczas…`, logprobs stuck near `-10.6` (close to uniform over the vocabulary), and almost every request ending because it hit the length limit. GPU memory, the prompt, and `json_schema` do not change this. No vLLM flag applies the bidirectional mask or the slot readout.

Two ways the qev server can look healthy and still score randomly:

- `DecisionEngine` reads `readout.json` and `modeling_overrides` only from a **local directory**. Given the Hub id `baselabs/joey-1` it falls back to causal attention. `serve.py` resolves the snapshot path and exits unless the engine reports `attention=noncausal`.
- `qev serve` selects the multimodal engine because this checkpoint has a `vision_config`, and `serve.patch` does not patch that engine. `serve.py` builds the text `DecisionEngine` directly.

Once the server is noncausal, the question decides the accuracy. On the 176 labeled descriptions the ordered `score` question was 52.8%, a `choice` of bare team names was 61.9%, and a `choice` whose options are team descriptions (including `unclassified`) is 80.1%. That question is what the classifier sends. The text is `ROUTE_CRITERIA` in `app/llm/joey_systemone.py`; the measurements are in [baseten-joey-scoring.md](baseten-joey-scoring.md).

## Deploy

The script builds the image on Spark and replaces the `joey-qev` container. Run it from a machine that can SSH to Spark:

```bash
services/joey-qev-server/deploy.sh
```

What that requires, and what it does:

1. SSH to `andrey@spark1.vexa.home` with `~/.keys/CoreAdmin.key`. Override with `SPARK_HOST`, `SPARK_USER`, `SSH_KEY`.
2. The Hugging Face snapshot of `baselabs/joey-1` is already in `~/.cache/huggingface` on Spark. The script takes `serve.patch` from the newest snapshot under `models--baselabs--joey-1/snapshots/`.
3. It copies `Dockerfile` and `serve.py` to `~/joey-qev-server` on Spark and builds `joey-qev:local`. The base image is `vllm-node-b12x:latest`, used only because it already has the GB10 build of torch and transformers 5.19.0 (the version the model pins). The build installs `accelerate==1.15.0` without dependencies, clones OneJev at `81ce62f1597c91e46767d4d02d6ac2e18534fe94`, and applies `serve.patch`.
4. It removes any existing `joey-qev` container and starts a new one: `--gpus all`, host port `8003`, the Hugging Face cache mounted read-only, `JOEY_MODEL=baselabs/joey-1`, `--restart unless-stopped`. Override the host port with `JOEY_PORT` and the checkpoint with `JOEY_MODEL`.
5. It polls `http://127.0.0.1:8003/health` for up to five minutes. On timeout it prints the last 40 log lines and exits 1.

`docker logs joey-qev` must contain `attention=noncausal`. If it says `causal`, the process is scoring noise; `serve.py` is written to refuse that start, so a causal line means an older image is still running.

### Check the model

```bash
curl -s http://10.70.0.121:8003/health
curl -s http://10.70.0.121:8003/v1/systemone -H 'Content-Type: application/json' -d '{
  "model": "joey-1",
  "state": "Не работает VPN туннель до филиала",
  "questions": {"team": {"type": "choice", "criteria": {"network": "VPN, firewall", "database": "PostgreSQL"}}}
}'
```

A healthy answer has `answers.team.choice = "network"` and a probability well above 0.5.

### Point the classifier at it

The Kubernetes deployment already does this (`k8s/deployment.yaml`):

```yaml
JOEY_ROUTING_MODE: systemone
JOEY_SYSTEMONE_URL: http://10.70.0.121:8003/v1/systemone
JOEY_DECISION_MODEL: joey-1
OPENAI_TEXT_MODEL: joey-1
```

There is no `OPENAI_BASE_URL`. The classifier selects this path when `JOEY_SYSTEMONE_URL` is set and the text model name contains `joey`. `GET /ready` then reports `joey_uses_systemone: true`. No API key is sent to the self-hosted server.

Redeploy the classifier with `scripts/deploy-k8s.sh` only when the API image itself changed. Restarting Joey does not require a new classifier image.

Baseten uses the same request with a different URL and model id. See [baseten-joey-scoring.md](baseten-joey-scoring.md).

## What is left of the old server

The vLLM container `vllm_joey` on spark1 port 8001 (`Joey-1-Local`) cannot serve this model. The Envoy route that used to proxy it (`AIGatewayRoute/spark-joey` in `ai-platform`) was removed, so `x-ai-eg-model: Joey-1-Local` returns 404 at the gateway. The container is unused; stopping it does not affect classification, and starting it again does not produce a working Joey.
