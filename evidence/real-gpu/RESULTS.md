# 실제 GPU time-slicing 결과 (2026-10-01)

환경: Windows 11 + WSL2 Ubuntu 24.04, RTX 4060 8GB (드라이버 616.92), NVIDIA Container Toolkit,
k3s v1.36.4 (containerd `nvidia` RuntimeClass), NVIDIA device plugin v0.17.1 time-slicing `replicas: 4`.
→ 노드에 `nvidia.com/gpu: 4`로 보임 (GPU 1장 = 4조각).

작업: `tools/gpu_bench.py` (작은 CNN, MNIST 크기 랜덤 데이터, batch 256, 3000 step). 데이터셋 다운로드 없이 GPU 시간만 잼.
재현: `scripts/wsl/install-k3s-gpu.sh`(sudo, 1회) → `kubectl apply -f manifests/real-gpu/device-plugin-timeslicing.yaml` → `scripts/wsl/gpu-bench.sh 1`, `scripts/wsl/gpu-bench.sh 4`.

## 단독 1개 vs 동시 4개

| | 단독 1개 | 동시 4개 (time-slicing) |
|---|---|---|
| 작업당 학습 시간 | **43.7초** | **228~230초** (5.3배) |
| 작업당 속도 | 68.6 step/s | 13.0 step/s |
| GPU 전체 처리량 | 68.6 step/s | 52.2 step/s (**-24%**) |
| 4개 모두 끝나는 시간 | 175초 (하나씩 차례로 돌렸다면) | 231초 (**+32%**) |
| nvidia-smi 사용률 (실행 중) | 99~100% | 99% |
| VRAM 사용 (Windows 화면 등 기본 3.6GB 포함) | 4.2GB | 6.2GB |

## 해석

- time-slicing은 **GPU를 나눠 "보이게" 해 줄 뿐 연산을 늘려 주지 않습니다.** 이미 GPU를 100% 쓰는 학습 작업 4개를 겹치면
  작업마다 1/4 속도 이하로 느려지고, 문맥 전환 비용 때문에 **전체 처리량이 24% 줄었습니다.** 이런 작업은 Kueue로 줄 세워 하나씩 돌리는 편이 더 빠릅니다.
- 메모리 격리가 없습니다. 작업 하나가 프로세스당 약 0.6GB(대부분 CUDA context)를 쓰고, 4개면 2.5GB가 늘었습니다.
  8GB 중 Windows가 이미 3.6GB를 쓰고 있어 큰 모델 4개는 OOM이 납니다. → 작업별 VRAM 상한이 필요하면 MIG(A100/H100) 같은 하드웨어 분할이 필요합니다.
- time-slicing이 이득인 경우는 GPU를 조금씩만 쓰는 작업(추론 서버, 노트북, 디버깅)을 여러 개 띄울 때입니다.

원본: `n1.jsonl`, `n4.jsonl` (작업별 JSON), `n1/n4-nvidia-smi.csv` (2초 간격 사용률·메모리), `n1/n4-pods.txt`.
