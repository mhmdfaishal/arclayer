# Dependency rules

Dependencies point inward: `delivery` and `infrastructure` depend on `usecases`, and `usecases` depends on `domain`. The rules below are enforced by `libs/arclayer/tests/unit/test_architecture.py`, which parses every source file with `ast`, so lazy imports inside functions are checked too.

## Which package may import which

| Area | May import | May not import |
|---|---|---|
| `arclayer/domain` | `arclayer.domain` | any framework, pydantic, sqlalchemy |
| `arclayer/usecases` | `domain`, `usecases` | `infrastructure`, `delivery`, any framework |
| `arclayer/infrastructure` | `domain`, `usecases` (ports and errors), `infrastructure` | `delivery`, `bootstrap` |
| `arclayer/infrastructure/config` | the above plus `contracts` | `delivery`, `bootstrap` |
| `arclayer/delivery` | `domain`, `usecases`, `delivery`, `bootstrap`, `contracts` | `infrastructure`, `apiclients` |
| `arclayer/apiclients` | `apiclients` | everything else in `arclayer` |
| `arclayer/bootstrap.py` | `domain`, `usecases`, `infrastructure`, `apiclients` | `delivery` |
| `arclayer/contracts` | `contracts` | `domain`, `usecases`, `infrastructure`, `host` |
| `arclayer/host` | `host`, `contracts` | `domain`, `usecases`, `infrastructure` |
| `arclayer/api.py` | `bootstrap`, `contracts`, `delivery`, `host`, `usecases.errors`, `domain.errors` | `infrastructure`, `apiclients` |
| `arclayer/__init__.py` | `api`, `host`, `contracts` | everything else |

`contracts` and `host` are the surface a host sees. Keeping them free of ArcLayer internals is what lets a host depend on the contract and nothing else.

## Third-party libraries are confined too

| Library | Allowed only in |
|---|---|
| `httpx`, `requests`, `aiohttp`, `urllib3` | `arclayer/apiclients` |
| `google`, `openai`, `anthropic`, `sentence_transformers`, `torch`, `transformers` | `arclayer/apiclients` |
| `sqlalchemy` | `arclayer/infrastructure/persistence` |
| `pydantic` | `arclayer/contracts`, `arclayer/delivery`, `arclayer/infrastructure/config` |
| `fastapi`, `starlette`, `uvicorn`, `pydantic_settings` | nowhere |

The practical effects: any new call to an external service has to live in `apiclients`, and no web framework can be added without the test failing. ArcLayer is a library that the host calls directly.

## Deliberate exception

`arclayer/infrastructure/config` imports `contracts`, because the YAML files are validated with the same models as the messages. No other `infrastructure` subpackage may.

## Limits of the check

The test reads `import` and `from ... import` statements. Dynamic loading with `importlib.import_module(...)` or `__import__(...)` is not detected. A new package without a rule fails `test_every_source_file_is_covered_by_a_rule`, so it cannot slip in unguarded.
