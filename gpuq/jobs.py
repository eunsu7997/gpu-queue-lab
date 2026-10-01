"""Build batch/v1 Job manifests that go through a Kueue LocalQueue."""
from datetime import datetime

QUEUE_LABEL = "kueue.x-k8s.io/queue-name"
PRIORITY_LABEL = "kueue.x-k8s.io/priority-class"
GPU_RESOURCE = "nvidia.com/gpu"

FAKE_IMAGE = "busybox:1.36"

# Read by the KWOK pod-complete stage (kwok/stages.yaml) so simulated pods
# "run" for the same duration a real container would. Ignored elsewhere.
KWOK_DELAY_ANNOTATION = "pod-complete.stage.kwok.x-k8s.io/delay"


def build_job(name, team, gpus=1, duration=60, priority="low",
              queue="gpu-queue", image=FAKE_IMAGE, command=None, run_label=None):
    """Return a Job dict.

    With the default busybox image the job just holds its GPU for `duration`
    seconds, which is all Kueue sees: scheduling behaviour is identical to a
    real training job with the same request.
    """
    if gpus < 1:
        raise ValueError("gpus must be >= 1")
    if command is None:
        command = ["sh", "-c",
                   f'echo "start $(date +%s) {name}"; sleep {int(duration)}; echo "end $(date +%s)"']
    labels = {QUEUE_LABEL: queue, PRIORITY_LABEL: priority, "gpuq.dev/team": team}
    if run_label:
        labels["gpuq.dev/run"] = run_label
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name, "namespace": team, "labels": labels},
        "spec": {
            "suspend": True,  # Kueue unsuspends the Job when it is admitted
            "backoffLimit": 0,
            "template": {
                "metadata": {
                    "labels": {"gpuq.dev/team": team},
                    "annotations": {KWOK_DELAY_ANNOTATION: f"{int(duration)}s"},
                },
                "spec": {
                    "restartPolicy": "Never",
                    "terminationGracePeriodSeconds": 5,
                    "containers": [{
                        "name": "train",
                        "image": image,
                        "command": command,
                        "resources": {
                            "requests": {"cpu": "100m", "memory": "64Mi"},
                            "limits": {"cpu": "100m", "memory": "64Mi", GPU_RESOURCE: str(gpus)},
                        },
                    }],
                },
            },
        },
    }


def build_batch(team, count, prefix=None, **kwargs):
    """Build `count` jobs named <prefix>-01, <prefix>-02, ..."""
    if not prefix:
        # time suffix so repeated runs don't collide with finished jobs
        prefix = f"{team}-{kwargs.get('priority', 'low')}-{datetime.now():%H%M%S}"
    return [build_job(f"{prefix}-{i:02d}", team, **kwargs) for i in range(1, count + 1)]


def as_list(items):
    return {"apiVersion": "v1", "kind": "List", "items": items}
