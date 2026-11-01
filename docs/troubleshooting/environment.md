# Environment problems

## `.venv/bin/pytest` fails or runs the wrong Python

Scripts in `.venv/bin` store the absolute path of the folder where the virtualenv was created in their shebang. If the project folder was moved, `pytest` and `pip` still point at the old location.
Fix: call modules through the interpreter, `.venv/bin/python -m pytest` and `.venv/bin/python -m pip`, or recreate the environment (see [running-and-testing](../operations/running-and-testing.md)).

## `ModuleNotFoundError: arclayer`

The package is not installed in development, so Python cannot find it from an arbitrary folder.
Fix: run from `libs/arclayer`, or set `PYTHONPATH=libs/arclayer`. Tests find it through the `pythonpath` entry in `libs/arclayer/pytest.ini`.

## Tests cannot find `configs/...`

Tests resolve `configs/` relative to `libs/arclayer`, so they must run from the checkout and not from an installed copy.
Fix: run them from `libs/arclayer`.

## `arclayer.db` appears in an unexpected folder

`db_url` defaults to `sqlite:///./arclayer.db`, relative to the working directory, so each folder you start the host from gets its own database.
Fix: pass an absolute path, for example `ArcLayer("sqlite:////var/lib/myhost/arclayer.db")`.

## A `.hypothesis` folder appears next to `pytest.ini`

It is the example cache of the Hypothesis library, written when the property tests run.
Fix: nothing is needed. It is safe to delete and is recreated on the next run.

## Installing dependencies downloads gigabytes

`sentence-transformers` depends on torch.
Fix: leave `embedding` at `"hashing"` for development, or install the `embeddings` extra only where the real model is needed.
