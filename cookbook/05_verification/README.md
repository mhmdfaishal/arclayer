# Verification

ArcLayer computes `S` (success), `C` (cost), `L` (latency) and `V` (violation) itself from what the host reports, and turns them into the reward `S - 0.2*C - 0.1*L - V`.

| File | Shows | You should see |
|---|---|---|
| [01_ground_truth.py](01_ground_truth.py) | Scoring a final answer against ground truth that the host never sees | A right answer `recovered` with reward `0.990`, a wrong one `escalate` with `-0.010`, and `truth visible to the host: False` |
| [02_permissions_and_budget.py](02_permissions_and_budget.py) | An honest executor, one that acts outside its permissions, one that overspends | `V = 1` and a negative reward for the last two, although `S = 1` |

A violation cancels the credit for succeeding. ArcLayer cannot check `actions_performed` itself, so the executor must report it truthfully.
