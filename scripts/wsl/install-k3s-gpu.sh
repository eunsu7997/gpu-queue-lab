#!/usr/bin/env bash
# Real-GPU step (docs/real-gpu.md), part 1: needs root, run once inside WSL2 Ubuntu.
#   wsl -d Ubuntu-24.04 -- sudo bash /mnt/c/work/gpu-queue-lab/scripts/wsl/install-k3s-gpu.sh
# Installs the NVIDIA Container Toolkit and k3s. k3s finds nvidia-container-runtime
# on start and registers an "nvidia" containerd runtime + RuntimeClass by itself.
# Undo: /usr/local/bin/k3s-uninstall.sh && apt-get remove -y nvidia-container-toolkit
set -euo pipefail

# 1. NVIDIA Container Toolkit (official apt repo)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey |
  gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list |
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  > /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt-get update
apt-get install -y nvidia-container-toolkit

# 2. k3s (single node). kubeconfig readable by the normal user; no traefik needed.
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--write-kubeconfig-mode 644 --disable traefik" sh -

# 3. check
sleep 10
grep -n nvidia /var/lib/rancher/k3s/agent/etc/containerd/config.toml || echo "WARN: nvidia runtime not in containerd config"
k3s kubectl get nodes
k3s kubectl get runtimeclass
