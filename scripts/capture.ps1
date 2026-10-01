# Save the evidence for one scenario run into evidence/<Name>/.
param([Parameter(Mandatory = $true)][string]$Name)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$dir = "evidence/$Name"
New-Item -ItemType Directory -Force -Path $dir | Out-Null

kubectl get workloads.kueue.x-k8s.io -A -o json | Set-Content "$dir/workloads.json" -Encoding utf8
kubectl get workloads.kueue.x-k8s.io -A -o wide | Set-Content "$dir/workloads.txt" -Encoding utf8
kubectl get clusterqueues -o wide | Set-Content "$dir/clusterqueues.txt" -Encoding utf8
kubectl get pods -A -l gpuq.dev/team -o wide | Set-Content "$dir/pods.txt" -Encoding utf8
kubectl get events -A --sort-by=.lastTimestamp | Select-String -Pattern "Preempt|Admitted|QuotaReserved|Evict" |
    ForEach-Object { $_.Line } | Set-Content "$dir/events.txt" -Encoding utf8
python -m gpuq report --input "$dir/workloads.json" --csv "$dir/report.csv" | Set-Content "$dir/report.md" -Encoding utf8
Get-Content "$dir/report.md"
Write-Host "saved to $dir"
