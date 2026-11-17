"""Serve baselabs/joey-1 with the runtime it was trained for (OneJev qev + the checkpoint's serve.patch).

joey-1 is a decision model, not a text generator: its full-attention layers use a block-bidirectional mask and
answers are read from option-slot logits. An OpenAI-style server (vLLM) runs it as a causal LM and samples noise.

Exposes the System One API: POST /v1/systemone, GET /v1/models, GET /health.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import uvicorn
from huggingface_hub import snapshot_download
from qev.engine import DecisionEngine
from qev.server import create_app

log = logging.getLogger("joey.serve")


def resolve_model_dir(model: str) -> str:
    """DecisionEngine reads readout.json and config.json's modeling_overrides only from a local directory;
    given a Hub id it silently falls back to causal attention."""
    if Path(model).is_dir():
        return model
    return snapshot_download(model, local_files_only=os.environ.get("HF_HUB_OFFLINE") == "1")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    model_dir = resolve_model_dir(os.environ.get("JOEY_MODEL", "baselabs/joey-1"))
    engine = DecisionEngine(
        model_dir,
        device=os.environ.get("JOEY_DEVICE", "cuda:0"),
        max_branch_tokens=int(os.environ.get("JOEY_MAX_BRANCH_TOKENS", "16384")),
    )
    attention = engine.info.extra["attention"]
    log.info("attention=%s readout=%s fork_mode=%s", attention, engine.info.extra["readout"], engine.info.fork_mode)
    if attention != "noncausal":
        raise SystemExit(f"{model_dir} loaded with {attention} attention; joey-1 must be served noncausal")
    app = create_app(engine, model_name=os.environ.get("JOEY_MODEL_NAME", "joey-1"),
                     description="baselabs/joey-1 decision model (qev runtime)")
    uvicorn.run(app, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8003")),
                log_level="info")


if __name__ == "__main__":
    main()
