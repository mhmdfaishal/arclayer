# Setting up and testing

## Set up

From the repository root:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r libs/arclayer/requirements.txt
```

This creates `.venv` and installs the pinned requirements. Call pip and pytest through the interpreter (`.venv/bin/python -m ...`), not as `.venv/bin/pip` or `.venv/bin/pytest`: those scripts store the absolute path of the folder where the environment was created. `sentence-transformers` pulls in torch, which is a large download; it is needed only for `embedding="st:<model>"`.

The package is not installed in development. To import it from a script or a REPL, run from `libs/arclayer` or put that folder on `PYTHONPATH`:

```bash
PYTHONPATH=libs/arclayer .venv/bin/python your_script.py
```

## Run the tests

```bash
cd libs/arclayer
../../.venv/bin/python -m pytest                  # everything
../../.venv/bin/python -m pytest -m "not slow"    # skip the long tests
```

Run it from `libs/arclayer`: `pytest.ini` and the `configs/` folder that some tests read are there.

The slow tests are the real sentence-transformers model and the synthetic learning check: after a 20 percent calibration phase, LinUCB must beat the static map, random and retry baselines.

Hypothesis, used by the property tests, writes a `.hypothesis` cache folder next to `pytest.ini`. It is safe to delete and is recreated on the next run.

## Install as a package

`libs/arclayer/pyproject.toml` defines the package `arclayer`, with the extras `embeddings` and `dev`. Installing it with `pip install` has not been tested yet; the development workflow above uses the `pythonpath` entry in `pytest.ini` instead.
