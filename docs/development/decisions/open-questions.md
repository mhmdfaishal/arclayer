# Open Questions

> Status note: translated from the original implementation plan (October 2026). The code may have diverged from this plan; see docs/architecture for the current structure.

These questions needed a decision before Phase 2 was complete.

| ID | Question | Recommendation |
|---|---|---|
| Q1 | Candidate supported classes: hard filter or soft feature? What replaces the precondition indicator? (Gotcha 1.1) | Soft feature; optional preconditions as a completeness score |
| Q2 | Framework for the reference host and the second host | One framework with native checkpoints + one framework with a different pattern; confirm after spike F5-01 |
| Q3 | Does P-D drop the cost ratio or not? | Keep the cost ratio; drop cosine, class match, and precondition completeness |
| Q4 | Is `λ` calibrated or fixed at 0.45? | Fixed, as in the proposal |
| Q5 | Do P and P-D start from zero or from the calibration snapshot? | From the snapshot, so that P vs P-F is a fair comparison |
| Q6 | How to combine seeds in McNemar | Decide before evaluation; proposal: per seed + cluster bootstrap across seeds |
| Q7 | `N_max` for the main path | 1 (enables the outcome matrix); `N_max > 1` as an additional online experiment |
| Q8 | LLM backbone and total budget | Decide after E-01 and the outcome-matrix cost estimate |

Items Q1, Q3, Q5, and Q7 touch the content of Chapter III of the proposal. If they are decided differently from the current proposal text, the proposal text needs to be adjusted so that the implementation and the document do not contradict each other.
