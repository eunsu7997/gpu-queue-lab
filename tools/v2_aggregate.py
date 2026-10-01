"""Average the v2 runs (evidence/real-gpu-v2/**/summary.json) into tables and charts.

  python tools/v2_aggregate.py            # prints markdown tables, writes summary.csv + charts
"""
import csv
import glob
import json
import os
import statistics
import sys

ROOT = "evidence/real-gpu-v2"


def load():
    runs = []
    for p in sorted(glob.glob(os.path.join(ROOT, "*", "*", "r*", "summary.json"))):
        with open(p, encoding="utf-8") as fh:
            s = json.load(fh)
        if s.get("ok"):
            runs.append(s)
        else:
            print("skip (not ok):", p, file=sys.stderr)
    return runs


def ms(vals):
    """'mean ± sd' (sample sd, n-1). Values are seconds or %."""
    vals = [v for v in vals if v is not None]
    if not vals:
        return None, None, 0
    sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
    return statistics.mean(vals), sd, len(vals)


def fmt(m, sd, unit=""):
    return "-" if m is None else f"{m:.1f}{unit} ± {sd:.1f}"


def group(runs, exp):
    out = {}
    for r in runs:
        if r["exp"] == exp:
            out.setdefault(r["variant"], []).append(r)
    return out


METRICS = {
    "mix": [("makespan_s", "8개 모두 끝난 시간", lambda r: r["team_a"]["makespan_s"], "초"),
            ("avg_jct_s", "작업당 평균 완료 시간", lambda r: r["team_a"]["avg_jct_s"], "초"),
            ("avg_wait_s", "평균 대기", lambda r: r["team_a"]["avg_wait_s"], "초"),
            ("gpu_util", "GPU 사용률", lambda r: r["gpu_util_avg"], "%")],
    "ckpt": [("team_a_makespan_s", "team-a 4개 끝난 시간", lambda r: r["team_a"]["makespan_s"], "초"),
             ("lost_s", "다시 한 학습 (작업 슬롯 초)", lambda r: r["lost_s"], "초"),
             ("evictions", "선점 횟수", lambda r: r["evictions"], ""),
             ("ckpt_overhead_s", "체크포인트 저장 시간 합", lambda r: r["ckpt_overhead_s"], "초"),
             ("team_b_wait_s", "team-b 평균 대기", lambda r: r["team_b"].get("avg_wait_s"), "초")],
}
ORDER = {
    "mix": ["mixed-strict", "mixed-borrow", "small-strict", "small-borrow", "large-strict", "large-borrow"],
    "ckpt": ["none", "periodic", "periodic+sigterm"],
}


def table(runs, exp):
    g = group(runs, exp)
    cols = METRICS[exp]
    lines = ["| 조건 | n | " + " | ".join(c[1] for c in cols) + " |",
             "|---|---|" + "---|" * len(cols)]
    rows = []
    for v in [v for v in ORDER[exp] if v in g] + [v for v in g if v not in ORDER[exp]]:
        cells, row = [], {"exp": exp, "variant": v, "n": len(g[v])}
        for key, _, get, unit in cols:
            m, sd, _ = ms([get(r) for r in g[v]])
            cells.append(fmt(m, sd, unit))
            row[key + "_mean"] = None if m is None else round(m, 2)
            row[key + "_sd"] = None if sd is None else round(sd, 2)
        lines.append(f"| {v} | {len(g[v])} | " + " | ".join(cells) + " |")
        rows.append(row)
    return "\n".join(lines), rows


def charts(rows):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except ImportError:
        print("matplotlib not installed, skipping charts", file=sys.stderr)
        return
    for f in ("Malgun Gothic", "NanumGothic", "AppleGothic"):
        if any(f == x.name for x in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = f
            break
    plt.rcParams["axes.unicode_minus"] = False
    blue, gray, orange = "#2563eb", "#9ca3af", "#ea580c"

    mix = {r["variant"]: r for r in rows if r["exp"] == "mix"}
    if mix:
        labels = {"mixed": "섞음\n(소2:중1:대1)", "small": "작은 작업만", "large": "큰 작업만"}
        groups = [k for k in labels if f"{k}-strict" in mix and f"{k}-borrow" in mix]
        fig, ax = plt.subplots(figsize=(7, 4))
        xs = range(len(groups))
        for off, quota, color, name in ((-0.2, "strict", gray, "고정 할당 (2칸)"), (0.2, "borrow", blue, "빌려 쓰기 (4칸)")):
            m = [mix[f"{g}-{quota}"]["makespan_s_mean"] for g in groups]
            sd = [mix[f"{g}-{quota}"]["makespan_s_sd"] for g in groups]
            bars = ax.bar([x + off for x in xs], m, 0.4, yerr=sd, capsize=4, color=color, label=name)
            ax.bar_label(bars, labels=[f"{v:.0f}초" for v in m], padding=10, fontsize=9)
        ax.set_xticks(list(xs), [labels[g] for g in groups])
        ax.set_ylabel("작업 8개 모두 끝난 시간 (초, 3회 평균 ± 표준편차)")
        ax.set_title("실제 PyTorch 작업: 빌려 쓰기 효과는 작업 크기에 따라 다르다")
        ax.legend(frameon=False)
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        fig.savefig(os.path.join(ROOT, "mix-makespan.png"), dpi=150)
        plt.close(fig)

    ck = {r["variant"]: r for r in rows if r["exp"] == "ckpt"}
    if ck:
        order = [v for v in ORDER["ckpt"] if v in ck]
        names = {"none": "체크포인트 없음", "periodic": "15초마다 저장", "periodic+sigterm": "15초마다 +\n종료 신호 때 저장"}
        fig, ax = plt.subplots(figsize=(7, 4))
        m = [ck[v]["lost_s_mean"] for v in order]
        sd = [ck[v]["lost_s_sd"] for v in order]
        bars = ax.bar([names[v] for v in order], m, 0.5, yerr=sd, capsize=4,
                      color=[orange if v == "none" else blue for v in order])
        ax.bar_label(bars, labels=[f"{v:.0f}초" for v in m], padding=10, fontsize=9)
        ax.set_ylabel("선점으로 다시 한 학습 (작업 슬롯 초, 3회 평균)")
        ax.set_title("선점 손실: 체크포인트로 얼마나 줄어드나")
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        fig.savefig(os.path.join(ROOT, "ckpt-lost.png"), dpi=150)
        plt.close(fig)


def main():
    runs = load()
    all_rows = []
    for exp in ("mix", "ckpt"):
        md, rows = table(runs, exp)
        if rows:
            print(f"\n## {exp}\n\n{md}")
            all_rows += rows
    if all_rows:
        keys = sorted({k for r in all_rows for k in r}, key=lambda k: (k not in ("exp", "variant", "n"), k))
        with open(os.path.join(ROOT, "summary.csv"), "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            w.writerows(all_rows)
        charts(all_rows)


if __name__ == "__main__":
    main()
