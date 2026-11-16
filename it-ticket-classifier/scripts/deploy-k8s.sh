#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export KUBECONFIG="${KUBECONFIG:-$HOME/.keys/kube/kube-infra.conf}"
IMAGE="${CLASSIFIER_IMAGE:-ttl.sh/vexa-it-ticket-classifier:24h}"

echo "==> Build image"
docker build -t it-ticket-classifier:local "$ROOT"
docker tag it-ticket-classifier:local "$IMAGE"
docker push "$IMAGE"

kubectl apply -f "$ROOT/k8s/deployment.yaml"
kubectl -n ai-classifier set image deploy/it-ticket-classifier "it-ticket-classifier=${IMAGE}"
kubectl -n ai-classifier rollout status deploy/it-ticket-classifier --timeout=600s

echo
kubectl -n ai-classifier get pvc,deploy,pods,svc,ingress -o wide
echo "API: http://classifier.apps.vexa.home/docs"