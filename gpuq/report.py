"""Turn `kubectl get workloads -A -o json` into per-job scheduling stats."""
from datetime import datetime

from .jobs import GPU_RESOURCE


def _ts(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def _condition(wl, ctype):
    for c in wl.get("status", {}).get("conditions", []) or []:
        if c.get("type") == ctype:
            return c
    return None


def _gpus(wl):
    total = 0
    for ps in wl.get("spec", {}).get("podSets", []) or []:
        for ctr in ps.get("template", {}).get("spec", {}).get("containers", []) or []:
            res = ctr.get("resources", {})
            val = res.get("limits", {}).get(GPU_RESOURCE) or res.get("requests", {}).get(GPU_RESOURCE)
            if val:
                total += int(val) * int(ps.get("count", 1))
    return total


def _evictions(wl):
    stats = wl.get("status", {}).get("schedulingStats", {}) or {}
    return sum(e.get("count", 0) for e in stats.get("evictions", []) or [])


def summarize(workloads_json):
    """Return one row per workload, oldest first."""
    rows = []
    for wl in workloads_json.get("items", []):
        meta = wl.get("metadata", {})
        owners = meta.get("ownerReferences") or [{}]
        created = _ts(meta.get("creationTimestamp"))
        admitted = _condition(wl, "Admitted")
        finished = _condition(wl, "Finished")
        admitted_at = _ts(admitted["lastTransitionTime"]) if admitted and admitted.get("status") == "True" else None
        finished_at = _ts(finished["lastTransitionTime"]) if finished and finished.get("status") == "True" else None

        if finished_at:
            state = "Finished"
        elif admitted_at:
            state = "Running"
        else:
            state = "Pending"

        rows.append({
            "job": owners[0].get("name", meta.get("name")),
            "team": meta.get("namespace"),
            "priority": wl.get("spec", {}).get("priorityClassRef", {}).get("name")
                        or meta.get("labels", {}).get("kueue.x-k8s.io/priority-class", ""),
            "gpus": _gpus(wl),
            "state": state,
            "cluster_queue": (wl.get("status", {}).get("admission") or {}).get("clusterQueue", ""),
            "created": created,
            # Admitted.lastTransitionTime is the *latest* admission, so for a
            # job that was preempted and re-admitted this includes the requeue.
            "wait_s": (admitted_at - created).total_seconds() if admitted_at and created else None,
            "run_s": (finished_at - admitted_at).total_seconds() if finished_at and admitted_at else None,
            "evictions": _evictions(wl),
        })
    rows.sort(key=lambda r: (r["created"] or datetime.min, r["job"]))
    return rows


def team_stats(rows):
    """Aggregate wait time and evictions per team."""
    out = {}
    for r in rows:
        t = out.setdefault(r["team"], {"jobs": 0, "admitted": 0, "evictions": 0, "waits": []})
        t["jobs"] += 1
        t["evictions"] += r["evictions"]
        if r["wait_s"] is not None:
            t["admitted"] += 1
            t["waits"].append(r["wait_s"])
    for t in out.values():
        w = sorted(t.pop("waits"))
        t["avg_wait_s"] = round(sum(w) / len(w), 1) if w else None
        t["max_wait_s"] = w[-1] if w else None
    return out


def _fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.0f}"
    return str(v)


def to_markdown(rows):
    cols = ["job", "team", "priority", "gpus", "state", "wait_s", "run_s", "evictions"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        lines.append("| " + " | ".join(_fmt(r[c]) for c in cols) + " |")
    lines += ["", "| team | jobs | admitted | avg_wait_s | max_wait_s | evictions |", "|---|---|---|---|---|---|"]
    for team, s in sorted(team_stats(rows).items()):
        lines.append(f"| {team} | {s['jobs']} | {s['admitted']} | {_fmt(s['avg_wait_s'])} "
                     f"| {_fmt(s['max_wait_s'])} | {s['evictions']} |")
    return "\n".join(lines)


def to_csv(rows, fh):
    import csv
    cols = ["job", "team", "priority", "gpus", "state", "cluster_queue", "created", "wait_s", "run_s", "evictions"]
    w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({**r, "created": r["created"].isoformat() if r["created"] else ""})


def gpu_in_use(workloads_json):
    """GPUs currently held by admitted, unfinished workloads, per cluster queue."""
    used = {}
    for r in summarize(workloads_json):
        if r["state"] == "Running":
            used[r["cluster_queue"]] = used.get(r["cluster_queue"], 0) + r["gpus"]
    return used
