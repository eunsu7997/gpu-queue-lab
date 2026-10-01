# Delete all experiment jobs (and their workloads) between scenarios.
kubectl delete jobs --all -n team-a --wait=true
kubectl delete jobs --all -n team-b --wait=true
