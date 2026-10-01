# Advertise a fake nvidia.com/gpu capacity on every gpu-node worker.
# Kubernetes treats it like any extended resource, so Kueue and the
# scheduler behave exactly as with real GPUs (pods just don't touch a GPU).
# Re-run after the cluster restarts.
param([int]$GpusPerNode = 2)
$ErrorActionPreference = "Stop"

# Patch via a file: PowerShell 5.1 mangles quotes in inline JSON args.
$patch = Join-Path $env:TEMP "gpuq-gpu-patch.json"
'[{"op":"add","path":"/status/capacity/nvidia.com~1gpu","value":"' + $GpusPerNode + '"}]' |
    Set-Content -Path $patch -Encoding ascii

$nodes = kubectl get nodes -l gpuq.dev/gpu-node=true -o name
foreach ($n in $nodes) {
    kubectl patch $n --subresource=status --type=json --patch-file $patch
}
Start-Sleep -Seconds 3
kubectl get nodes -l gpuq.dev/gpu-node=true -o custom-columns="NODE:.metadata.name,GPU_CAPACITY:.status.capacity.nvidia\.com/gpu,GPU_ALLOCATABLE:.status.allocatable.nvidia\.com/gpu"
