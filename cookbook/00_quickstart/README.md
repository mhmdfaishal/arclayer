# Quickstart

| File | Shows | You should see |
|---|---|---|
| [01_hello_recovery.py](01_hello_recovery.py) | The smallest complete integration: one candidate, one fault, one call to `handle_fault` | `action: execute`, `status: recovered`, `reward: 0.9899` |
| [02_learning_which_recovery_works.py](02_learning_which_recovery_works.py) | Two recoveries, one of which never works: ArcLayer tries both, then settles on the one that does | `retry` runs once and fails, `use_backup` runs the other nine times |

Start with 01. The reward in 01 is `1 - 0.2 * (0.05 / 1.0) - 0.1 * (300 / 300000) = 0.9899`: full credit for success, minus small penalties for cost and latency.
