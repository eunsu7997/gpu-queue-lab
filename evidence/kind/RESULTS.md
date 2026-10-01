# kind 클러스터 실험 결과 (2026-10-01)

환경: Windows 11 + Docker Desktop 29.8.0 (WSL2), kind v0.33.0 (k8s v1.37.0, control-plane 1 + worker 2),
워커당 가짜 `nvidia.com/gpu` 2개 (`scripts/01-fake-gpu.ps1`), Kueue v0.20.0.
KWOK 시뮬과 달리 **진짜 kubelet이 진짜 컨테이너(busybox sleep)를 실행**합니다.
재현: `scripts/00`~`03` 실행 후 `OUT=evidence/kind sim/run-all.sh` (Git Bash). 작업 길이는 시뮬과 같음 (S1/S4 120초, S2 60초, S3 90초/high 30초).

## KWOK 시뮬 vs kind

같은 조건: team-a가 GPU 1개짜리 작업 4개 제출, team-b는 쉬는 중.

| 지표 | 시뮬: cohort 있음 | **kind: cohort 있음** | 시뮬: 엄격한 할당량 | **kind: 엄격한 할당량** |
|---|---|---|---|---|
| 작업 4개 모두 끝난 시간 | 121초 | **124초** | 243초 | **250초** |
| 평균 대기시간 | 0초 | **0초** | 61초 | **62초** |
| 최대 대기시간 | 0초 | **0초** | 122초 | **125초** |
| 평균 GPU 사용률 | 98% | **98%** | 50% | **50%** |

| 시나리오 | 시뮬 | kind |
|---|---|---|
| S2 team-b 대기시간 (회수) | 1초, 2초 | **1초, 3초** |
| S2 team-a 선점 | 2건, 93~94초 뒤 재실행 | **2건, 101~102초 뒤 재실행** |
| S2 전체 완료 | 215초 | **226초** |
| S2 구간 GPU 사용률 | 77% | **77%** |
| S3 high 대기시간 | 1초 | **1초** |
| S3 team-a low 선점 | 1건 | **1건 (56초 뒤 재실행)** |
| S3 team-b 영향 | 없음 | **없음** |

→ 결론과 숫자가 시뮬과 같습니다. 빌려 쓰기로 완료 시간이 약 절반(250초 → 124초), GPU 사용률이 50% → 98%.
kind 쪽이 3~11초씩 긴 이유는 진짜 Pod 생성·컨테이너 시작·종료 시간(작업당 run_s 123~125초 vs sleep 120초)입니다.

Kueue 판단 근거(`events.txt`):
- S2: `Preempted ... due to reclamation within the cohort; preemptor path: /gpu-pool/team-b-cq`
- S3: `Preempted ... due to prioritization in the ClusterQueue`

## 진행 중 겪은 문제 (트러블슈팅 기록)

1. **`kind load docker-image` 실패** (`ctr: content digest ... not found`): Docker Desktop의 containerd 이미지 저장소와 kind의 멀티 플랫폼 import가 안 맞음. 노드 안에서 `docker exec <node> crictl pull busybox:1.36`으로 미리 받아 해결.
2. **실험 중 kubectl 대상이 바뀜**: 같은 PC에서 다른 kind 클러스터가 만들어지며 `~/.kube/config`의 current-context가 바뀌어, 결과 캡처가 엉뚱한 클러스터를 조회하고 멈춤. `kind get kubeconfig --name gpuq`로 전용 kubeconfig를 만들고 `KUBECONFIG`로 고정해 재실행.
   (`events.txt`에는 이 중단된 1차 실행의 이벤트(약 34분 전)도 섞여 있습니다. 숫자는 `workloads.json`/`report.csv` 기준.)
3. 클러스터 생성 직후 노드가 NotReady일 때 GPU 패치를 하면 `allocatable`이 잠깐 `<none>`으로 보이지만, kubelet이 Ready가 되면 2로 채워짐.

그래프(`gpu-usage.csv` → `tools/plot_usage.py`)는 이 PC에 matplotlib이 없어 아직 그리지 않았습니다.
