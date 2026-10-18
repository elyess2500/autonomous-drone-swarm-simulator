# Main results

| Condition | n | Coverage mean % (SD) | Survivors mean | Connected mean % | Task completions mean | Pending map exposure mean |
| --- | --- | --- | --- | --- | --- | --- |
| 90 px / 8 drones | 8 | 5.21 (1.40) | 0.000 | 92.63 | 3.88 | 19.76 |
| 180 px / 8 drones | 8 | 12.51 (0.77) | 0.750 | 96.91 | 6.62 | 4.15 |
| 360 px / 8 drones | 8 | 15.65 (1.86) | 1.000 | 98.64 | 5.88 | 0.00 |
| 180 px / 4 drones | 8 | 7.69 (0.95) | 0.250 | 98.02 | 3.62 | 0.04 |
| 180 px / 16 drones | 8 | 15.66 (0.70) | 0.875 | 94.18 | 7.88 | 28.84 |

| Contrast versus reference | Mean difference (pp) | 95% CI | 98.75% CI | Primary classification |
| --- | --- | --- | --- | --- |
| range_90 | -7.309 | [-8.471, -6.162] | [-8.792, -5.879] | SUPPORTED difference |
| range_360 | +3.131 | [+1.729, +4.469] | [+1.354, +4.811] | SUPPORTED difference |
| swarm_4 | -4.823 | [-5.837, -3.824] | [-6.096, -3.564] | SUPPORTED difference |
| swarm_16 | +3.146 | [+2.443, +3.771] | [+2.235, +3.912] | SUPPORTED difference |

| Condition | Awards | Completions | Cancellations | Waits | Backoffs | Path searches | Energy checks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 90 px / 8 drones | 10.00 | 3.88 | 1.38 | 614.25 | 0.12 | 1636.38 | 254268.38 |
| 180 px / 8 drones | 16.12 | 6.62 | 2.88 | 1348.62 | 0.88 | 1831.75 | 24418.75 |
| 360 px / 8 drones | 14.88 | 5.88 | 1.38 | 1495.88 | 0.88 | 1444.12 | 4004.12 |
| 180 px / 4 drones | 9.12 | 3.62 | 1.62 | 144.75 | 0.25 | 585.75 | 2410.75 |
| 180 px / 16 drones | 19.88 | 7.88 | 2.50 | 2183.00 | 1.38 | 4332.25 | 307933.00 |

| Condition | Mean update ms | Mean p50 | Mean p95 | Mean p99 | Worst max | Mean excluding CSV ms |
| --- | --- | --- | --- | --- | --- | --- |
| 90 px / 8 drones | 36.628 | 32.653 | 48.990 | 84.018 | 2439.765 | 36.438 |
| 180 px / 8 drones | 13.254 | 7.428 | 26.648 | 68.001 | 602.820 | 13.055 |
| 360 px / 8 drones | 8.786 | 6.892 | 14.452 | 33.085 | 522.805 | 8.601 |
| 180 px / 4 drones | 3.886 | 3.280 | 5.991 | 17.017 | 70.827 | 3.694 |
| 180 px / 16 drones | 64.819 | 42.838 | 132.864 | 366.494 | 3736.303 | 64.618 |

All central values are across eight seed-level runs, not independent ticks. Timing p50/p95/p99 columns are means of run quantiles; worst maximum is the largest tick latency in the condition.
