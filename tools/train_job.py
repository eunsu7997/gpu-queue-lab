"""Real PyTorch training job for the v2 experiments (mixed sizes, optional checkpointing).

Synthetic data (no dataset download): the point is GPU time and what happens on
preemption, not accuracy.

Environment:
  SIZE            small | medium | large   (model width + batch, see SIZES)
  STEPS           total optimizer steps (default per size)
  CKPT_EVERY_S    save a checkpoint every N seconds of training, 0 = never (default 0)
  CKPT_ON_SIGTERM 1 = save one more checkpoint when Kubernetes sends SIGTERM (default 0)
  CKPT_DIR        where checkpoints and the attempt log go (default /ckpt/<JOB_NAME>)
  JOB_NAME        name used in logs (default $HOSTNAME)

Every attempt (a fresh pod after preemption is a new attempt) appends JSON lines to
CKPT_DIR/attempts.jsonl: start / ckpt / sigterm / end. The log lives on the node
(hostPath), so it survives the pod being deleted by an eviction.
"""
import json
import os
import signal
import sys
import time

import torch
import torch.nn as nn

# width: conv channels, batch: images per step. small is launch-bound (GPU not saturated),
# large keeps the RTX 4060 at ~100% on its own.
SIZES = {
    "small":  {"width": 16, "batch": 32,  "steps": 6000},
    "medium": {"width": 32, "batch": 128, "steps": 3000},
    "large":  {"width": 64, "batch": 256, "steps": 1500},
}

size = os.environ.get("SIZE", "medium")
cfg = SIZES[size]
steps_total = int(os.environ.get("STEPS", cfg["steps"]))
ckpt_every = float(os.environ.get("CKPT_EVERY_S", "0"))
ckpt_on_term = os.environ.get("CKPT_ON_SIGTERM", "0") == "1"
job = os.environ.get("JOB_NAME") or os.environ.get("HOSTNAME", "local")
ckpt_dir = os.environ.get("CKPT_DIR") or f"/ckpt/{job}"
os.makedirs(ckpt_dir, exist_ok=True)
ckpt_path = os.path.join(ckpt_dir, "ckpt.pt")
log_path = os.path.join(ckpt_dir, "attempts.jsonl")


def log(event, **kw):
    rec = {"event": event, "job": job, "size": size, "t": round(time.time(), 3), **kw}
    with open(log_path, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(json.dumps(rec), flush=True)


w = cfg["width"]
dev = torch.device("cuda")
torch.manual_seed(0)
model = nn.Sequential(
    nn.Conv2d(1, w, 3, padding=1), nn.ReLU(),
    nn.Conv2d(w, 2 * w, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
    nn.Conv2d(2 * w, 4 * w, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
    nn.Flatten(), nn.Linear(4 * w * 7 * 7, 256), nn.ReLU(), nn.Linear(256, 10),
).to(dev)
opt = torch.optim.SGD(model.parameters(), lr=0.01, momentum=0.9)
loss_fn = nn.CrossEntropyLoss()
x = torch.randn(cfg["batch"], 1, 28, 28, device=dev)
y = torch.randint(0, 10, (cfg["batch"],), device=dev)

step = 0
attempt = 1
if os.path.exists(ckpt_path):
    state = torch.load(ckpt_path, map_location=dev)
    model.load_state_dict(state["model"])
    opt.load_state_dict(state["opt"])
    step = state["step"]
if os.path.exists(log_path):
    with open(log_path) as fh:
        attempt = 1 + sum(1 for line in fh if '"event": "start"' in line)


def save():
    t = time.time()
    torch.save({"model": model.state_dict(), "opt": opt.state_dict(), "step": step}, ckpt_path + ".tmp")
    os.replace(ckpt_path + ".tmp", ckpt_path)  # atomic: a kill mid-save never leaves a broken file
    return time.time() - t


term = {"flag": False}
signal.signal(signal.SIGTERM, lambda *_: term.update(flag=True))

log("start", attempt=attempt, resume_step=step, steps_total=steps_total,
    ckpt_every_s=ckpt_every, ckpt_on_sigterm=ckpt_on_term)
t_start = time.time()
last_ckpt = t_start
while step < steps_total:
    opt.zero_grad(set_to_none=True)
    loss_fn(model(x), y).backward()
    opt.step()
    step += 1
    if term["flag"]:
        torch.cuda.synchronize()
        saved = None
        if ckpt_on_term:
            saved = round(save(), 3)
        log("sigterm", attempt=attempt, step=step, saved_s=saved, run_s=round(time.time() - t_start, 2))
        sys.exit(143)
    if ckpt_every and step % 50 == 0 and time.time() - last_ckpt >= ckpt_every:
        torch.cuda.synchronize()
        log("ckpt", attempt=attempt, step=step, save_s=round(save(), 3))
        last_ckpt = time.time()

torch.cuda.synchronize()
log("end", attempt=attempt, step=step, run_s=round(time.time() - t_start, 2),
    max_mem_mb=round(torch.cuda.max_memory_allocated() / 2**20))
