"""Small CNN training loop on random MNIST-shaped data, for the time-slicing test.

No dataset download: the point is GPU time per job, not accuracy.
Prints one JSON line: {"job", "steps", "train_s", "steps_per_s", "gpu", "max_mem_mb"}.
"""
import json
import os
import time

import torch
import torch.nn as nn

STEPS = int(os.environ.get("STEPS", "3000"))
BATCH = int(os.environ.get("BATCH", "256"))

dev = torch.device("cuda")
model = nn.Sequential(
    nn.Conv2d(1, 32, 3, padding=1), nn.ReLU(),
    nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
    nn.Conv2d(64, 128, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
    nn.Flatten(), nn.Linear(128 * 7 * 7, 256), nn.ReLU(), nn.Linear(256, 10),
).to(dev)
opt = torch.optim.SGD(model.parameters(), lr=0.01)
loss_fn = nn.CrossEntropyLoss()
x = torch.randn(BATCH, 1, 28, 28, device=dev)
y = torch.randint(0, 10, (BATCH,), device=dev)

for _ in range(20):  # warm-up (cuDNN autotune, allocator)
    opt.zero_grad(); loss_fn(model(x), y).backward(); opt.step()
torch.cuda.synchronize()

t0 = time.time()
for _ in range(STEPS):
    opt.zero_grad(); loss_fn(model(x), y).backward(); opt.step()
torch.cuda.synchronize()
dt = time.time() - t0

print(json.dumps({
    "job": os.environ.get("HOSTNAME", "local"),
    "steps": STEPS,
    "train_s": round(dt, 2),
    "steps_per_s": round(STEPS / dt, 1),
    "gpu": torch.cuda.get_device_name(0),
    "max_mem_mb": round(torch.cuda.max_memory_allocated() / 2**20),
    "start": round(t0, 2),
    "end": round(t0 + dt, 2),
}))
