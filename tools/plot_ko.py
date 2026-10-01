"""Korean versions of the result charts (used on the Notion page).
Needs matplotlib and the NanumGothic font. Run from the repo root:
    python tools/plot_ko.py   # writes evidence/sim/ko/*.png
"""
import csv, sys
from collections import defaultdict
from datetime import datetime
import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager as fm
import matplotlib.pyplot as plt
import glob, os
for f in glob.glob(os.path.expanduser("~/.fonts/NanumGothic*.ttf")): fm.fontManager.addfont(f)
plt.rcParams.update({"font.family":"NanumGothic","axes.unicode_minus":False,
  "axes.edgecolor":"#c9c8c3","axes.labelcolor":"#52514e","xtick.color":"#52514e","ytick.color":"#52514e",
  "axes.spines.top":False,"axes.spines.right":False,"figure.facecolor":"#fcfcfb","axes.facecolor":"#fcfcfb"})
BLUE, ORANGE, INK, MUTED = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e"
EV = "evidence/sim/"
OUT = "evidence/sim/ko/"

def load(path):
    per = defaultdict(dict)
    for r in csv.DictReader(open(path)):
        per[datetime.strptime(r["time"], "%Y-%m-%dT%H:%M:%SZ")][r["cluster_queue"]] = int(r["gpus_in_use"])
    ts = sorted(per); t0 = ts[0]
    return [(t-t0).total_seconds() for t in ts], {q:[per[t].get(q,0) for t in ts] for q in ["team-a-cq","team-b-cq"]}

# 1. comparison bars: two panels, one axis each
fig, axes = plt.subplots(1, 2, figsize=(9, 3.4))
data = [("작업 4개가 모두 끝난 시간 (초)", [121, 243], "{:.0f}초", "짧을수록 좋음"),
        ("평균 GPU 사용률 (%)", [98, 50], "{:.0f}%", "높을수록 좋음")]
labels = ["빌려 쓰기 있음", "고정 할당"]
for ax, (title, vals, fmt, hint) in zip(axes, data):
    bars = ax.barh(labels, vals, color=[BLUE, "#b9b8b2"], height=0.55)
    ax.invert_yaxis()
    for b, v in zip(bars, vals):
        ax.text(v + max(vals)*0.02, b.get_y()+b.get_height()/2, fmt.format(v), va="center", color=INK, fontsize=12, fontweight="bold")
    ax.set_xlim(0, max(vals)*1.25); ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    ax.set_title(title, loc="left", color=INK, fontsize=12, fontweight="bold")
    ax.text(0, -0.25, hint, transform=ax.transAxes, color=MUTED, fontsize=9)
    ax.tick_params(axis="y", length=0, labelsize=11)
fig.tight_layout(); fig.savefig(OUT + "ko-compare.png", dpi=170)

# 2. GPUs in use over time, two lines
fig, ax = plt.subplots(figsize=(9, 3.6))
for path, label, color in [(EV+"s1-clean/gpu-usage.csv","빌려 쓰기 있음",BLUE),(EV+"s4/gpu-usage.csv","고정 할당",ORANGE)]:
    xs, qs = load(path); tot = [a+b for a,b in zip(*qs.values())]
    ax.step(xs, tot, where="post", color=color, linewidth=2.2)
    last = max(i for i,v in enumerate(tot) if v)
    done = {"빌려 쓰기 있음": 121, "고정 할당": 243}[label]  # makespan from Kueue workload timestamps
    ax.annotate(f"{label} · {done}초에 완료", xy=(xs[last], tot[last]), xytext=(6, 8), textcoords="offset points", color=INK, fontsize=10)
ax.axhline(4, color="#c9c8c3", linestyle="--", linewidth=1); ax.text(1, 4.08, "전체 GPU 4개", color=MUTED, fontsize=9)
ax.set_ylim(0, 4.8); ax.set_yticks([0,1,2,3,4]); ax.set_xlabel("시간 (초)"); ax.set_ylabel("사용 중인 GPU 개수", labelpad=10); ax.set_axisbelow(True)
ax.set_title("같은 작업 4개, GPU를 얼마나 쓰고 있었나", loc="left", color=INK, fontsize=13, fontweight="bold")
ax.grid(axis="y", color="#ecebe7"); fig.tight_layout(); fig.savefig(OUT + "ko-usage.png", dpi=170)

# 3. reclaim stacked
xs, qs = load(EV+"s1-s2/gpu-usage.csv")
last = max(i for i,(a,b) in enumerate(zip(*qs.values())) if a+b)
xs = xs[:last+3]; a = qs["team-a-cq"][:last+3]; b = qs["team-b-cq"][:last+3]
fig, ax = plt.subplots(figsize=(9, 3.6))
ax.stackplot(xs, a, b, step="post", colors=[BLUE, ORANGE], labels=["A팀", "B팀"], edgecolor="#fcfcfb", linewidth=1)
ax.axhline(2, color="#fcfcfb", linestyle=":", linewidth=1.2); ax.text(xs[-1]-4, 1.75, "A팀 기본 몫 2개", color="#ffffff", fontsize=10, ha="right")
ax.annotate("B팀 등장 → 1~2초 만에\nA팀이 빌린 GPU 2개 반납", xy=(32, 3), xytext=(60, 4.3), color=INK, fontsize=10, arrowprops=dict(arrowstyle="->", color=MUTED))
ax.annotate("B팀 끝나자\nA팀이 다시 빌려 씀", xy=(96, 3.5), xytext=(130, 3.3), color=INK, fontsize=10, arrowprops=dict(arrowstyle="->", color=MUTED))
ax.set_ylim(0, 5); ax.set_yticks([0,1,2,3,4]); ax.set_xlabel("시간 (초)"); ax.set_ylabel("사용 중인 GPU 개수", labelpad=10); ax.set_axisbelow(True)
ax.set_title("빌려 쓰다가 주인이 오면 돌려주기", loc="left", color=INK, fontsize=13, fontweight="bold")
ax.legend(loc="upper right", frameon=False, ncol=2); ax.grid(axis="y", color="#ecebe7")
fig.tight_layout(); fig.savefig(OUT + "ko-reclaim.png", dpi=170)
print("ok")
