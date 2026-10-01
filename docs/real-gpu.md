# (선택) 실제 RTX 4060으로 검증하기

가짜 GPU 실험이 끝난 뒤, 같은 큐 설정을 실제 GPU에서 확인하는 단계입니다.
KubeLLM-Ops의 "Kubernetes GPU 할당" 단계를 먼저 끝내면 그 설정을 그대로 씁니다.

## 1. 쿠버네티스에서 GPU가 보이게 하기

Windows + Docker Desktop kind는 기본 설정으로 노드 안에 GPU가 안 들어갑니다. 아래 중 하나가 필요합니다.

- NVIDIA의 **nvkind**(kind에 GPU를 붙이는 도구)를 WSL2 Ubuntu 안에서 사용
- WSL2 Ubuntu에 **k3s** 설치 + NVIDIA Container Toolkit

어느 쪽이든 끝나면 `kubectl describe node`에 `nvidia.com/gpu: 1`이 보여야 합니다.
이 단계는 아직 검증 전이니, 막히면 그 과정을 그대로 트러블슈팅 기록으로 남깁니다.

## 2. Time-slicing으로 GPU 1장을 4개로 나누기

NVIDIA device plugin 설정(ConfigMap):

```yaml
version: v1
sharing:
  timeSlicing:
    resources:
      - name: nvidia.com/gpu
        replicas: 4
```

적용 후 노드의 `nvidia.com/gpu`가 4로 보이면, 가짜 GPU와 같은 숫자라서 `manifests/kueue/` 설정을 수정 없이 쓸 수 있습니다.
(가짜 GPU 패치 스크립트는 실행하지 않습니다. 노드 라벨 `gpuq.dev/gpu-node=true`만 붙입니다.)

주의: time-slicing은 메모리 격리가 없습니다. 8GB VRAM을 4개 작업이 나눠 쓰므로 작업당 2GB 이하로 작게 잡습니다. 이 한계 자체가 면접에서 좋은 이야깃거리입니다(MIG와의 차이).

## 3. 진짜 학습 작업 넣기

```powershell
python -m gpuq submit --team team-a --count 4 --prefix gpu-a `
  --image pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime
```

기본 명령은 sleep이므로, 실제 학습을 돌리려면 `gpuq/jobs.py`의 `command`에 작은 PyTorch 학습 스크립트(예: MNIST 1 epoch)를 넣습니다.
측정 포인트: time-slicing 1개 작업 단독 vs 4개 동시 실행 시 작업당 학습 시간.
