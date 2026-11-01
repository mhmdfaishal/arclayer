# Candidates

A candidate is a recovery your host can run. ArcLayer never runs it; it only decides whether the candidate is allowed and, among the allowed ones, which to pick.

| File | Shows | You should see |
|---|---|---|
| [01_define_candidates.py](01_define_candidates.py) | Three candidates with preconditions, permissions and budgets; a duplicate id; disabling one | A line per candidate, `Conflict` for the duplicate, and a policy created afterwards without the disabled one |
| [candidates.yaml](candidates.yaml) | The same kind of definition as data, in the format `ArcLayer(candidates="file.yaml")` reads | |
| [02_candidates_from_yaml.py](02_candidates_from_yaml.py) | Loading candidates from YAML; a database that is reopened does not get them twice | `2` candidates after the first start and `2` after reopening |
| [03_why_a_candidate_was_rejected.py](03_why_a_candidate_was_rejected.py) | The gate's reason codes: `PRECONDITION_UNMET`, `HOST_CAPABILITY_MISSING`, `OVER_BUDGET`, `PERMISSION_NOT_ALLOWED`, and what happens when nothing is left | One candidate chosen with four rejected, then `safe_stop` when the budget is too small for all |

File 03 is the debugging tool: when a recovery never runs, print `command.excluded`.
