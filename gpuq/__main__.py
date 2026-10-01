"""CLI: python -m gpuq {render,submit,report,sample} ..."""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone

from . import jobs, report


def kubectl(*args, stdin=None):
    res = subprocess.run(["kubectl", *args], input=stdin, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"kubectl {' '.join(args)} failed:\n{res.stderr}")
    return res.stdout


def get_workloads():
    return json.loads(kubectl("get", "workloads.kueue.x-k8s.io", "-A", "-o", "json"))


def cmd_render(a, submit=False):
    batch = jobs.build_batch(a.team, a.count, prefix=a.prefix, gpus=a.gpus, duration=a.duration,
                             priority=a.priority, image=a.image, run_label=a.run)
    doc = json.dumps(jobs.as_list(batch), indent=2)
    if submit:
        print(kubectl("apply", "-f", "-", stdin=doc), end="")
    else:
        print(doc)


def cmd_report(a):
    data = json.load(open(a.input, encoding="utf-8-sig")) if a.input else get_workloads()
    rows = report.summarize(data)
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            report.to_csv(rows, fh)
    print(report.to_markdown(rows))


def cmd_sample(a):
    """Poll every N seconds and append GPU usage per queue to a CSV (for a utilization chart)."""
    with open(a.out, "a", encoding="utf-8") as fh:
        if fh.tell() == 0:
            fh.write("time,cluster_queue,gpus_in_use\n")
        end = time.time() + a.seconds
        while time.time() < end:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            used = report.gpu_in_use(get_workloads())
            for cq in a.queues:
                fh.write(f"{now},{cq},{used.get(cq, 0)}\n")
            fh.flush()
            print(now, used)
            time.sleep(a.interval)


def main(argv=None):
    p = argparse.ArgumentParser(prog="gpuq")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("render", "submit"):
        s = sub.add_parser(name, help=f"{name} a batch of GPU jobs")
        s.add_argument("--team", required=True, choices=["team-a", "team-b"])
        s.add_argument("--count", type=int, default=1)
        s.add_argument("--gpus", type=int, default=1)
        s.add_argument("--duration", type=int, default=60, help="seconds each job holds its GPU")
        s.add_argument("--priority", default="low", choices=["low", "high"])
        s.add_argument("--prefix")
        s.add_argument("--image", default=jobs.FAKE_IMAGE)
        s.add_argument("--run", help="label to tag this experiment run")

    r = sub.add_parser("report", help="per-job wait/run time and evictions")
    r.add_argument("--input", help="saved `kubectl get workloads -A -o json` (default: live cluster)")
    r.add_argument("--csv")

    s = sub.add_parser("sample", help="record GPUs in use per ClusterQueue over time")
    s.add_argument("--out", default="evidence/gpu-usage.csv")
    s.add_argument("--interval", type=int, default=5)
    s.add_argument("--seconds", type=int, default=600)
    s.add_argument("--queues", nargs="+", default=["team-a-cq", "team-b-cq"])

    a = p.parse_args(argv)
    if a.cmd == "render":
        cmd_render(a)
    elif a.cmd == "submit":
        cmd_render(a, submit=True)
    elif a.cmd == "report":
        cmd_report(a)
    elif a.cmd == "sample":
        cmd_sample(a)


if __name__ == "__main__":
    main()
