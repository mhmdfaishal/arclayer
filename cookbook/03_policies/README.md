# Policies

A policy decides which eligible candidate to run. `P` is LinUCB; `B0` to `B3` are baselines that exist to compare against.

| File | Shows | You should see |
|---|---|---|
| [01_choose_a_policy.py](01_choose_a_policy.py) | The same 200 faults handled by `B0`, `B1`, `B2`, `B3` and `P` | Mean reward `0.000`, `0.000`, `0.990`, `0.345`, `0.970` |
| [02_strict_sequential.py](02_strict_sequential.py) | Overlapping incidents are accepted by default; `strict_sequential=True` refuses them | `PolicyBusy` for the strict policy until the first result is reported |
| [03_warm_start_and_freeze.py](03_warm_start_and_freeze.py) | Starting a policy from a snapshot of an earlier one, and freezing a policy | Cold start `0.950`, warm start `0.990`, and `policy updated: False` after the freeze |

The numbers in 01 come from the seeded simulation in the file. `B2` is perfect there because its table matches how the simulated host works; in real hosts a fixed table is only as good as the person who wrote it, which is the case for learning. `P` starts knowing nothing and gets close.

A warm start needs the same candidates in the registry as the snapshot has, or `create_policy` raises `ValueError`.
