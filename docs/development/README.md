# Development

Everything about how ArcLayer was planned, decided, tested and checked against the literature. The first four folders come from the original implementation plan (October 2026), split by concern and translated to English. They are a record of intent, so the code may differ in places. Treat [architecture](../architecture/README.md) as the source of truth for what exists. In particular, since 2026-11-01 ArcLayer is a library: the HTTP API, API keys and server entrypoint described in older documents no longer exist (see [deviations-from-plan](decisions/deviations-from-plan.md)).

| Folder | Contents |
|---|---|
| [decisions/](decisions/README.md) | Why things are the way they are: risks found early, technical choices, open questions |
| [design/](design/README.md) | Planned architecture, contracts, API and component behaviour |
| [evaluation/](evaluation/README.md) | Plan for evaluating the layer: test hosts, fault injection, experiment harness, statistics. The code lives in the sibling project `projects/evaluation` |
| [process/](process/README.md) | Implementation phases, testing strategy, security and ethics |
| [research/](research/README.md) | Review of failure handling against production practice and the reference papers, with the sources used |
| [archive/](archive/README.md) | The original implementation plan in Indonesian, from which the English documents above were derived |
