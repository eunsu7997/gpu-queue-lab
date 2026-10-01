import io
import json
import pathlib
import unittest

from gpuq import jobs, report

FIXTURE = json.loads((pathlib.Path(__file__).parent / "fixtures" / "workloads.json").read_text())


class JobTest(unittest.TestCase):
    def test_job_goes_through_queue_with_gpu_limit(self):
        j = jobs.build_job("x", "team-a", gpus=2, priority="high")
        self.assertEqual(j["metadata"]["labels"][jobs.QUEUE_LABEL], "gpu-queue")
        self.assertEqual(j["metadata"]["labels"][jobs.PRIORITY_LABEL], "high")
        self.assertTrue(j["spec"]["suspend"])
        ctr = j["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(ctr["resources"]["limits"]["nvidia.com/gpu"], "2")

    def test_kwok_delay_matches_duration(self):
        j = jobs.build_job("x", "team-a", duration=90)
        self.assertEqual(j["spec"]["template"]["metadata"]["annotations"][jobs.KWOK_DELAY_ANNOTATION], "90s")

    def test_batch_names_are_numbered(self):
        names = [j["metadata"]["name"] for j in jobs.build_batch("team-b", 3, prefix="s1")]
        self.assertEqual(names, ["s1-01", "s1-02", "s1-03"])

    def test_zero_gpus_rejected(self):
        with self.assertRaises(ValueError):
            jobs.build_job("x", "team-a", gpus=0)


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.rows = {r["job"]: r for r in report.summarize(FIXTURE)}

    def test_finished_job_wait_and_run(self):
        r = self.rows["team-a-low-01"]
        self.assertEqual((r["state"], r["wait_s"], r["run_s"]), ("Finished", 1, 60))

    def test_preempted_job_is_pending_with_eviction(self):
        r = self.rows["team-a-low-03"]
        self.assertEqual((r["state"], r["wait_s"], r["evictions"]), ("Pending", None, 1))

    def test_gpu_count_multiplies_podset_count(self):
        self.assertEqual(self.rows["team-b-low-01"]["gpus"], 2)

    def test_gpu_in_use_counts_running_only(self):
        self.assertEqual(report.gpu_in_use(FIXTURE), {"team-b-cq": 2})

    def test_team_stats(self):
        s = report.team_stats(report.summarize(FIXTURE))
        self.assertEqual(s["team-a"], {"jobs": 2, "admitted": 1, "evictions": 1, "avg_wait_s": 1.0, "max_wait_s": 1.0})
        self.assertEqual(s["team-b"]["avg_wait_s"], 12.0)

    def test_markdown_and_csv_render(self):
        rows = report.summarize(FIXTURE)
        self.assertIn("| team-a | 2 | 1 |", report.to_markdown(rows))
        buf = io.StringIO()
        report.to_csv(rows, buf)
        self.assertEqual(len(buf.getvalue().strip().splitlines()), 4)


if __name__ == "__main__":
    unittest.main()
