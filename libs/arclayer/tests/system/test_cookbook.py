"""Every cookbook example must run, and every cookbook folder must be documented."""

import ast
import importlib.util
import os
import pathlib
import re
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[4]
COOKBOOK = REPO / "cookbook"
LIB = REPO / "libs" / "arclayer"
FOLDERS = sorted(p for p in COOKBOOK.glob("[0-9][0-9]_*") if p.is_dir())
EXAMPLES = sorted(COOKBOOK.glob("[0-9][0-9]_*/[0-9][0-9]_*.py"))


def test_the_cookbook_exists_and_has_examples():
    assert (COOKBOOK / "README.md").exists()
    assert len(EXAMPLES) >= 15


def test_the_cookbook_readme_lists_every_folder():
    text = (COOKBOOK / "README.md").read_text(encoding="utf-8")
    assert [f.name for f in FOLDERS if f.name not in text] == []


@pytest.mark.parametrize("folder", FOLDERS, ids=lambda p: p.name)
def test_every_folder_has_a_readme_that_lists_its_examples(folder):
    readme = folder / "README.md"
    assert readme.exists(), f"{folder.name} has no README.md"
    text = readme.read_text(encoding="utf-8")
    assert [f.name for f in folder.glob("[0-9][0-9]_*.py") if f.name not in text] == []


def third_party_imports(source: str) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
    return modules - set(sys.stdlib_module_names) - {"arclayer"}


FRAMEWORK_EXAMPLES = sorted((COOKBOOK / "06_frameworks").glob("[0-9][0-9]_*.py"))


def test_the_frameworks_folder_covers_several_frameworks():
    assert len(FRAMEWORK_EXAMPLES) >= 8


@pytest.mark.parametrize("example", FRAMEWORK_EXAMPLES, ids=lambda p: p.name)
def test_a_framework_example_names_the_package_it_requires(example):
    source = example.read_text(encoding="utf-8")
    requires = [line for line in ast.get_docstring(ast.parse(source)).splitlines() if line.startswith("Requires")]
    assert requires, "the docstring needs a line that starts with 'Requires'"
    assert re.search(r"`[A-Za-z0-9_.\-\[\]=<>]+`", requires[0]), "the Requires line must name the PyPI package in backticks"


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_the_example_runs_and_says_what_it_shows(example, tmp_path):
    source = example.read_text(encoding="utf-8")
    missing = sorted(m for m in third_party_imports(source) if importlib.util.find_spec(m) is None)
    if missing:
        pytest.skip(f"not installed: {', '.join(missing)}")
    doc = ast.get_docstring(ast.parse(source))
    assert doc and doc.splitlines()[0].strip(), "the example needs a docstring that starts with its title"

    run = subprocess.run(
        [sys.executable, str(example)], cwd=tmp_path, capture_output=True, text=True, timeout=180,
        env={**os.environ, "PYTHONPATH": str(LIB)},
    )

    assert run.returncode == 0, run.stderr[-800:]
    assert run.stdout.strip(), "the example should print what it demonstrates"
    assert list(tmp_path.iterdir()) == [], "an example must not leave files in the working directory"
