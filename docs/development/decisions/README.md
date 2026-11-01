# Design Decisions

This folder holds the design rationale behind ArcLayer, the external recovery control layer for multi-agent LLM systems.
It records the decisions that were made, the risks and gotchas found while planning, and the questions that were still open.
The files are translated from the original implementation plan and may lag the code.

- [overview.md](overview.md): summary of the system form, algorithm and test hosts, and the mapping from the proposal to code modules.
- [risks-and-gotchas.md](risks-and-gotchas.md): nine design-affecting risks (constant features, reward definition, ground-truth leakage, experiment cost, concurrency, and others).
- [technical-decisions.md](technical-decisions.md): technology choices per layer, with reasons and rejected alternatives.
- [open-questions.md](open-questions.md): questions Q1 to Q8 that needed a decision, with recommendations.
- [deviations-from-plan.md](deviations-from-plan.md): where the implementation departs from the plan, and where the plan differs from the current proposal.
