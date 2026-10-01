#!/usr/bin/env bash
# Try to start the CUDA MPS control daemon next to the GPU, through Docker Desktop (WSL2).
# Records why MPS can't be compared with time-slicing on this machine.
#   bash scripts/mps-check.sh > evidence/real-gpu-v2/mps/mps-check.txt 2>&1
IMAGE=${IMAGE:-vllm/vllm-openai:latest}   # any image with apt + a CUDA PyTorch
docker run --rm --gpus all --entrypoint bash "$IMAGE" -c '
echo "## GPU device nodes inside the container (native Linux has /dev/nvidia0, /dev/nvidiactl; WSL2 has only /dev/dxg)"
ls -la /dev | grep -E "nvidia|dxg"
nvidia-smi --query-gpu=name,driver_version --format=csv
echo "## nvidia-cuda-mps-control from the Ubuntu driver package"
apt-get update -qq >/dev/null 2>&1
PKG=$(apt-cache search --names-only "^nvidia-compute-utils-[0-9]+$" | sort -V | tail -1 | cut -d" " -f1)
cd /tmp && apt-get download "$PKG" >/dev/null 2>&1 && dpkg -x ./*.deb x && echo "package: $PKG"
export CUDA_MPS_PIPE_DIRECTORY=/tmp/mps CUDA_MPS_LOG_DIRECTORY=/tmp/mpslog
mkdir -p $CUDA_MPS_PIPE_DIRECTORY $CUDA_MPS_LOG_DIRECTORY
x/usr/bin/nvidia-cuda-mps-control -d; echo "mps-control -d exit code: $?"
sleep 2
echo get_server_list | x/usr/bin/nvidia-cuda-mps-control; echo "control query exit code: $?"
echo "## log dir"; ls -la /tmp/mpslog; cat /tmp/mpslog/* 2>/dev/null
echo "## CUDA itself still works (plain time-sliced context)"
python3 -c "import torch; a=torch.randn(2048,2048,device=\"cuda\"); print(\"cuda ok\", torch.cuda.get_device_name(0), float((a@a).sum()))"
'
