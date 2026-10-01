"""Plot GPUs in use over time from `gpuq sample` CSVs (needs matplotlib).

usage: python tools/plot_usage.py OUT.png LABEL=path/gpu-usage.csv [LABEL=...]
Each series is the total GPUs in use across all ClusterQueues; with a single
input the per-queue split is stacked instead.
"""
import csv
import sys
from collections import defaultdict
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TOTAL_GPUS = 4


def load(path):
    per_t = defaultdict(dict)
    for row in csv.DictReader(open(path, encoding="utf-8")):
        t = datetime.strptime(row["time"], "%Y-%m-%dT%H:%M:%SZ")
        per_t[t][row["cluster_queue"]] = int(row["gpus_in_use"])
    times = sorted(per_t)
    t0 = times[0]
    xs = [(t - t0).total_seconds() for t in times]
    queues = sorted({q for v in per_t.values() for q in v})
    return xs, {q: [per_t[t].get(q, 0) for t in times] for q in queues}


def main(out, *series):
    fig, ax = plt.subplots(figsize=(8, 3.6))
    if len(series) == 1:
        label, path = series[0].split("=", 1)
        xs, qs = load(path)
        ax.stackplot(xs, *qs.values(), labels=list(qs), step="post", alpha=0.85)
        ax.set_title(f"GPUs in use by queue - {label}")
    else:
        for s in series:
            label, path = s.split("=", 1)
            xs, qs = load(path)
            total = [sum(v) for v in zip(*qs.values())]
            # average only until the last job finished (ignore idle tail)
            last = max((i for i, v in enumerate(total) if v), default=0)
            used = total[: last + 1]
            avg = sum(used) / len(used) / TOTAL_GPUS * 100
            ax.step(xs, total, where="post", label=f"{label} (avg util {avg:.0f}%)", linewidth=2)
        ax.set_title("GPUs in use over time")
    ax.axhline(TOTAL_GPUS, color="gray", linestyle="--", linewidth=1)
    ax.set_ylim(0, TOTAL_GPUS + 0.5)
    ax.set_xlabel("seconds since first sample")
    ax.set_ylabel("GPUs in use (of 4)")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=150)


if __name__ == "__main__":
    main(*sys.argv[1:])
