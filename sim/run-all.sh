#!/usr/bin/env bash
# Run S1-S4 back to back on the simulation cluster and save evidence/sim/<scenario>/.
# Durations are shorter than docs/experiments.md (120s instead of 300s) to keep a run ~10 min.
set -euo pipefail
cd "$(dirname "$0")/.."
D=${D:-120}          # job duration for S1/S4
OUT=evidence/sim

reset() {
  kubectl delete jobs --all -n team-a --wait=true >/dev/null
  kubectl delete jobs --all -n team-b --wait=true >/dev/null
  sleep 3
}
capture() {
  local dir="$OUT/$1"; mkdir -p "$dir"
  kubectl get workloads.kueue.x-k8s.io -A -o json > "$dir/workloads.json"
  kubectl get workloads.kueue.x-k8s.io -A -o wide > "$dir/workloads.txt"
  kubectl get clusterqueues -o wide > "$dir/clusterqueues.txt"
  kubectl get events -A --sort-by=.lastTimestamp 2>/dev/null | grep -E "Preempt|Admitted|QuotaReserved|Evict" > "$dir/events.txt" || true
  python3 -m gpuq report --input "$dir/workloads.json" --csv "$dir/report.csv" > "$dir/report.md"
  echo "== $1"; cat "$dir/report.md"
}
wait_done() {   # wait until every job in team-a/team-b has completed
  local s
  while :; do
    # name=succeeded per line; read into a variable first because
    # `kubectl | grep -q` + pipefail fails on SIGPIPE
    s=$(kubectl get jobs -A -l gpuq.dev/team -o jsonpath='{range .items[*]}{.metadata.name}={.status.succeeded}{"\n"}{end}')
    grep -qv '=1$' <<<"$s" || break
    sleep 3
  done
}
sample() { python3 -m gpuq sample --interval 2 --seconds "$2" --out "$OUT/$1/gpu-usage.csv" >/dev/null & }

rm -rf "$OUT"; mkdir -p "$OUT"/{s1-s2,s3,s4,s1-clean}
reset

echo "### S1+S2: team-a borrows, team-b reclaims"
sample s1-s2 $((D * 3))
python3 -m gpuq submit --team team-a --count 4 --duration "$D" --prefix s1-a
sleep 30
kubectl get workloads -A -o wide > "$OUT/s1-s2/at-30s-before-team-b.txt"
kubectl get clusterqueue team-a-cq -o yaml > "$OUT/s1-s2/team-a-cq-borrowing.yaml"
python3 -m gpuq submit --team team-b --count 2 --duration 60 --prefix s2-b
sleep 10
kubectl get workloads -A -o wide > "$OUT/s1-s2/at-40s-after-team-b.txt"
wait_done; capture s1-s2; wait

echo "### S3: priority preemption inside team-a"
reset
python3 -m gpuq submit --team team-b --count 2 --duration 90 --prefix s3-b
python3 -m gpuq submit --team team-a --count 2 --duration 90 --prefix s3-low
sleep 15
python3 -m gpuq submit --team team-a --count 1 --duration 30 --priority high --prefix s3-high
sleep 10
kubectl get workloads -A -o wide > "$OUT/s3/after-high-submitted.txt"
wait_done; capture s3

echo "### S4: strict quota (no cohort)"
reset
kubectl apply -f manifests/kueue/variants/no-borrowing.yaml >/dev/null
sleep 3
sample s4 $((D * 2 + 30))
python3 -m gpuq submit --team team-a --count 4 --duration "$D" --prefix s4-a
wait_done; capture s4; wait

echo "### S1-clean: same 4 jobs with cohort, no team-b"
reset
kubectl apply -f manifests/kueue/02-cluster-queues.yaml >/dev/null
sleep 3
sample s1-clean $((D + 30))
python3 -m gpuq submit --team team-a --count 4 --duration "$D" --prefix s1c-a
wait_done; capture s1-clean; wait
echo done
