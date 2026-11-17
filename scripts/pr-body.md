## Summary

Production deployment support for the IT ticket classifier on Kubernetes, with **Joey-1** served on Spark via **Envoy AI Gateway**, and **Docling** extracted on Spark (slim API container).

## Changes

### Runtime / LLM
- `OPENAI_BASE_URL` for OpenAI-compatible gateways (vLLM / Envoy)
- Chat Completions + `json_schema` structured output (Joey on Spark)
- Partial JSON **salvage** for truncated vLLM responses (no post-LLM heuristic fallback)
- `max_tokens=2048` for classification calls

### Docling
- Optional remote `DOCLING_API_URL` (`POST /v1/extract`)
- `services/docling-server` sidecar image for Spark
- Docling removed from default wheel deps (`pip install .[docling]` for local in-process use)

### Kubernetes
- `it-ticket-classifier/k8s/deployment.yaml` — namespace `it-classifier`, **30Gi PVC**, ingress `it-classifier.apps.vexa.home`
- `scripts/deploy-k8s.sh`

## Ops notes (outside repo)

- Spark: Joey vLLM on `10.70.0.121:8001` (`Joey-1-Local`)
- Spark: Docling on `10.70.0.121:8002`
- Envoy: `joey-gateway.yaml` in `k8s-apps` (platform repo / ops)