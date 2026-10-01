#!/usr/bin/env bash
# v2 experiments: after install-k3s-gpu.sh, set up time-slicing, Kueue v0.20.0 and the queues.
#   wsl -d Ubuntu-24.04 -- bash /mnt/c/work/gpu-queue-lab/scripts/wsl/setup-v2.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
K="k3s kubectl"
$K apply -f manifests/real-gpu/device-plugin-timeslicing.yaml
$K label node --all gpuq.dev/gpu-node=true --overwrite
$K apply --server-side -f https://github.com/kubernetes-sigs/kueue/releases/download/v0.20.0/manifests.yaml >/dev/null
$K -n kueue-system wait deploy/kueue-controller-manager --for=condition=Available --timeout=300s
$K -n kube-system rollout status ds/nvidia-device-plugin --timeout=300s
until [ "$($K get node -o jsonpath='{.items[0].status.allocatable.nvidia\.com/gpu}')" = "4" ]; do sleep 2; done
for f in 00-namespaces 01-resource-flavor 02-cluster-queues 03-local-queues 04-priority-classes; do
  until $K apply -f manifests/kueue/$f.yaml; do sleep 5; done  # Kueue webhook may need a moment
done
$K get node -o jsonpath='{.items[0].status.allocatable}'; echo
$K get clusterqueues
