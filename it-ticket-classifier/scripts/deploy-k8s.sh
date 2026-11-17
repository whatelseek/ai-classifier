#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export KUBECONFIG="${KUBECONFIG:-$HOME/.keys/kube/kube-infra.conf}"
IMAGE="${CLASSIFIER_IMAGE:-ttl.sh/vexa-it-ticket-classifier:24h}"

echo "==> Build slim API image (Docling runs on Spark)"
docker build -t it-ticket-classifier:local "$ROOT"
docker tag it-ticket-classifier:local "$IMAGE"
docker push "$IMAGE"

kubectl apply -f "$ROOT/k8s/deployment.yaml"
kubectl -n it-classifier set image deploy/it-ticket-classifier api="${IMAGE}"
# Same tag is reused on every push, so force a new pod to pull it.
kubectl -n it-classifier rollout restart deploy/it-ticket-classifier
kubectl -n it-classifier rollout status deploy/it-ticket-classifier --timeout=600s

echo
kubectl -n it-classifier get pvc,deploy,pods,svc,ingress -o wide
echo "API: http://it-classifier.apps.vexa.home/docs"