import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import v2_run  # noqa: E402


def ev(event, t, attempt, **kw):
    return {"event": event, "job": kw.pop("job", "a-01"), "size": "medium", "t": t, "attempt": attempt, **kw}


class LostWorkTest(unittest.TestCase):
    def test_no_checkpoint_redoes_everything_before_the_kill(self):
        rows = [
            ev("start", 100, 1, resume_step=0),
            ev("sigterm", 160, 1, step=600, run_s=60, saved_s=None),  # 10 steps/s
            ev("start", 300, 2, resume_step=0),
            ev("end", 400, 2, step=1000, run_s=100),
        ]
        per_job, lost, ckpt, evictions = v2_run.metrics(rows, {"a-01": 90}, 90)
        self.assertEqual(evictions, 1)
        self.assertEqual(lost, 60.0)
        self.assertEqual(per_job[0]["attempts"], 2)
        self.assertEqual(per_job[0]["wait_s"], 10)
        self.assertEqual(per_job[0]["jct_s"], 310)

    def test_periodic_checkpoint_only_loses_work_since_last_save(self):
        rows = [
            ev("start", 100, 1, resume_step=0),
            ev("ckpt", 150, 1, step=500, save_s=0.2),
            ev("sigterm", 160, 1, step=600, run_s=60, saved_s=None),
            ev("start", 300, 2, resume_step=500),
            ev("end", 350, 2, step=1000, run_s=50),
        ]
        _, lost, ckpt, _ = v2_run.metrics(rows, {"a-01": 100}, 100)
        self.assertEqual(lost, 10.0)
        self.assertEqual(ckpt, 0.2)

    def test_sigterm_checkpoint_loses_nothing(self):
        rows = [
            ev("start", 100, 1, resume_step=0),
            ev("sigterm", 160, 1, step=600, run_s=60, saved_s=0.3),
            ev("start", 300, 2, resume_step=600),
            ev("end", 340, 2, step=1000, run_s=40),
        ]
        _, lost, ckpt, _ = v2_run.metrics(rows, {"a-01": 100}, 100)
        self.assertEqual(lost, 0.0)
        self.assertEqual(ckpt, 0.3)

    def test_team_stats(self):
        per_job = [
            {"job": "a-01", "team": "team-a", "submitted": 0, "wait_s": 5, "jct_s": 100, "attempts": 1},
            {"job": "a-02", "team": "team-a", "submitted": 1, "wait_s": 50, "jct_s": 150, "attempts": 1},
            {"job": "b-01", "team": "team-b", "submitted": 90, "wait_s": 2, "jct_s": 60, "attempts": 1},
        ]
        a = v2_run.team_stats(per_job, "team-a", 0, {})
        self.assertEqual(a["makespan_s"], 151)
        self.assertEqual(a["avg_wait_s"], 27.5)
        self.assertEqual(v2_run.team_stats(per_job, "team-b", 0, {})["makespan_s"], 60)


class ManifestTest(unittest.TestCase):
    def test_job_goes_through_kueue_with_real_gpu(self):
        j = v2_run.job_manifest("a-01", "team-a", "large", "run1", ckpt=(15, 1))
        self.assertTrue(j["spec"]["suspend"])
        self.assertEqual(j["metadata"]["labels"]["kueue.x-k8s.io/queue-name"], "gpu-queue")
        spec = j["spec"]["template"]["spec"]
        self.assertEqual(spec["runtimeClassName"], "nvidia")
        env = {e["name"]: e["value"] for e in spec["containers"][0]["env"]}
        self.assertEqual(env["STEPS"], str(v2_run.STEPS["large"]))
        self.assertEqual(env["CKPT_EVERY_S"], "15")
        self.assertEqual(env["CKPT_ON_SIGTERM"], "1")
        self.assertNotIn("memory", spec["containers"][0]["resources"]["limits"])


if __name__ == "__main__":
    unittest.main()
