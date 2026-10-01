# Create the kind cluster (1 control-plane + 2 workers).
# ASCII only on purpose: Windows PowerShell 5.1 misreads non-BOM UTF-8.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
kind create cluster --config kind/cluster.yaml
kubectl get nodes -L gpuq.dev/gpu-node
