#!/usr/bin/env bash
# Simulation mode (Linux / WSL2): real kube-apiserver + scheduler + Kueue,
# with KWOK fake nodes instead of kubelets. No Docker-in-Docker, no GPU.
# Kueue scheduling decisions are the real ones; pod "execution" is simulated.
set -euo pipefail
for t in curl kubectl python3 openssl go; do command -v $t >/dev/null || { echo "need $t"; exit 1; }; done
python3 -c "import yaml" 2>/dev/null || { echo "need PyYAML (pip install pyyaml)"; exit 1; }
cd "$(dirname "$0")/.."
KUEUE_VERSION=${KUEUE_VERSION:-v0.20.0}
KWOK_VERSION=${KWOK_VERSION:-v0.8.0}
WORK=${WORK:-/tmp/gpuq-sim}
mkdir -p "$WORK/bin" "$WORK/certs"
export PATH="$WORK/bin:$PATH"

# 1. tools
for b in kwokctl kwok; do
  [ -x "$WORK/bin/$b" ] || { curl -sSLo "$WORK/bin/$b" "https://github.com/kubernetes-sigs/kwok/releases/download/$KWOK_VERSION/$b-linux-amd64"; chmod +x "$WORK/bin/$b"; }
done
[ -x "$WORK/bin/kueue" ] || GOBIN="$WORK/bin" go install "sigs.k8s.io/kueue/cmd/kueue@$KUEUE_VERSION"

# 2. cluster (control plane binaries + KWOK with our stages)
kwokctl create cluster --name gpuq --runtime binary --config kwok/stages.yaml
export KUBECONFIG="$WORK/kubeconfig"
kwokctl get kubeconfig --name gpuq > "$KUBECONFIG"

# 3. Kueue CRDs (conversion webhooks dropped: no webhook service in sim mode)
curl -sSL "https://github.com/kubernetes-sigs/kueue/releases/download/$KUEUE_VERSION/manifests.yaml" -o "$WORK/kueue.yaml"
python3 - "$WORK/kueue.yaml" "$WORK/kueue-crds.yaml" <<'PY'
import sys, yaml
crds = [d for d in yaml.safe_load_all(open(sys.argv[1])) if d and d["kind"] == "CustomResourceDefinition"]
for c in crds:
    c["spec"].pop("conversion", None)
yaml.safe_dump_all(crds, open(sys.argv[2], "w"))
PY
kubectl apply --server-side -f "$WORK/kueue-crds.yaml" >/dev/null
kubectl wait --for condition=established --timeout=60s -f "$WORK/kueue-crds.yaml" >/dev/null
kubectl create namespace kueue-system --dry-run=client -o yaml | kubectl apply -f - >/dev/null

# 4. Kueue controller as a local process (self-signed certs for its servers)
for d in /tmp/k8s-webhook-server/serving-certs /etc/kueue/metrics/certs; do
  mkdir -p "$d"
  [ -f "$d/tls.crt" ] || openssl req -x509 -newkey rsa:2048 -nodes -days 7 -subj "/CN=localhost" \
    -keyout "$d/tls.key" -out "$d/tls.crt" 2>/dev/null
done
setsid nohup kueue --config sim/kueue-config.yaml --feature-gates=VisibilityOnDemand=false \
  > "$WORK/kueue.log" 2>&1 &
sleep 10

# 5. nodes + queues
kubectl apply -f sim/nodes.yaml
for f in 00-namespaces 01-resource-flavor 02-cluster-queues 03-local-queues 04-priority-classes; do
  kubectl apply -f "manifests/kueue/$f.yaml"
done
kubectl get nodes -o custom-columns="NODE:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu"
echo "export KUBECONFIG=$KUBECONFIG"
