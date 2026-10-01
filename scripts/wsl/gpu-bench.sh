#!/usr/bin/env bash
# Real-GPU step (docs/real-gpu.md), part 2: run N copies of tools/gpu_bench.py at once
# on the k3s time-sliced GPU and save one JSON line per job.
#   wsl -d Ubuntu-24.04 -- bash /mnt/c/work/gpu-queue-lab/scripts/wsl/gpu-bench.sh 1
#   wsl -d Ubuntu-24.04 -- bash /mnt/c/work/gpu-queue-lab/scripts/wsl/gpu-bench.sh 4
set -euo pipefail
cd "$(dirname "$0")/../.."
N=${1:-1}
OUT=evidence/real-gpu; mkdir -p "$OUT"
K="k3s kubectl"
IMAGE=${IMAGE:-pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime}

$K create configmap gpu-bench --from-file=tools/gpu_bench.py --dry-run=client -o yaml | $K apply -f - >/dev/null
$K delete jobs -l app=gpu-bench --wait=true >/dev/null

for i in $(seq -w 1 "$N"); do
cat <<EOF | $K apply -f - >/dev/null
apiVersion: batch/v1
kind: Job
metadata:
  name: bench-n${N}-${i}
  labels: {app: gpu-bench}
spec:
  backoffLimit: 0
  template:
    metadata:
      labels: {app: gpu-bench}
    spec:
      runtimeClassName: nvidia
      restartPolicy: Never
      containers:
        - name: train
          image: ${IMAGE}
          command: ["python", "/bench/gpu_bench.py"]
          env: [{name: STEPS, value: "${STEPS:-3000}"}]
          resources:
            limits: {nvidia.com/gpu: 1}
          volumeMounts: [{name: bench, mountPath: /bench}]
      volumes: [{name: bench, configMap: {name: gpu-bench}}]
EOF
done

# sample GPU utilisation while the jobs run
( while :; do nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader; sleep 2; done ) \
  > "$OUT/n${N}-nvidia-smi.csv" &
SMI=$!
$K wait --for=condition=complete jobs -l app=gpu-bench --timeout=1800s >/dev/null
kill $SMI
$K get pods -l app=gpu-bench -o wide > "$OUT/n${N}-pods.txt"
: > "$OUT/n${N}.jsonl"
for j in $($K get jobs -l app=gpu-bench -o name); do $K logs "$j" | tail -1 >> "$OUT/n${N}.jsonl"; done
cat "$OUT/n${N}.jsonl"
