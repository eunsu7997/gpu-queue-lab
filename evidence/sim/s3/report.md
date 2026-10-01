| job | team | priority | gpus | state | wait_s | run_s | evictions |
|---|---|---|---|---|---|---|---|
| s3-b-01 | team-b | low | 1 | Finished | 0 | 91 | 0 |
| s3-b-02 | team-b | low | 1 | Finished | 0 | 91 | 0 |
| s3-low-01 | team-a | low | 1 | Finished | 48 | 91 | 1 |
| s3-low-02 | team-a | low | 1 | Finished | 0 | 91 | 0 |
| s3-high-01 | team-a | high | 1 | Finished | 1 | 31 | 0 |

| team | jobs | admitted | avg_wait_s | max_wait_s | evictions |
|---|---|---|---|---|---|
| team-a | 3 | 3 | 16 | 48 | 1 |
| team-b | 2 | 2 | 0 | 0 | 0 |
