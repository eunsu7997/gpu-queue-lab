# 실험 시나리오

클러스터 GPU는 총 4개(워커 2대 × 가짜 GPU 2개)이고, team-a와 team-b가 각각 2개씩 소유(nominalQuota)합니다.
두 팀은 같은 cohort `gpu-pool`에 있어서, 상대 팀이 놀고 있으면 최대 2개까지 빌려 쓸 수 있습니다.

모든 명령은 레포 루트에서 실행합니다. 시나리오 사이에는 `scripts/reset-jobs.ps1`로 작업을 지웁니다.

> 아래 "예상 결과"는 Kueue 설계상 기대하는 동작입니다. 실제로 돌린 결과만 "실제 결과" 칸에 적고, 다르면 다른 대로 적습니다. 다른 경우가 오히려 좋은 트러블슈팅 소재입니다.

---

## S1. 빌려 쓰기 (Borrowing)

**질문:** 한 팀이 놀 때 그 팀의 GPU를 다른 팀이 쓸 수 있는가?

```powershell
python -m gpuq sample --seconds 400 --out evidence/s1/gpu-usage.csv   # 별도 창에서
python -m gpuq submit --team team-a --count 4 --duration 300 --prefix s1-a
kubectl get workloads -n team-a -w
```

| | 예상 결과 | 실제 결과 |
|---|---|---|
| team-a 작업 4개 | 4개 모두 Admitted (2개는 team-b 몫을 빌림) | |
| `kubectl get clusterqueue team-a-cq -o yaml`의 borrowed | nvidia.com/gpu 2 | |
| GPU 사용률 | 4/4 = 100% | |

캡처: `scripts/capture.ps1 -Name s1`

## S2. 돌려받기 (Reclaim, 선점)

**질문:** 빌려준 팀이 돌아오면 바로 자기 GPU를 되찾는가?

S1이 끝나기 전에 바로 이어서:

```powershell
python -m gpuq submit --team team-b --count 2 --duration 120 --prefix s2-b
kubectl get workloads -A -w
```

| | 예상 결과 | 실제 결과 |
|---|---|---|
| team-b 작업 2개 대기시간 | 수 초 이내 Admitted | |
| team-a 작업 | 빌린 2개가 Evicted (reason Preempted) 후 다시 대기열로 | |
| 이벤트 | `Preempted` 이벤트 2건 | |
| team-a 선점된 작업 | team-b 작업이 끝난 뒤 다시 Admitted | |

캡처: `scripts/capture.ps1 -Name s2`

## S3. 우선순위 선점 (Priority)

**질문:** 급한 작업(high)이 오면 같은 팀의 덜 급한 작업(low)을 밀어내는가?

```powershell
scripts/reset-jobs.ps1
python -m gpuq submit --team team-b --count 2 --duration 600 --prefix s3-b      # team-b가 자기 몫을 다 씀 (빌릴 여유 없음)
python -m gpuq submit --team team-a --count 2 --duration 600 --prefix s3-low    # team-a 자기 몫 2개 꽉 참
python -m gpuq submit --team team-a --count 1 --duration 60 --priority high --prefix s3-high
```

| | 예상 결과 | 실제 결과 |
|---|---|---|
| s3-high-01 | 몇 초 내 Admitted | |
| s3-low 중 1개 | Evicted (Preempted), 다시 대기 | |
| team-b 작업 | 영향 없음 | |

캡처: `scripts/capture.ps1 -Name s3`

## S4. 비교 실험: cohort 없이 엄격한 할당량

**질문:** 빌려 쓰기가 실제로 얼마나 이득인가? (포트폴리오의 핵심 숫자)

```powershell
scripts/reset-jobs.ps1
scripts/03-apply-queues.ps1 -NoBorrowing
python -m gpuq sample --seconds 700 --out evidence/s4/gpu-usage.csv   # 별도 창에서
python -m gpuq submit --team team-a --count 4 --duration 300 --prefix s4-a
# 끝나면
scripts/capture.ps1 -Name s4
scripts/03-apply-queues.ps1    # 원래 설정으로 복구
```

S1과 같은 작업 4개를 같은 조건으로 넣고 비교합니다. S1은 중간에 S2를 섞었으니, 비교용 "cohort 있음" 값은 S2 없이 S1만 한 번 더 돌려서 얻습니다(`-Name s1-clean`으로 캡처).

| 지표 | cohort 있음 (s1-clean) | cohort 없음 (S4) |
|---|---|---|
| team-a 작업 4개 모두 끝난 시간 | (예상 약 300초) | (예상 약 600초) |
| team-a 평균 대기시간 | | |
| 평균 GPU 사용률 (gpu-usage.csv) | (예상 약 100%) | (예상 약 50%) |

포트폴리오 문장 예: "cohort 기반 GPU 빌려 쓰기로 유휴 GPU를 없애 같은 작업 4개의 완료 시간을 X초 → Y초로 줄였고, 소유 팀이 돌아오면 Z초 안에 선점으로 GPU를 되찾게 했다."

---

## 추가 아이디어 (선택)

- **Fair sharing**: ClusterQueue `fairSharing.weight`로 팀별 가중치를 다르게 주고 대기시간 차이 측정
- **Kueue 메트릭**: Kueue `/metrics`를 Prometheus로 수집해 `kueue_pending_workloads`, 대기시간 히스토그램을 Grafana로 시각화 (KubeLLM-Ops에서 해 본 방식 재사용)
- **실제 GPU**: [real-gpu.md](real-gpu.md)
