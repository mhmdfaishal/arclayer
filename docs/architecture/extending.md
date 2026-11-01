# Where new code goes

| You want to add | Put it in | Then |
|---|---|---|
| An embedding model | `arclayer/apiclients/embedding/<name>.py` | add the spec string in `make_embedder` (`arclayer/bootstrap.py`); tests in `tests/unit/apiclients/embedding/` |
| Any other call to an external service | `arclayer/apiclients/` | do not import httpx or a vendor SDK anywhere else; the architecture test fails |
| A method on `ArcLayer` | `arclayer/api.py` | back it with a use case in `arclayer/usecases/` and wire that use case in `bootstrap.py`; test it in `tests/unit/api/` |
| A selection policy or baseline | `arclayer/domain/policies/` | register it in `factory.py` and add the kind to `PolicyKind` in the contracts |
| A storage backend | `arclayer/infrastructure/persistence/` | implement the ports in `usecases/ports.py`, select it in `bootstrap.py` |
| A gate rule or a feature | `arclayer/domain/gate.py` or `features.py` | a new feature changes the feature hash, so existing policies reject new incidents with `FeatureMismatch`; create a new policy |
| A verifier | `arclayer/usecases/services/verifiers.py` | add it to `DEFAULT_VERIFIERS`; candidates refer to it by `verifier_id` |
| A recovery candidate | a `CandidateSpec` passed to `ArcLayer(candidates=...)` or a YAML entry in `configs/candidates/` | the executor for it is written in the host, not here |
| A host integration | the host's own code | implement `HostAdapter` and `RecoveryExecutor`; see [integration](../integration/README.md) |

## Tests

`tests/unit/` mirrors the package layout, and `tests/system/` runs a full learning loop against a synthetic host. Run them with `pytest` from `libs/arclayer`; see [running-and-testing](../operations/running-and-testing.md).

A change that moves code between layers should start with a failing case in `tests/unit/test_architecture.py`.
