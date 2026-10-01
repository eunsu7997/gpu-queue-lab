# Namespaces, ResourceFlavor, ClusterQueues (with cohort), LocalQueues, priorities.
# Pass -NoBorrowing to use the strict-quota baseline for scenario S4.
param([switch]$NoBorrowing)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
kubectl apply -f manifests/kueue/00-namespaces.yaml
kubectl apply -f manifests/kueue/01-resource-flavor.yaml
if ($NoBorrowing) {
    kubectl apply -f manifests/kueue/variants/no-borrowing.yaml
} else {
    kubectl apply -f manifests/kueue/02-cluster-queues.yaml
}
kubectl apply -f manifests/kueue/03-local-queues.yaml
kubectl apply -f manifests/kueue/04-priority-classes.yaml
kubectl get clusterqueues,localqueues -A
