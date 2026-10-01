# Install Kueue from the official release manifest.
param([string]$Version = "v0.20.0")
$ErrorActionPreference = "Stop"
kubectl apply --server-side -f "https://github.com/kubernetes-sigs/kueue/releases/download/$Version/manifests.yaml"
kubectl -n kueue-system wait deploy/kueue-controller-manager --for=condition=Available --timeout=300s
kubectl -n kueue-system get pods
