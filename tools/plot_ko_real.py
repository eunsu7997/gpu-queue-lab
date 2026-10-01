"""Korean charts for the kind reproduction and the RTX 4060 time-slicing run
(used on the Notion page). Needs matplotlib and the NanumGothic font. Run from the repo root:
    python tools/plot_ko_real.py   # writes evidence/kind/ko/*.png, evidence/real-gpu/ko/*.png
"""
import csv, glob, json, os
from collections import defaultdict
from datetime import datetime
import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager as fm
import matplotlib.pyplot as plt
for f in glob.glob(os.path.expanduser("~/.fonts/NanumGothic*.ttf")): fm.fontManager.addfont(f)
plt.rcParams.update({"font.family":"NanumGothic","axes.unicode_minus":False,
  "axes.edgecolor":"#c9c8c3","axes.labelcolor":"#52514e","xtick.color":"#52514e","ytick.color":"#52514e",
  "axes.spines.top":False,"axes.spines.right":False,"figure.facecolor":"#fcfcfb","axes.facecolor":"#fcfcfb"})
BLUE, ORANGE, GRAY, INK, MUTED = "#2a78d6", "#eb6834", "#b9b8b2", "#0b0b0b", "#52514e"
KIND, REAL = "evidence/kind/", "evidence/real-gpu/"
os.makedirs(KIND + "ko", exist_ok=True); os.makedirs(REAL + "ko", exist_ok=True)

def load(path):
    per = defaultdict(dict)
    for r in csv.DictReader(open(path)):
        per[datetime.strptime(r["time"], "%Y-%m-%dT%H:%M:%SZ")][r["cluster_queue"]] = int(r["gpus_in_use"])
    ts = sorted(per); t0 = ts[0]
    return [(t-t0).total_seconds() for t in ts], [sum(per[t].values()) for t in ts]

def hbars(ax, labels, vals, colors, fmt, title, hint):
    bars = ax.barh(labels, vals, color=colors, height=0.55)
    ax.invert_yaxis()
    for b, v in zip(bars, vals):
        ax.text(v + max(vals)*0.02, b.get_y()+b.get_height()/2, fmt.format(v), va="center", color=INK, fontsize=12, fontweight="bold")
    ax.set_xlim(0, max(vals)*1.3); ax.set_xticks([]); ax.spines["bottom"].set_visible(False)
    ax.set_title(title, loc="left", color=INK, fontsize=12, fontweight="bold")
    ax.text(0, -0.2, hint, transform=ax.transAxes, color=MUTED, fontsize=9)
    ax.tick_params(axis="y", length=0, labelsize=11)

# 1. sim vs kind: makespan, grouped bars
fig, ax = plt.subplots(figsize=(9, 3.9))
groups = ["빌려 쓰기 있음", "고정 할당"]
sim, kind = [121, 243], [124, 250]  # evidence/sim/RESULTS.md, evidence/kind/RESULTS.md
y = range(len(groups)); h = 0.36
for off, vals, color, label in [(-h/2, sim, GRAY, "가상 서버 (KWOK)"), (h/2, kind, BLUE, "집 PC kind (진짜 컨테이너)")]:
    bars = ax.barh([i+off for i in y], vals, height=h, color=color, label=label)
    for b, v in zip(bars, vals):
        ax.text(v + 4, b.get_y()+b.get_height()/2, f"{v}초", va="center", color=INK, fontsize=11, fontweight="bold")
ax.set_yticks(list(y)); ax.set_yticklabels(groups, fontsize=11); ax.invert_yaxis()
ax.set_xlim(0, 300); ax.set_xticks([]); ax.spines["bottom"].set_visible(False); ax.tick_params(axis="y", length=0)
ax.set_title("작업 4개가 모두 끝난 시간: 가상 서버와 진짜 환경이 같은 결론", loc="left", color=INK, fontsize=13, fontweight="bold")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=2, frameon=False)
fig.tight_layout(); fig.savefig(KIND + "ko/ko-sim-vs-kind.png", dpi=170)

# 2. kind: GPUs in use over time
fig, ax = plt.subplots(figsize=(9, 3.6))
for path, label, color, done in [(KIND+"s1-clean/gpu-usage.csv","빌려 쓰기 있음",BLUE,124),(KIND+"s4/gpu-usage.csv","고정 할당",ORANGE,250)]:
    xs, tot = load(path)
    ax.step(xs, tot, where="post", color=color, linewidth=2.2)
    last = max(i for i,v in enumerate(tot) if v)
    ax.annotate(f"{label} · {done}초에 완료", xy=(xs[last], tot[last]), xytext=(6, 8), textcoords="offset points", color=INK, fontsize=10)
ax.axhline(4, color="#c9c8c3", linestyle="--", linewidth=1); ax.text(1, 4.08, "전체 GPU 4개", color=MUTED, fontsize=9)
ax.set_ylim(0, 4.8); ax.set_yticks([0,1,2,3,4]); ax.set_xlabel("시간 (초)"); ax.set_ylabel("사용 중인 GPU 개수", labelpad=10); ax.set_axisbelow(True)
ax.set_title("집 PC kind에서도 같은 모양: 빌려 쓰면 4개를 다 씀", loc="left", color=INK, fontsize=13, fontweight="bold")
ax.grid(axis="y", color="#ecebe7"); fig.tight_layout(); fig.savefig(KIND + "ko/ko-usage.png", dpi=170)

# 3. real GPU: solo vs 4-way time-slicing
n1 = [json.loads(l) for l in open(REAL + "n1.jsonl")]
n4 = [json.loads(l) for l in open(REAL + "n4.jsonl")]
solo_s = n1[0]["train_s"]; solo_tp = n1[0]["steps_per_s"]
four_tp = sum(j["steps_per_s"] for j in n4)
four_done = max(j["end"] for j in n4) - min(j["start"] for j in n4)
fig, axes = plt.subplots(1, 2, figsize=(9, 3.4))
labels = ["하나씩 차례로", "4개 동시에 (4조각)"]
hbars(axes[0], labels, [round(solo_s*4), round(four_done)], [BLUE, ORANGE], "{:.0f}초", "작업 4개가 모두 끝난 시간", "짧을수록 좋음")
hbars(axes[1], labels, [solo_tp, round(four_tp, 1)], [BLUE, ORANGE], "{:.1f} step/s", "GPU 전체 처리량", "높을수록 좋음")
fig.suptitle("RTX 4060 한 장을 4조각으로 나눠 학습 4개를 동시에 돌리면", x=0.02, ha="left", color=INK, fontsize=13, fontweight="bold")
fig.tight_layout(); fig.savefig(REAL + "ko/ko-timeslicing.png", dpi=170)
print("ok", round(four_tp, 1), round(four_done))
