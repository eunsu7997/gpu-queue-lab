"""v2 experiments on the real RTX 4060 (k3s on WSL2, time-slicing replicas: 4).

Runs real PyTorch training jobs (tools/train_job.py) through Kueue and measures
completion time, wait time, GPU utilisation and, after preemption, how much training
had to be redone. Run inside WSL2 from the repo root:

  python3 tools/v2_run.py mix --quota borrow --mix mixed --rep 1
  python3 tools/v2_run.py ckpt --ckpt none --rep 1

Each run writes evidence/real-gpu-v2/<exp>/<variant>/r<rep>/:
  summary.json   metrics for this run
  attempts.jsonl every start / ckpt / sigterm / end line from every pod
  workloads.json Kueue Workloads at the end
  nvidia-smi.csv 1 s GPU utilisation and memory samples
"""
import argparse
import json
import os
import subprocess
import sys
import time

K = ["k3s", "kubectl"]
IMAGE = os.environ.get("IMAGE", "pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime")
HOST_DIR = "/var/lib/gpuq"  # hostPath on the single k3s node; survives pod deletion
OUT_ROOT = "evidence/real-gpu-v2"

# Steps chosen so each job takes ~45 s alone on the RTX 4060 (measured, see RESULTS.md).
STEPS = {"small": 11000, "medium": 6000, "large": 1300}
MIXES = {
    # submission order is fixed so every repetition sees the same queue
    "mixed": ["large", "small", "medium", "small", "large", "small", "medium", "small"],
    "small": ["small"] * 8,
    "large": ["large"] * 8,
}
CKPT = {  # variant -> (CKPT_EVERY_S, CKPT_ON_SIGTERM)
    "none": (0, 0),
    "periodic": (15, 0),
    "periodic+sigterm": (15, 1),
}


def kubectl(*args, stdin=None, check=True):
    res = subprocess.run(K + list(args), input=stdin, capture_output=True, text=True)
    if check and res.returncode != 0:
        sys.exit(f"kubectl {' '.join(args)} failed:\n{res.stderr}")
    return res.stdout


def apply_quota(quota):
    f = "manifests/kueue/02-cluster-queues.yaml" if quota == "borrow" else "manifests/kueue/variants/no-borrowing.yaml"
    kubectl("apply", "-f", f)


def job_manifest(name, team, size, run, steps=None, ckpt=(0, 0), priority="low"):
    every, on_term = ckpt
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": name, "namespace": team,
            "labels": {"kueue.x-k8s.io/queue-name": "gpu-queue", "kueue.x-k8s.io/priority-class": priority,
                       "gpuq.dev/team": team, "gpuq.dev/run": run, "gpuq.dev/size": size},
        },
        "spec": {
            "suspend": True,
            "backoffLimit": 0,
            "template": {
                "metadata": {"labels": {"gpuq.dev/team": team, "gpuq.dev/run": run}},
                "spec": {
                    "runtimeClassName": "nvidia",
                    "restartPolicy": "Never",
                    "terminationGracePeriodSeconds": 10,
                    "containers": [{
                        "name": "train",
                        "image": IMAGE,
                        "imagePullPolicy": "IfNotPresent",
                        "command": ["python", "/code/train_job.py"],
                        "env": [
                            {"name": "SIZE", "value": size},
                            {"name": "STEPS", "value": str(steps or STEPS[size])},
                            {"name": "JOB_NAME", "value": name},
                            {"name": "CKPT_DIR", "value": f"/ckpt/{name}"},
                            {"name": "CKPT_EVERY_S", "value": str(every)},
                            {"name": "CKPT_ON_SIGTERM", "value": str(on_term)},
                        ],
                        # requests only count against the Kueue quota; no memory limit so torch is not OOM-killed
                        "resources": {"requests": {"cpu": "100m", "memory": "64Mi"},
                                      "limits": {"nvidia.com/gpu": "1"}},
                        "volumeMounts": [{"name": "code", "mountPath": "/code"},
                                         {"name": "ckpt", "mountPath": "/ckpt"}],
                    }],
                    "volumes": [
                        {"name": "code", "configMap": {"name": "train-job"}},
                        {"name": "ckpt", "hostPath": {"path": f"{HOST_DIR}/{run}", "type": "DirectoryOrCreate"}},
                    ],
                },
            },
        },
    }


def submit(manifests):
    kubectl("apply", "-f", "-", stdin=json.dumps({"apiVersion": "v1", "kind": "List", "items": manifests}))


def reset():
    for ns in ("team-a", "team-b"):
        kubectl("delete", "jobs", "--all", "-n", ns, "--wait=true", check=False)
    for ns in ("team-a", "team-b"):
        cm = kubectl("create", "configmap", "train-job", "-n", ns, "--from-file=tools/train_job.py",
                     "--dry-run=client", "-o", "yaml")
        kubectl("apply", "-f", "-", stdin=cm)


def wait_done(run, n_jobs, timeout):
    end = time.time() + timeout
    while time.time() < end:
        js = json.loads(kubectl("get", "jobs", "-A", "-l", f"gpuq.dev/run={run}", "-o", "json"))["items"]
        done = sum(1 for j in js if j.get("status", {}).get("succeeded"))
        failed = [j["metadata"]["name"] for j in js if j.get("status", {}).get("failed")]
        if failed:
            print("FAILED jobs:", failed)
            return False
        if len(js) == n_jobs and done == n_jobs:
            return True
        time.sleep(2)
    print("timeout")
    return False


def read_attempts(run):
    rows = []
    base = f"{HOST_DIR}/{run}"
    for job in sorted(os.listdir(base)):
        p = os.path.join(base, job, "attempts.jsonl")
        if os.path.exists(p):
            with open(p) as fh:
                rows += [json.loads(line) for line in fh if line.strip()]
    return rows


def smi_avg(path, t0, t1):
    vals = []
    with open(path) as fh:
        for line in fh:
            try:
                ts, util, mem = [x.strip() for x in line.split(",")]
                ts = float(ts)
            except ValueError:
                continue
            if t0 <= ts <= t1:
                vals.append((float(util), float(mem)))
    if not vals:
        return None, None
    return (round(sum(v[0] for v in vals) / len(vals), 1), round(max(v[1] for v in vals)))


def metrics(rows, submitted, t0):
    """Per-job and per-run numbers from the attempt log."""
    jobs = {}
    for r in rows:
        jobs.setdefault(r["job"], []).append(r)
    per_job, lost_s, ckpt_s, evictions = [], 0.0, 0.0, 0
    for name, ev in jobs.items():
        ev.sort(key=lambda r: r["t"])
        starts = [r for r in ev if r["event"] == "start"]
        end = next((r for r in ev if r["event"] == "end"), None)
        # redone work: steps trained after the last saved point of an attempt, before the kill
        for i, s in enumerate(starts):
            kill = next((r for r in ev if r["event"] == "sigterm" and r["attempt"] == s["attempt"]), None)
            if not kill:
                continue
            evictions += 1
            nxt = starts[i + 1] if i + 1 < len(starts) else None
            resumed = nxt["resume_step"] if nxt else s["resume_step"]
            rate = (kill["step"] - s["resume_step"]) / max(kill["run_s"], 1e-6)  # steps/s in that attempt
            lost_s += (kill["step"] - resumed) / rate if rate else 0
        ckpt_s += sum(r.get("save_s") or 0 for r in ev if r["event"] == "ckpt")
        ckpt_s += sum(r.get("saved_s") or 0 for r in ev if r["event"] == "sigterm")
        sub = submitted[name]
        per_job.append({
            "job": name, "size": ev[0]["size"], "team": "team-b" if name.startswith("b-") else "team-a",
            "submitted": round(sub - t0, 1),
            "wait_s": round(starts[0]["t"] - sub, 1) if starts else None,
            "jct_s": round(end["t"] - sub, 1) if end else None,
            "attempts": len(starts),
        })
    return per_job, round(lost_s, 1), round(ckpt_s, 2), evictions


def team_stats(per_job, team, t0, submitted):
    js = [j for j in per_job if j["team"] == team and j["jct_s"] is not None]
    if not js:
        return {}
    return {
        "jobs": len(js),
        "makespan_s": round(max(j["submitted"] + j["jct_s"] for j in js) - min(j["submitted"] for j in js), 1),
        "avg_jct_s": round(sum(j["jct_s"] for j in js) / len(js), 1),
        "avg_wait_s": round(sum(j["wait_s"] for j in js) / len(js), 1),
    }


def run(exp, variant, rep, plan, quota, timeout):
    """plan: list of (delay_s, manifest)."""
    run_id = f"{exp}-{variant.replace('+', '-')}-r{rep}-{int(time.time())}"
    out = os.path.join(OUT_ROOT, exp, variant, f"r{rep}")
    os.makedirs(out, exist_ok=True)
    apply_quota(quota)
    reset()
    for _, m in plan:
        m["metadata"]["labels"]["gpuq.dev/run"] = run_id
        m["spec"]["template"]["metadata"]["labels"]["gpuq.dev/run"] = run_id
        m["spec"]["template"]["spec"]["volumes"][1]["hostPath"]["path"] = f"{HOST_DIR}/{run_id}"

    smi_path = os.path.join(out, "nvidia-smi.csv")
    smi = subprocess.Popen(["bash", "-c",
                            "while :; do echo \"$(date +%s.%N),$(nvidia-smi --query-gpu=utilization.gpu,memory.used "
                            "--format=csv,noheader,nounits)\"; sleep 1; done"],
                           stdout=open(smi_path, "w"))
    t0 = time.time()
    submitted = {}
    for delay, m in sorted(plan, key=lambda p: p[0]):
        while time.time() - t0 < delay:
            time.sleep(0.2)
        submit([m])
        submitted[m["metadata"]["name"]] = time.time()
        print(f"+{time.time() - t0:5.1f}s submitted {m['metadata']['namespace']}/{m['metadata']['name']}")
    ok = wait_done(run_id, len(plan), timeout)
    t1 = time.time()
    smi.terminate()

    with open(os.path.join(out, "workloads.json"), "w") as fh:
        fh.write(kubectl("get", "workloads.kueue.x-k8s.io", "-A", "-o", "json"))
    rows = read_attempts(run_id)
    with open(os.path.join(out, "attempts.jsonl"), "w") as fh:
        fh.writelines(json.dumps(r) + "\n" for r in rows)
    per_job, lost_s, ckpt_s, evictions = metrics(rows, submitted, t0)
    ends = [r["t"] for r in rows if r["event"] == "end"]
    util, mem = smi_avg(smi_path, t0, max(ends) if ends else t1)
    summary = {
        "exp": exp, "variant": variant, "rep": rep, "run_id": run_id, "ok": ok, "quota": quota,
        "makespan_s": round(max(ends) - t0, 1) if ends else None,
        "team_a": team_stats(per_job, "team-a", t0, submitted),
        "team_b": team_stats(per_job, "team-b", t0, submitted),
        "gpu_util_avg": util, "gpu_mem_max_mb": mem,
        "evictions": evictions, "lost_s": lost_s, "ckpt_overhead_s": ckpt_s,
        "jobs": per_job,
    }
    with open(os.path.join(out, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    print(json.dumps({k: v for k, v in summary.items() if k != "jobs"}))
    return ok


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="exp", required=True)
    m = sub.add_parser("mix", help="exp 1: borrowing vs fixed quota with mixed real jobs")
    m.add_argument("--quota", choices=["borrow", "strict"], required=True)
    m.add_argument("--mix", choices=list(MIXES), default="mixed")
    m.add_argument("--rep", type=int, default=1)
    c = sub.add_parser("ckpt", help="exp 2: preemption with and without checkpoints")
    c.add_argument("--ckpt", choices=list(CKPT), required=True)
    c.add_argument("--rep", type=int, default=1)
    c.add_argument("--b-delay", type=float, default=90, help="seconds before team-b arrives")
    sub.add_parser("warmup", help="pull the image with one short job before measuring")
    a = p.parse_args()

    if a.exp == "warmup":
        plan = [(0, job_manifest("warmup", "team-a", "small", "x", steps=500))]
        return run("warmup", "warmup", 1, plan, "borrow", 1800)
    if a.exp == "mix":
        plan = [(0, job_manifest(f"a-{i:02d}-{s}", "team-a", s, "x"))
                for i, s in enumerate(MIXES[a.mix], 1)]
        ok = run("mix", f"{a.mix}-{a.quota}", a.rep, plan, a.quota, 3600)
    else:
        # team-a fills all 4 slices (2 own + 2 borrowed); team-b reclaims its 2 later
        cfg = CKPT[a.ckpt]
        plan = [(0, job_manifest(f"a-{i:02d}", "team-a", "medium", "x", steps=8000, ckpt=cfg)) for i in range(1, 5)]
        plan += [(a.b_delay, job_manifest(f"b-{i:02d}", "team-b", "medium", "x", steps=4000)) for i in (1, 2)]
        ok = run("ckpt", a.ckpt, a.rep, plan, "borrow", 3600)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
