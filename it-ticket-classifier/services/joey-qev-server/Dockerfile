# Built on the Spark vLLM image only for its GB10-compatible torch and transformers 5.19.0 (the version
# joey-1 pins); vLLM itself is not used.
ARG BASE_IMAGE=vllm-node-b12x:latest
FROM ${BASE_IMAGE}

# Runtime commit pinned by the model repository's setup.sh.
ARG ONEJEV_COMMIT=81ce62f1597c91e46767d4d02d6ac2e18534fe94

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/OneJev \
    HF_HUB_OFFLINE=1

# --no-deps keeps the image's CUDA build of torch.
RUN pip install --no-cache-dir --no-deps accelerate==1.15.0

# serve.patch comes from the model snapshot (deploy.sh copies it into the build context).
COPY serve.patch /tmp/serve.patch
RUN git clone -q https://github.com/OmniJev/OneJev.git /opt/OneJev \
    && git -C /opt/OneJev checkout -q "${ONEJEV_COMMIT}" \
    && git -C /opt/OneJev apply /tmp/serve.patch \
    && rm -rf /opt/OneJev/.git /opt/OneJev/assets /tmp/serve.patch

COPY serve.py /opt/joey/serve.py

EXPOSE 8003

CMD ["python3", "/opt/joey/serve.py"]
