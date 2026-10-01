| job | team | priority | gpus | state | wait_s | run_s | evictions |
|---|---|---|---|---|---|---|---|
| s1-a-01 | team-a | low | 1 | Finished | 101 | 124 | 1 |
| s1-a-02 | team-a | low | 1 | Finished | 0 | 123 | 0 |
| s1-a-03 | team-a | low | 1 | Finished | 0 | 123 | 0 |
| s1-a-04 | team-a | low | 1 | Finished | 102 | 124 | 1 |
| s2-b-01 | team-b | low | 1 | Finished | 1 | 68 | 0 |
| s2-b-02 | team-b | low | 1 | Finished | 3 | 67 | 0 |

| team | jobs | admitted | avg_wait_s | max_wait_s | evictions |
|---|---|---|---|---|---|
| team-a | 4 | 4 | 51 | 102 | 2 |
| team-b | 2 | 2 | 2 | 3 | 0 |
