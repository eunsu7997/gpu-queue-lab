#!/usr/bin/env bash
pkill -x kueue || true
PATH="${WORK:-/tmp/gpuq-sim}/bin:$PATH" kwokctl delete cluster --name gpuq
