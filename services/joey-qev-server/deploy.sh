#!/usr/bin/env bash
# Run the joey-1 System One server on spark1 (port 8003). The model must already be in the HF cache there.
set -euo pipefail
SPARK_HOST="${SPARK_HOST:-spark1.vexa.home}"
SPARK_USER="${SPARK_USER:-andrey}"
SSH_KEY="${SSH_KEY:-$HOME/.keys/CoreAdmin.key}"
SRC="$(cd "$(dirname "$0")" && pwd)"
PORT="${JOEY_PORT:-8003}"
MODEL="${JOEY_MODEL:-baselabs/joey-1}"

tar -cf - -C "$SRC" Dockerfile serve.py | ssh -i "$SSH_KEY" "${SPARK_USER}@${SPARK_HOST}" \
  "mkdir -p ~/joey-qev-server && tar -xf - -C ~/joey-qev-server"

ssh -i "$SSH_KEY" "${SPARK_USER}@${SPARK_HOST}" bash -s <<REMOTE
set -euo pipefail
SNAP=\$(ls -d ~/.cache/huggingface/hub/models--${MODEL//\//--}/snapshots/* | tail -1)
cd ~/joey-qev-server
cp "\$SNAP/serve.patch" serve.patch
docker build -t joey-qev:local .
docker rm -f joey-qev 2>/dev/null || true
docker run -d --name joey-qev --restart unless-stopped \\
  --gpus all --ipc=host \\
  -p ${PORT}:8003 \\
  -e JOEY_MODEL=${MODEL} \\
  -v "\$HOME/.cache/huggingface:/root/.cache/huggingface:ro" \\
  joey-qev:local
for i in \$(seq 1 60); do
  curl -sf http://127.0.0.1:${PORT}/health && { echo; echo "joey-qev OK on :${PORT}"; exit 0; }
  sleep 5
done
docker logs --tail 40 joey-qev
exit 1
REMOTE
