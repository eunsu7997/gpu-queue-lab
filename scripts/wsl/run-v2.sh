#!/usr/bin/env bash
# v2 experiments, 3 repetitions each. Repetitions are interleaved (A B A B ...) so slow drift
# in the machine (Windows apps, temperature) hits every variant equally.
#   wsl -d Ubuntu-24.04 -- bash /mnt/c/work/gpu-queue-lab/scripts/wsl/run-v2.sh mix
#   wsl -d Ubuntu-24.04 -- bash /mnt/c/work/gpu-queue-lab/scripts/wsl/run-v2.sh ckpt
set -uo pipefail
cd "$(dirname "$0")/../.."
REPS=${REPS:-3}
case "${1:?mix|ckpt}" in
  mix)
    for rep in $(seq 1 "$REPS"); do
      for mix in mixed small large; do
        for quota in strict borrow; do
          python3 tools/v2_run.py mix --mix $mix --quota $quota --rep $rep
        done
      done
    done ;;
  ckpt)
    for rep in $(seq 1 "$REPS"); do
      for c in none periodic periodic+sigterm; do
        python3 tools/v2_run.py ckpt --ckpt $c --rep $rep
      done
    done ;;
esac
