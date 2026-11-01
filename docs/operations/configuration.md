# Configuration

ArcLayer reads no environment variables and has no configuration file of its own. Everything is an argument to `ArcLayer(...)` or to `create_policy(...)`; the full list with meanings is in [integration/api-reference.md](../integration/api-reference.md). This page covers the choices that need a decision.

## Where the data lives

`db_url` defaults to `sqlite:///./arclayer.db`, which is relative to the working directory: starting the host from another folder creates a second, empty database. For anything lasting, pass an absolute path, for example `ArcLayer("sqlite:////var/lib/myhost/arclayer.db")`. `db_url=None` keeps everything in memory and forgets it on exit. The tables and what they hold are in [persistence](../architecture/persistence.md).

## Embeddings

`embedding="hashing"` (default) is a deterministic 384-dimension hashed bag of words. It is fast and offline but carries no semantic meaning, so the cosine feature and baseline B4 only reflect shared words. Use it for tests and simulations.

`embedding="st:<model>"`, for example `st:sentence-transformers/all-MiniLM-L6-v2`, uses a local sentence-transformers model. It needs the `embeddings` extra, which pulls in torch, and downloads the model on first use.

The choice is recorded in every policy (embedding model id and feature hash). A policy refuses incidents embedded with another model (`FeatureMismatch`), so do not change `embedding` on a database that already holds policies.

## Candidates

`candidates=` takes a YAML path or a list of `CandidateSpec`. It is applied only while the registry is empty, so reopening a database never duplicates or overwrites candidates. A policy keeps the candidates that were enabled when it was created; later registrations and `set_candidate_enabled` affect only policies created afterwards.

## Policy defaults

`create_policy` fills these defaults. They are placeholders with no unit attached, so set them to match what your executors report.

| Argument | Default | Meaning |
|---|---|---|
| `n_max` | `1` | Incidents allowed per task |
| `step_cap` | `20` | Normalises the step position feature |
| `task_cost_cap` | `3.0` | Normalises the remaining-budget feature |
| `incident_cost_cap` | `1.0` | Divides `cost_used` into `C` |
| `incident_latency_cap_ms` | `300000` | Divides `latency_ms` into `L` |
| `strict_sequential` | `False` | `True` makes a second incident raise `PolicyBusy` while one waits for its result |
| `allowed_permissions` | all permissions of enabled candidates | What the gate allows |

Reward weights default to `s=1.0, c=0.2, l=0.1, v=1.0` and must satisfy `w_c + w_l < w_s` and `w_v >= w_s`.

## Bundled config files

`libs/arclayer/configs/` holds the thesis defaults: the six recovery candidates (`candidates/default.yaml`), the feature spec, reward weights, gate and the static map used by baseline B2. They are inputs for experiments and examples; the library does not load them on its own.
