# Statistical Analysis

> Status note: translated from the original implementation plan (October 2026). The code may have diverged from this plan; see docs/architecture for the current structure. The code described here now lives in the sibling project projects/evaluation.

## 10.1 Metrics (Table 8)

`analysis/metrics.py` computes the following from audit records:
- Post-repair pass rate per task (benchmark criterion after recovery).
- Recovery success rate per incident.
- Trial success rate when a case has several attempts.
- Number of attempts per task, tokens, and cost relative to B1.
- Latency p50, p95.
- Violation rate.
- Cumulative reward per incident sequence per seed (learning curve).
- All metrics broken down by fault class and by orchestration pattern.
- Attribution accuracy only when `label_source = ATTRIBUTION`.

## 10.2 Statistics (`analysis/stats.py`, `analysis/power.py`)

| Test | Implementation | Notes |
|---|---|---|
| McNemar (P vs B1..B4, P vs P-D, P vs P-F) | statsmodels, exact version when discordant pairs < 25 | At task level, per seed |
| Bootstrap 95% CI of the difference in proportions | Resampling **per task_id** (cluster bootstrap), 10,000 iterations, seed recorded | Proposal III.3.4 |
| Wilcoxon signed-rank | SciPy, for paired cost and latency | Effect size: rank-biserial |
| Odds ratio of discordant pairs | `b / c` with CI | |
| Holm correction | On the family P vs {B1, B2, B3, B4} | As stated in the proposal |
| Upper bound on violations | One-sided 95% Clopper-Pearson when there are zero violations | For H3 |
| Power | McNemar formula (Connor) or Monte Carlo simulation from the pilot discordant proportions, target power 0.8, alpha 0.05 | Computed before the evaluation data is opened |

Pooling seeds: gotcha. Five seeds on the same tasks are not independent. The main McNemar test is run per seed and the range is reported, or on the per-task majority outcome across seeds. Fix one of the two before evaluation (Q6). The per-task bootstrap already handles the dependence between seeds if all seeds are put in the same cluster.

## 10.3 Report

`analysis/report.py` produces CSV/LaTeX tables and plots (cumulative reward curve, bar chart of post-repair pass rate per class and pattern, heatmap of candidate choice per class) from the audit DB. All numbers in Chapter IV must be regenerable with a single command.
